"""
services/campaign_runner.py
===========================
Runs the full generate -> send -> log pipeline on a background thread so the
Streamlit interface stays responsive during long campaigns.

This is the orchestration that used to live in the original ``main.py``,
re-shaped so that:

    * progress and counters are published to a shared, thread-safe
      ``RunnerState`` singleton that the UI polls;
    * every step is streamed to the live ``log_manager``;
    * scheduled sends wait (with a live countdown) until their start time;
    * the job can be cancelled cleanly at any point.

The worker thread only ever touches the RunnerState, the LogManager and the
filesystem/network — it never calls Streamlit APIs — so it is safe to run
detached from the script's execution context.
"""

from __future__ import annotations

import copy
import csv
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from services.certificate_generator import (
    CertificateGenerationError,
    generate_certificate,
)
from services.config_manager import GENERATED_DIR, LOGS_DIR, resolve_path
from services.email_sender import build_context, send_certificate_email
from services.excel_reader import Participant
from services.log_manager import log_manager

# Status constants
STATUS_IDLE = "idle"
STATUS_SCHEDULED = "scheduled"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_ERROR = "error"

CSV_HEADERS = [
    "Name",
    "Email",
    "PDF Generated",
    "Email Sent",
    "Retries",
    "Timestamp",
    "Error Message",
]


@dataclass
class RunnerState:
    """Thread-safe, process-level snapshot of the current campaign."""

    status: str = STATUS_IDLE
    total: int = 0
    processed: int = 0
    certs_generated: int = 0
    emails_sent: int = 0
    failed: int = 0
    current_index: int = 0
    current_name: str = ""
    current_email: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    scheduled_for: Optional[float] = None
    error_message: str = ""
    csv_log_path: str = ""
    dry_run: bool = False

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- derived read-only metrics ------------------------------------
    @property
    def is_active(self) -> bool:
        return self.status in (STATUS_RUNNING, STATUS_SCHEDULED)

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.processed)

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0.0
        return min(100.0, (self.processed / self.total) * 100.0)

    @property
    def success_rate(self) -> float:
        if self.processed == 0:
            return 0.0
        return (self.emails_sent / self.processed) * 100.0

    @property
    def elapsed_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return max(0.0, end - self.start_time)

    @property
    def eta_seconds(self) -> float:
        if self.processed == 0 or self.start_time is None or not self.is_active:
            return 0.0
        rate = self.elapsed_seconds / self.processed
        return rate * self.remaining

    @property
    def countdown_seconds(self) -> float:
        if self.status != STATUS_SCHEDULED or self.scheduled_for is None:
            return 0.0
        return max(0.0, self.scheduled_for - time.time())

    def snapshot(self) -> "RunnerState":
        """Return a lock-free shallow copy safe for the UI to read."""
        with self._lock:
            clone = RunnerState()
            for f_name in (
                "status",
                "total",
                "processed",
                "certs_generated",
                "emails_sent",
                "failed",
                "current_index",
                "current_name",
                "current_email",
                "start_time",
                "end_time",
                "scheduled_for",
                "error_message",
                "csv_log_path",
                "dry_run",
            ):
                setattr(clone, f_name, getattr(self, f_name))
            return clone


class CampaignRunner:
    """Owns the background worker thread and the shared RunnerState."""

    def __init__(self) -> None:
        self.state = RunnerState()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle -----------------------------------------------------
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        participants: List[Participant],
        config: Dict,
        scheduled_for: Optional[float] = None,
    ) -> None:
        """Kick off a campaign on a background thread."""
        if self.is_busy():
            raise RuntimeError("A campaign is already running.")

        self._cancel.clear()
        job_config = copy.deepcopy(config)
        job_participants = list(participants)

        with self.state._lock:
            self.state = RunnerState()
        self.state.total = len(job_participants)
        self.state.scheduled_for = scheduled_for
        self.state.dry_run = bool(job_config.get("dry_run", False))
        self.state.status = STATUS_SCHEDULED if scheduled_for else STATUS_RUNNING

        self._thread = threading.Thread(
            target=self._run,
            args=(job_participants, job_config, scheduled_for),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """Request cancellation of the running/scheduled campaign."""
        self._cancel.set()

    # -- worker --------------------------------------------------------
    def _run(
        self,
        participants: List[Participant],
        config: Dict,
        scheduled_for: Optional[float],
    ) -> None:
        try:
            if scheduled_for:
                self._wait_until(scheduled_for)
                if self._cancel.is_set():
                    self._finish(STATUS_CANCELLED, "Campaign cancelled before start.")
                    return

            self._set(status=STATUS_RUNNING, start_time=time.time())
            self._execute(participants, config)

            if self._cancel.is_set():
                self._finish(STATUS_CANCELLED, "Campaign cancelled.")
            else:
                self._finish(STATUS_COMPLETED, "")
        except Exception as exc:  # noqa: BLE001
            log_manager.error(f"Campaign crashed: {exc}")
            self._finish(STATUS_ERROR, str(exc))

    def _wait_until(self, target_epoch: float) -> None:
        when = datetime.fromtimestamp(target_epoch).strftime("%Y-%m-%d %H:%M:%S")
        log_manager.info(f"Campaign scheduled for {when}. Waiting…")
        while time.time() < target_epoch:
            if self._cancel.is_set():
                return
            time.sleep(0.5)

    def _execute(self, participants: List[Participant], config: Dict) -> None:
        template_path = resolve_path(config.get("certificate_template", ""))
        elements = config.get("certificate_elements", [])
        email_settings = config.get("email_settings", {})
        template = config.get("email_template", {})
        campaign = config.get("campaign_settings", {})
        delay = config.get("delay_settings", {})
        dry_run = bool(config.get("dry_run", False))

        certificate_name = campaign.get("certificate_name", "Certificate")
        organization = email_settings.get("organization_name", "")
        subject = email_settings.get("email_subject", "Your Certificate")

        # Delay -----------------------------------------------------------
        unit_factor = 60.0 if delay.get("delay_unit") == "minutes" else 1.0
        throttle_seconds = float(delay.get("delay_between_emails", 2.0)) * unit_factor

        # Retries ---------------------------------------------------------
        max_retries = int(delay.get("max_retry_attempts", delay.get("retry_count", 3)))
        retry_delay = float(delay.get("retry_delay", 5))
        backoff = [retry_delay] * max(1, max_retries)

        batch_size = max(1, int(campaign.get("batch_size", 50)))
        output_dir = GENERATED_DIR

        csv_path = LOGS_DIR / f"mail_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._set(csv_log_path=str(csv_path))
        self._ensure_csv_header(csv_path)

        total = len(participants)
        mode = "DRY RUN — no emails will actually be sent" if dry_run else "live send"
        log_manager.info(f"Starting campaign ({mode}) for {total} participant(s).")

        for index, participant in enumerate(participants, start=1):
            if self._cancel.is_set():
                log_manager.warning("Cancellation requested — stopping.")
                break

            if batch_size and (index - 1) % batch_size == 0 and index > 1:
                log_manager.info(f"— Batch boundary at #{index} —")

            self._set(
                current_index=index,
                current_name=participant.name,
                current_email=participant.email,
            )
            log_manager.info(
                f"Processing {index}/{total}", participant=participant.name
            )

            pdf_generated = False
            email_sent = False
            retries = 0
            error_message = ""

            # -- Certificate ------------------------------------------
            try:
                pdf_path = generate_certificate(
                    participant, template_path, elements, config, output_dir
                )
                pdf_generated = True
                self._inc(certs_generated=1)
                log_manager.success(
                    "Certificate generated", participant=participant.name
                )
            except CertificateGenerationError as exc:
                error_message = str(exc)
                log_manager.error(
                    f"Certificate failed: {exc}", participant=participant.name
                )
                self._inc(processed=1, failed=1)
                self._write_csv(csv_path, participant, False, False, 0, error_message)
                continue

            # -- Email ------------------------------------------------
            context = build_context(
                name=participant.name,
                email=participant.email,
                organization=organization,
                certificate_name=certificate_name,
                extras=participant.extras,
            )
            log_manager.info("Sending email…", participant=participant.name)
            result = send_certificate_email(
                name=participant.name,
                email=participant.email,
                pdf_path=pdf_path,
                email_settings=email_settings,
                template=template,
                context=context,
                subject=subject,
                max_retries=max_retries,
                retry_backoff=backoff,
                dry_run=dry_run,
            )
            email_sent = result.success
            retries = result.retries
            error_message = result.error_message

            if email_sent:
                self._inc(emails_sent=1)
                if retries:
                    log_manager.warning(
                        f"Email sent after {retries} retr{'y' if retries == 1 else 'ies'}",
                        participant=participant.name,
                    )
                else:
                    log_manager.success("Email sent", participant=participant.name)
            else:
                log_manager.error(
                    f"Email failed after {retries} retries: {error_message}",
                    participant=participant.name,
                )

            self._inc(processed=1)
            if not (pdf_generated and email_sent):
                self._inc(failed=1)

            self._write_csv(
                csv_path, participant, pdf_generated, email_sent, retries, error_message
            )

            # -- Throttle --------------------------------------------
            if index < total and not self._cancel.is_set() and throttle_seconds > 0:
                self._interruptible_sleep(throttle_seconds)

    # -- helpers -------------------------------------------------------
    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if self._cancel.is_set():
                return
            time.sleep(min(0.25, end - time.time()))

    def _ensure_csv_header(self, path: Path) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADERS)

    def _write_csv(
        self,
        path: Path,
        participant: Participant,
        pdf_generated: bool,
        email_sent: bool,
        retries: int,
        error_message: str,
    ) -> None:
        row = [
            participant.name,
            participant.email,
            "Yes" if pdf_generated else "No",
            "Yes" if email_sent else "No",
            retries,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            error_message,
        ]
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def _finish(self, status: str, error_message: str) -> None:
        self._set(status=status, end_time=time.time(), error_message=error_message)
        s = self.state
        if status == STATUS_COMPLETED:
            log_manager.success(
                f"Campaign complete — {s.emails_sent} sent, {s.failed} failed "
                f"of {s.total}."
            )
        elif status == STATUS_CANCELLED:
            log_manager.warning(
                f"Campaign cancelled — {s.processed}/{s.total} processed."
            )
        elif status == STATUS_ERROR:
            log_manager.error(f"Campaign ended with an error: {error_message}")

    def _set(self, **kwargs) -> None:
        with self.state._lock:
            for key, value in kwargs.items():
                setattr(self.state, key, value)

    def _inc(self, **kwargs) -> None:
        with self.state._lock:
            for key, value in kwargs.items():
                setattr(self.state, key, getattr(self.state, key) + value)


# Process-level singleton shared across Streamlit re-runs.
campaign_runner = CampaignRunner()

"""
services/excel_reader.py
========================
Reads participant spreadsheets (.xlsx / .xls) and turns them into clean,
validated participant records using a user-chosen column mapping.

Extends the original ``load_participants`` logic so that column names are
no longer hardcoded and arbitrary extra fields (for email placeholders) can
be carried through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import pandas as pd

from core.utils import is_valid_email


@dataclass
class Participant:
    """A single validated participant row plus any extra mapped fields."""

    name: str
    email: str
    extras: Dict[str, str] = field(default_factory=dict)


@dataclass
class LoadResult:
    """Outcome of turning a dataframe into participant records."""

    participants: List[Participant]
    skipped_invalid: int
    skipped_missing: int

    @property
    def valid_count(self) -> int:
        return len(self.participants)

    @property
    def total_seen(self) -> int:
        return self.valid_count + self.skipped_invalid + self.skipped_missing


def load_dataframe(path: Path) -> pd.DataFrame:
    """
    Read an Excel file into a dataframe, choosing the correct engine based
    on the file extension. Supports both .xlsx and legacy .xls.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Spreadsheet not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".xls":
        engine = "xlrd"
    elif suffix in (".xlsx", ".xlsm"):
        engine = "openpyxl"
    else:
        # Best effort: let pandas infer.
        engine = None

    df = pd.read_excel(path, engine=engine)
    # Normalise column headers to strings and strip whitespace.
    df.columns = [str(c).strip() for c in df.columns]
    return df


def get_columns(df: pd.DataFrame) -> List[str]:
    """Return the list of column headers in a dataframe."""
    return [str(c) for c in df.columns]


def build_participants(
    df: pd.DataFrame,
    name_column: str,
    email_column: str,
    extra_fields: Dict[str, str] | None = None,
    certificate_id_column: str | None = None,
) -> LoadResult:
    """
    Turn a dataframe into validated Participant records.

    Args:
        df: the loaded spreadsheet.
        name_column: header holding the participant name.
        email_column: header holding the participant email.
        extra_fields: mapping of ``{{Placeholder}} -> column header`` for
            any additional dynamic fields to expose to the email template.
        certificate_id_column: optional column header containing certificate IDs.
            If provided, adds {{CertificateID}} to participant extras.

    Rules (preserved from the original project):
        - Fully empty rows are ignored.
        - Rows missing name or email are skipped.
        - Rows with an invalid email are skipped and counted.
    """
    extra_fields = extra_fields or {}

    if name_column not in df.columns:
        raise ValueError(f"Name column '{name_column}' not found in spreadsheet.")
    if email_column not in df.columns:
        raise ValueError(f"Email column '{email_column}' not found in spreadsheet.")

    df = df.dropna(how="all")

    participants: List[Participant] = []
    skipped_invalid = 0
    skipped_missing = 0

    for _, row in df.iterrows():
        raw_name = row.get(name_column)
        raw_email = row.get(email_column)

        name = "" if pd.isna(raw_name) else str(raw_name).strip()
        email = "" if pd.isna(raw_email) else str(raw_email).strip()

        if not name or not email:
            skipped_missing += 1
            continue

        if not is_valid_email(email):
            skipped_invalid += 1
            continue

        extras: Dict[str, str] = {}
        for placeholder, column in extra_fields.items():
            if column and column in df.columns:
                val = row.get(column)
                extras[placeholder] = "" if pd.isna(val) else str(val).strip()

        # Add certificate ID if column specified
        if certificate_id_column and certificate_id_column in df.columns:
            val = row.get(certificate_id_column)
            extras["{{CertificateID}}"] = "" if pd.isna(val) else str(val).strip()

        participants.append(Participant(name=name, email=email, extras=extras))

    return LoadResult(
        participants=participants,
        skipped_invalid=skipped_invalid,
        skipped_missing=skipped_missing,
    )

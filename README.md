# Certificate Studio

A professional Streamlit application for generating personalized certificates
and emailing them to participants — with **no code editing required**. It is a
refactor of the original command-line certificate mailer: all of the original
business logic (certificate rendering, Brevo delivery, retries, throttling,
dry-run mode, Excel loading, CSV logging) is preserved and reused, now wrapped
in a modern, modular UI.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

or simply:

```bash
./run.sh
```

Then open the URL Streamlit prints (usually http://localhost:8501).

> **Tip:** Leave **Dry run** enabled (Settings page) until you're ready. In dry
> run, certificates are generated for real but sends are simulated — perfect for
> previewing the whole workflow without a live API key.

## The workflow (no code required)

1. **Data & Template → Participants** — upload your `.xlsx`/`.xls`, choose how
   many rows to preview (5/10/20/50/100/All, or an exact custom count), and
   map the name/email columns (plus any extra placeholder fields).
2. **Data & Template → Certificate & Text** — upload a template (PNG, JPG, JPEG
   or PDF; non-PNG is converted automatically) and position the name with a
   live preview. Bold and italic use true font faces (DejaVu Serif/Sans ship
   with real bold, italic, and bold-italic variants) rather than a synthetic
   slant, so styling renders exactly as shown.
3. **Email Template** — edit each section of the email and watch the live
   preview. Use placeholders like `{{Name}}`, `{{Organization}}`,
   `{{CertificateName}}`, `{{Date}}`.
4. **Settings** — enter sender details and your Brevo API key; set delays,
   retries and campaign options.
5. **Presets** *(optional)* — save the whole setup for reuse, or load a saved one.
6. **Send & Monitor** — send immediately or schedule for later, then watch live
   progress, metrics and colour-coded logs. Download the results when done.
7. **Data & Template → Files & Media** *(optional)* — keep supporting material
   (event photos, a highlight video, briefing audio, extra spreadsheets,
   sponsor documents) alongside the campaign, browsable and downloadable by
   type.

## Getting a Brevo API key

1. Sign up / log in at [brevo.com](https://www.brevo.com).
2. Go to **Settings → SMTP & API → API Keys**, generate a key, and paste it into
   the app's **Settings** page.
3. Under **Senders & IP**, verify the sender email you plan to use — Brevo
   rejects sends from unverified senders.

## Project structure

```
app.py                      # Entry point + sidebar navigation
core/
    theme.py                # Design system (ink & brass) + UI components
    state.py                # Session bootstrapping + config accessors
    utils.py                # Email validation, filename/colour helpers
ui/
    dashboard.py            # Summary cards, progress, readiness checklist
    template_manager.py     # Excel import, column mapping, certificate + text editor, files
    email_editor.py         # Section-based email editor with live preview
    settings.py             # Sender, delay/retry, campaign, configuration
    presets_panel.py        # Preset create/duplicate/rename/delete/import/export
    scheduler.py            # Scheduler + start/cancel + live monitor
    logging_panel.py        # Live, searchable, colour-coded log panel
services/
    config_manager.py       # Default config schema, load/save, paths
    preset_manager.py       # Preset persistence & lifecycle
    excel_reader.py         # Spreadsheet loading + validated participants
    image_converter.py      # PNG/JPG/JPEG/PDF -> PNG normalisation
    certificate_generator.py# Name rendering + PDF export (+ live preview)
    email_sender.py         # Brevo API, template rendering, retries, dry run
    log_manager.py          # Thread-safe live log buffer
    campaign_runner.py      # Background worker, progress state, scheduling
assets/     fonts/          # Bundled + uploaded fonts, uploads, sample data
templates/                  # Certificate templates (uploaded/converted)
presets/                    # Saved presets (JSON)
generated_certificates/     # Output PDFs
logs/                       # Per-run CSV result logs
config/                     # config.json (auto-created, last-used settings)
```

## How settings are stored

Every setting is saved to `config/config.json` and loaded automatically on
startup, so your last session is always restored. A **preset** is a complete,
portable snapshot of that configuration (template reference, email template,
sender settings, text positions, delays, retries, column mapping, campaign
settings) that you can export to a file and share.

## Responsiveness & performance

- Sending runs on a **background thread**, so the UI stays usable during long
  campaigns; the monitor auto-refreshes once a second only while active.
- The certificate preview is **cached**, so adjusting position sliders stays
  snappy.
- Uploaded templates are **content-addressed**, so re-uploading the same file
  doesn't duplicate work.

## Notes on the original project

- The original CLI entry point (`main.py`) has been superseded by `app.py`, but
  the underlying logic lives on in `services/certificate_generator.py` and
  `services/email_sender.py` with the same rendering/retry/throttle behaviour.
- `.env` is **no longer required** — secrets live in the Settings page. The
  `.env.example` file is retained only for parity.

## Troubleshooting

- **"No participants loaded"** — upload an Excel file and click *Load
  participants* on the Data & Template page (or use the bundled sample).
- **Emails fail with 401/403 from Brevo** — the API key is invalid; regenerate
  it in the Brevo dashboard and update Settings.
- **Emails fail mentioning the sender** — verify the sender email in Brevo.
- **Rate-limit errors** — increase the delay between emails on the Settings page.
- **Name overflows the certificate** — raise *Max text width*, lower *Min font
  size*, or reposition on the Certificate & Text tab; the live preview shows the
  result immediately.

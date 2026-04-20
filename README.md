# Auberry Daily Review Report

This project fetches fresh Google reviews for Auberry The Bake Shop, analyzes them with Anthropic, generates a premium PDF report, and emails it automatically.

## Local run

1. Copy `.env.example` to `.env`
2. Fill in the required API keys and SMTP settings
3. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

4. Generate and send the report:

```bash
python3 send_report.py
```

## GitHub Actions schedule

The included workflow runs every day at `03:30 UTC`, which is `09:00 AM IST`.

## Required GitHub secrets

- `GOOGLE_PLACES_API_KEY`
- `ANTHROPIC_API_KEY`
- `AUBERRY_PLACE_ID`
- `AUBERRY_BRAND_NAME`
- `REPORT_RECIPIENT`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_FROM_NAME`

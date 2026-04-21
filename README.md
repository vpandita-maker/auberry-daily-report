# Auberry Daily Review Report

This project fetches fresh Google reviews for Auberry The Bake Shop, analyzes them with Anthropic, generates a static HTML dashboard, emails it automatically, and publishes the latest dashboard to GitHub Pages.

## Local run

1. Copy `.env.example` to `.env`
2. Fill in the required API keys and SMTP settings
3. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

4. Generate and send the reports:

```bash
python3 send_report.py
```

Build the hosted dashboard locally:

```bash
python3 publish_dashboard.py
```

## Outlet configuration

The project now supports multiple outlets through `outlets.json`. Each run loops through the configured branches, blends the reviews into one portfolio-wide analysis, generates a static HTML dashboard, and emails that combined brief.

Example format:

```json
[
  { "name": "Auberry The Bake Shop - Kondapur", "place_id": "..." },
  { "name": "Shared Google Listing", "source_url": "https://share.google/..." }
]
```

Each outlet must include `name` and either `place_id` or `source_url`. `source_url` works best with full Google Maps URLs that contain a resolvable place identifier.

## GitHub Actions schedule

The report workflow sends the email on the configured nightly schedule, and the dashboard deploy workflow publishes the latest site after successful report runs and on pushes to `main`.

## Required GitHub secrets

- `GOOGLE_PLACES_API_KEY`
- `ANTHROPIC_API_KEY`
- `REPORT_RECIPIENT`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_FROM_NAME`

Optional:

- `DASHBOARD_URL`

Optional legacy fallback values if `outlets.json` is missing:

- `AUBERRY_PLACE_ID`
- `AUBERRY_BRAND_NAME`

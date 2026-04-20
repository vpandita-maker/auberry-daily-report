import json
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from dotenv import load_dotenv

from analyzer.ai_analysis import analyze_reviews
from reports.pdf_generator import generate_pdf_report
from scrapers.google import get_google_reviews


load_dotenv()


OUTLETS_FILE = Path(os.getenv("AUBERRY_OUTLETS_FILE", "outlets.json"))
PLACE_ID = os.getenv("AUBERRY_PLACE_ID", "ChIJtVnlYUyTyzsRqFxHmIIV7Sc")
BRAND_NAME = os.getenv("AUBERRY_BRAND_NAME", "Auberry The Bake Shop - Kondapur")
REPORT_RECIPIENT = os.getenv("REPORT_RECIPIENT", "rahul.pandita.rp@gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Vansh Pandita")


def load_outlets():
    if OUTLETS_FILE.exists():
        with OUTLETS_FILE.open("r", encoding="utf-8") as config_file:
            outlets = json.load(config_file)
        if not isinstance(outlets, list) or not outlets:
            raise RuntimeError(f"{OUTLETS_FILE} must contain a non-empty list of outlets.")

        normalized = []
        for outlet in outlets:
            name = str(outlet.get("name", "")).strip()
            place_id = str(outlet.get("place_id", "")).strip()
            if not name or not place_id:
                raise RuntimeError(
                    f"Every outlet in {OUTLETS_FILE} must include non-empty 'name' and 'place_id' values."
                )
            normalized.append({"name": name, "place_id": place_id})
        return normalized

    return [{"name": BRAND_NAME, "place_id": PLACE_ID}]


def build_report(outlet):
    reviews = get_google_reviews(outlet["place_id"])
    if not reviews:
        raise RuntimeError("No reviews were fetched, so the report was not generated.")

    analysis = analyze_reviews(reviews, outlet["name"])
    pdf_path = generate_pdf_report(analysis)
    return Path(pdf_path), analysis


def send_email(report_results, failed_outlets):
    if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM:
        raise RuntimeError(
            "Missing SMTP credentials. Set SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM in .env."
        )

    subject = f"Daily Review Intelligence Report - Auberry ({len(report_results)} outlets)"
    body_lines = [
        "Hi,",
        "",
        "Attached are today's review intelligence reports for Auberry.",
        "",
        "Outlet snapshot:",
    ]

    for result in report_results:
        analysis = result["analysis"]
        body_lines.extend(
            [
                f"- {result['name']}: {analysis['overall_sentiment'].title()} | "
                f"{analysis['average_rating']:.1f}/5 | "
                f"{analysis['total_reviews_analyzed']} reviews | "
                f"Risk {analysis['rating_risk'].title()}",
                f"  Priority action: {analysis['week_priority_action']}",
            ]
        )

    if failed_outlets:
        body_lines.extend(
            [
                "",
                "Outlets skipped today:",
            ]
        )
        for failed in failed_outlets:
            body_lines.append(f"- {failed['name']}: {failed['error']}")

    body_lines.extend(
        [
            "",
            "Generated automatically by Vansh Pandita.",
            "",
        ]
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = REPORT_RECIPIENT
    message.set_content("\n".join(body_lines))

    for result in report_results:
        pdf_path = result["pdf_path"]
        with pdf_path.open("rb") as attachment:
            message.add_attachment(
                attachment.read(),
                maintype="application",
                subtype="pdf",
                filename=pdf_path.name,
            )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def main():
    report_results = []
    failed_outlets = []

    for outlet in load_outlets():
        try:
            pdf_path, analysis = build_report(outlet)
            report_results.append(
                {
                    "name": outlet["name"],
                    "pdf_path": pdf_path,
                    "analysis": analysis,
                }
            )
        except Exception as exc:
            failed_outlets.append({"name": outlet["name"], "error": str(exc)})
            print(f"Skipped {outlet['name']}: {exc}")

    if not report_results:
        raise RuntimeError("No outlet reports were generated successfully.")

    send_email(report_results, failed_outlets)
    print(f"Sent {len(report_results)} report(s) to {REPORT_RECIPIENT}")


if __name__ == "__main__":
    main()

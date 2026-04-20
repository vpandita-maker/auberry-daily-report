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


PLACE_ID = os.getenv("AUBERRY_PLACE_ID", "ChIJtVnlYUyTyzsRqFxHmIIV7Sc")
BRAND_NAME = os.getenv("AUBERRY_BRAND_NAME", "Auberry The Bake Shop - Kondapur")
REPORT_RECIPIENT = os.getenv("REPORT_RECIPIENT", "rahul.pandita.rp@gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Vansh Pandita")


def build_report():
    reviews = get_google_reviews(PLACE_ID)
    if not reviews:
        raise RuntimeError("No reviews were fetched, so the report was not generated.")

    analysis = analyze_reviews(reviews, BRAND_NAME)
    pdf_path = generate_pdf_report(analysis)
    return Path(pdf_path), analysis


def send_email(pdf_path, analysis):
    if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM:
        raise RuntimeError(
            "Missing SMTP credentials. Set SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM in .env."
        )

    subject = f"Daily Review Intelligence Report - {BRAND_NAME}"
    body = (
        f"Hi,\n\n"
        f"Attached is today's review intelligence report for {BRAND_NAME}.\n\n"
        f"Summary:\n"
        f"- Overall sentiment: {analysis['overall_sentiment'].title()}\n"
        f"- Average rating: {analysis['average_rating']:.1f}/5\n"
        f"- Reviews analyzed: {analysis['total_reviews_analyzed']}\n"
        f"- Rating risk: {analysis['rating_risk'].title()}\n\n"
        f"Priority action:\n"
        f"{analysis['week_priority_action']}\n\n"
        f"Generated automatically by Vansh Pandita.\n"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = REPORT_RECIPIENT
    message.set_content(body)

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
    pdf_path, analysis = build_report()
    send_email(pdf_path, analysis)
    print(f"Sent {pdf_path.name} to {REPORT_RECIPIENT}")


if __name__ == "__main__":
    main()

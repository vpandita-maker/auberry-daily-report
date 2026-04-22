import json
import os
import re
import shutil
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from dotenv import load_dotenv

from analyzer.ai_analysis import analyze_reviews
from reports.html_dashboard import generate_html_dashboard
from scrapers.google import extract_place_id_from_google_url, get_google_reviews


load_dotenv()

REPORT_WINDOW_DAYS = 1


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
RECIPIENT_NAME_OVERRIDE = os.getenv("RECIPIENT_NAME_OVERRIDE", "").strip()
DASHBOARD_URL = os.getenv(
    "DASHBOARD_URL",
    "https://vpandita-maker.github.io/auberry-daily-report/",
).strip()


def _split_display_name(display_name):
    parts = [part for part in str(display_name).strip().split() if part]
    if not parts:
        return {"first_name": "", "last_name": "", "full_name": ""}
    if len(parts) == 1:
        return {"first_name": parts[0], "last_name": "", "full_name": parts[0]}
    return {
        "first_name": parts[0],
        "last_name": parts[-1],
        "full_name": f"{parts[0]} {parts[-1]}",
    }


def _infer_person_name_from_email(email, override=""):
    if override.strip():
        return _split_display_name(override)

    local = email.split("@", 1)[0]
    cleaned = re.sub(r"\d+", " ", local)
    cleaned = re.sub(r"[._-]+", " ", cleaned).strip()
    normalized_cleaned = re.sub(r"[^a-z]", "", cleaned.lower())
    sender_local = SMTP_FROM.split("@", 1)[0] if SMTP_FROM else ""
    normalized_sender = re.sub(r"[^a-z]", "", sender_local.lower())

    if normalized_cleaned and normalized_cleaned == normalized_sender and SMTP_FROM_NAME.strip():
        return _split_display_name(SMTP_FROM_NAME)

    parts = [part.capitalize() for part in cleaned.split() if part]
    if not parts:
        return {"first_name": "there", "last_name": "", "full_name": "there"}
    if len(parts) == 1:
        return {"first_name": parts[0], "last_name": "", "full_name": parts[0]}
    return {
        "first_name": parts[0],
        "last_name": parts[-1],
        "full_name": f"{parts[0]} {parts[-1]}",
    }


def _recipient_name(email):
    return _infer_person_name_from_email(email, RECIPIENT_NAME_OVERRIDE)["first_name"]


def _sender_first_name():
    sender = SMTP_FROM_NAME.strip() or "Team"
    return sender.split()[0]


def _is_recent_review(review, cutoff_timestamp):
    timestamp = review.get("timestamp")
    if timestamp:
        return timestamp >= cutoff_timestamp

    relative = str(review.get("date", "")).strip().lower()
    recent_markers = (
        "today",
        "yesterday",
        "day ago",
        "days ago",
        "a week ago",
        "weeks ago",
        "a month ago",
        "month ago",
    )
    return any(marker in relative for marker in recent_markers)


def _is_review_from_today(review):
    timestamp = review.get("timestamp")
    if timestamp:
        review_dt = datetime.fromtimestamp(timestamp, UTC)
        now_dt = datetime.now(UTC)
        return review_dt.date() == now_dt.date()

    relative = str(review.get("date", "")).strip().lower()
    return relative == "today" or "hour ago" in relative or "hours ago" in relative


def _truncate_text(text, limit=360):
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _normalize_term(text):
    normalized = re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()
    replacements = {
        "doughnut": "donut",
        "doughnuts": "donuts",
        "choco": "chocolate",
    }
    words = [replacements.get(word, word) for word in normalized.split()]
    return " ".join(words)


def _singularize(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _item_aliases(item_name):
    normalized = _normalize_term(item_name)
    if not normalized:
        return set()

    aliases = {normalized}
    compact = normalized.replace("(", " ").replace(")", " ")
    aliases.add(compact)

    tokens = [token for token in compact.split() if token]
    singular_tokens = [_singularize(token) for token in tokens]
    plural_tokens = [token if token.endswith("s") else f"{token}s" for token in singular_tokens]

    aliases.add(" ".join(singular_tokens))
    aliases.add(" ".join(plural_tokens))

    for token in tokens + singular_tokens + plural_tokens:
        if len(token) >= 5:
            aliases.add(token)

    for separator in ("/", " or ", " and "):
        if separator in normalized:
            for part in normalized.split(separator):
                part = part.strip()
                if part:
                    aliases.add(part)

    return {alias.strip() for alias in aliases if alias.strip()}


def _review_mentions_item(review_text, item_name):
    review_slug = f" {_normalize_term(review_text)} "
    aliases = _item_aliases(item_name)
    if not aliases:
        return False

    for alias in sorted(aliases, key=len, reverse=True):
        if f" {alias} " in review_slug:
            return True
    return False


def _should_hide_failed_outlet(error_message):
    normalized = str(error_message).strip().lower()
    hidden_markers = (
        "no reviews were fetched",
        "missing a resolvable google place_id",
    )
    return any(marker in normalized for marker in hidden_markers)


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
            source_url = str(outlet.get("source_url", "")).strip()
            if not name or not (place_id or source_url):
                raise RuntimeError(
                    f"Every outlet in {OUTLETS_FILE} must include a non-empty 'name' plus either 'place_id' or 'source_url'."
                )
            normalized.append({"name": name, "place_id": place_id, "source_url": source_url})
        return normalized

    return [{"name": BRAND_NAME, "place_id": PLACE_ID}]


def build_combined_report(outlets):
    combined_reviews = []
    configured_outlet_count = len(outlets)
    participating_outlets = []
    failed_outlets = []
    visible_failed_outlets = []
    review_dates = []
    outlet_locations = []
    cutoff = datetime.now(UTC).timestamp() - (24 * 60 * 60)

    for outlet in outlets:
        try:
            place_id = outlet.get("place_id", "")
            if not place_id and outlet.get("source_url"):
                place_id = extract_place_id_from_google_url(outlet["source_url"])
            if not place_id:
                raise RuntimeError("Missing a resolvable Google place_id")

            reviews = get_google_reviews(place_id)
            if not reviews:
                raise RuntimeError("No reviews were fetched")

            outlet_address = reviews[0].get("outlet_address", "") if reviews else ""
            if outlet_address:
                outlet_locations.append(f"{outlet['name']}: {outlet_address}")

            for review in reviews:
                enriched = dict(review)
                if not _is_recent_review(enriched, cutoff):
                    continue
                outlet_name = outlet["name"]
                review_text = enriched.get("text", "").strip()
                location = enriched.get("outlet_address", "")
                review_date = enriched.get("date_exact") or enriched.get("date") or "Unknown"
                if enriched.get("date_exact"):
                    review_dates.append(enriched["date_exact"])
                enriched["source"] = f"Google - {outlet_name}"
                prefix = f"[Outlet: {outlet_name} | Location: {location} | Review date: {review_date}]"
                enriched["text"] = f"{prefix} {review_text}" if review_text else prefix
                combined_reviews.append(enriched)
            if any(review.get("source") == f"Google - {outlet_name}" for review in combined_reviews):
                participating_outlets.append(outlet["name"])
        except Exception as exc:
            failed = {"name": outlet["name"], "error": str(exc)}
            failed_outlets.append(failed)
            if not _should_hide_failed_outlet(failed["error"]):
                visible_failed_outlets.append(failed)
            print(f"Skipped {outlet['name']}: {exc}")

    if not combined_reviews:
        raise RuntimeError("No outlet reviews were fetched successfully.")

    analysis = analyze_reviews(combined_reviews, "Auberry The Bake Shop - All Outlets")
    analysis["brand_name"] = "Auberry The Bake Shop - All Outlets"
    analysis["configured_outlet_count"] = configured_outlet_count
    analysis["portfolio_outlets"] = participating_outlets
    analysis["portfolio_failed_outlets"] = visible_failed_outlets
    analysis["portfolio_locations"] = outlet_locations
    analysis["review_dates"] = sorted(set(review_dates))
    analysis["report_scope"] = "Today only"
    if analysis["review_dates"]:
        first_review = datetime.strptime(analysis["review_dates"][0], "%Y-%m-%d").strftime("%b %d, %Y")
        last_review = datetime.strptime(analysis["review_dates"][-1], "%Y-%m-%d").strftime("%b %d, %Y")
        analysis["review_window"] = f"{first_review} to {last_review}"
    else:
        analysis["review_window"] = "Dates unavailable"

    today_reviews = []
    for review in sorted(combined_reviews, key=lambda item: item.get("timestamp") or 0, reverse=True):
        source_label = str(review.get("source", "Google"))
        outlet_name = source_label.replace("Google - ", "", 1) if source_label.startswith("Google - ") else source_label
        today_reviews.append(
            {
                "outlet": outlet_name,
                "location": str(review.get("outlet_address", "")),
                "author": str(review.get("author", "") or "Anonymous"),
                "rating": review.get("rating"),
                "date_time": str(review.get("date_time_exact") or review.get("date_exact") or review.get("date") or "Unknown"),
                "text": _truncate_text(review.get("text", ""), 360),
                "source_url": str(review.get("source_url", "")),
                "author_url": str(review.get("author_url", "")),
            }
        )
    analysis["new_reviews_today"] = today_reviews

    mention_sources = {}
    for item in analysis.get("most_mentioned_items", []) or []:
        item_name = str(item.get("item", "")).strip()
        if not item_name:
            continue
        sources = []
        for review in today_reviews:
            if not _review_mentions_item(review.get("text", ""), item_name):
                continue
            sources.append(
                {
                    "outlet": review["outlet"],
                    "date_time": review["date_time"],
                    "source_url": review["source_url"],
                }
            )
            if len(sources) >= 3:
                break
        mention_sources[item_name] = sources
    analysis["mention_sources"] = mention_sources

    html_path = generate_html_dashboard(analysis)
    analysis["html_dashboard_path"] = str(Path(html_path).resolve())
    return Path(html_path), analysis, visible_failed_outlets


def publish_dashboard_site(html_path, site_dir="site"):
    site_path = Path(site_dir)
    site_path.mkdir(parents=True, exist_ok=True)

    index_path = site_path / "index.html"
    shutil.copyfile(html_path, index_path)
    (site_path / ".nojekyll").write_text("", encoding="utf-8")
    return index_path.resolve()


def send_email(html_path, analysis, failed_outlets, recipient=None):
    if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM:
        raise RuntimeError(
            "Missing SMTP credentials. Set SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM in .env."
        )

    target_recipient = recipient or REPORT_RECIPIENT
    contributing_outlet_count = len(analysis.get("portfolio_outlets", []))
    configured_outlet_count = int(analysis.get("configured_outlet_count", contributing_outlet_count) or contributing_outlet_count)
    subject = f"Daily Review Intelligence Report - Auberry ({configured_outlet_count} outlets tracked)"
    greeting_name = _recipient_name(target_recipient)
    top_issue = (analysis.get("top_3_urgent_issues") or ["service and food consistency issues"])[0]
    top_strength = (analysis.get("top_3_strengths") or ["strong dessert quality across key outlets"])[0]
    top_recommendation = (analysis.get("top_3_recommendations") or [{}])[0]
    recommendation_text = top_recommendation.get("title") or "a targeted corrective action plan"
    dashboard_url = DASHBOARD_URL or analysis.get("dashboard_url") or ""
    overview = (
        f"Auberry's daily review brief shows {analysis['overall_sentiment']} sentiment and a "
        f"{analysis['average_rating']:.1f}/5 average across {analysis['total_reviews_analyzed']} reviews. "
        f"Key themes include {top_issue.lower()} alongside strengths such as {top_strength.lower()}. "
        f"The report pinpoints outlet-specific issues, including Musarambagh and Kukatpally, and recommends {recommendation_text.lower()} "
        f"to reduce risk and stabilize guest experience across all {configured_outlet_count} tracked outlets."
    )
    body_lines = [
        f"Hi {greeting_name},",
        "",
        overview,
        "",
        "View live dashboard:",
        dashboard_url or "Dashboard URL unavailable",
        "",
        f"Outlet coverage: {contributing_outlet_count} of {configured_outlet_count} outlets contributed review data in this cycle.",
    ]

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
            "Best regards,",
            _sender_first_name(),
        ]
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = target_recipient
    message.set_content("\n".join(body_lines))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def main():
    html_path, analysis, failed_outlets = build_combined_report(load_outlets())
    test_recipient = os.getenv("REPORT_RECIPIENT_OVERRIDE", "").strip() or None
    send_email(html_path, analysis, failed_outlets, recipient=test_recipient)
    print(f"Sent combined report to {test_recipient or REPORT_RECIPIENT}")


if __name__ == "__main__":
    main()

from datetime import UTC, datetime
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


CATEGORY_ORDER = [
    ("food_quality", "Food Quality", "F"),
    ("service", "Service", "S"),
    ("ambiance", "Ambiance", "A"),
    ("value_for_money", "Value for Money", "V"),
    ("coffee_quality", "Coffee Quality", "C"),
]
IST = ZoneInfo("Asia/Kolkata")


def _safe_filename(text):
    return text.replace(" ", "_").replace("-", "").replace("/", "")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _outlet_aliases(outlet):
    base = _slug(outlet)
    aliases = {base}
    trimmed = base.replace("auberry the bake shop", "").replace("auberry", "").strip()
    if trimmed:
        aliases.add(trimmed)
    for token in trimmed.split():
        if len(token) > 3:
            aliases.add(token)
    return {alias for alias in aliases if alias}


def _display_outlet_name(outlet):
    text = str(outlet).strip()
    short = (
        text.replace("Auberry The Bake Shop -", "")
        .replace("Auberry The Bake Shop", "")
        .replace("AUBERRY -", "")
        .replace("AUBERRY", "")
        .strip(" -")
        .strip()
    )
    return short or text


def _format_display_date(value):
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    for fmt in ("%Y-%m-%d", "%b %d, %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%A, %d %B %Y")
        except ValueError:
            continue
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").astimezone(IST)
        return parsed.strftime("%A, %d %B %Y")
    except ValueError:
        return text


def _format_display_datetime(value):
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=UTC)
            if fmt == "%Y-%m-%d":
                return parsed.astimezone(IST).strftime("%d/%m/%y")
            return parsed.astimezone(IST).strftime("%d/%m/%y %I:%M %p IST")
        except ValueError:
            continue
    return text


def _format_review_window(value):
    text = str(value or "").strip()
    if " to " not in text:
        return _format_display_date(text)
    start, end = text.split(" to ", 1)
    return f"{_format_display_date(start)} to {_format_display_date(end)}"


def _text_mentions_outlet(text, outlet):
    haystack = _slug(text)
    return any(alias in haystack for alias in _outlet_aliases(outlet))


def _normalize_sentiment(value):
    text = _slug(value)
    if text in {"positive", "good", "strong"}:
        return "positive"
    if text in {"negative", "bad", "weak"}:
        return "negative"
    if text in {"neutral", "mixed"}:
        return "neutral"
    return "na"


def _metric_delta(value, positive_suffix, negative_suffix):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "Stable"
    if numeric > 0:
        return f"+{numeric:g} {positive_suffix}"
    if numeric < 0:
        return f"{numeric:g} {negative_suffix}"
    return "No change"


def _comparison_value(analysis, key, fallback=0):
    comparison = analysis.get("comparison") or {}
    value = comparison.get(key, fallback)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _extract_outlet_name(text, outlets):
    for outlet in outlets:
        if _text_mentions_outlet(text, outlet):
            return outlet
    return None


def _derive_item_panels(items):
    positive = [item for item in items if _normalize_sentiment(item.get("sentiment")) == "positive"]
    negative = [item for item in items if _normalize_sentiment(item.get("sentiment")) == "negative"]
    neutral = [item for item in items if _normalize_sentiment(item.get("sentiment")) == "neutral"]

    top_items = sorted(
        positive or items,
        key=lambda item: (
            0 if _normalize_sentiment(item.get("sentiment")) == "positive" else 1,
            -int(item.get("mentions", 0)),
            str(item.get("item", "")),
        ),
    )[:5]
    underperforming = sorted(negative + neutral, key=lambda item: (-int(item.get("mentions", 0)), str(item.get("item", ""))))[:5]
    return top_items, underperforming


def _build_heatmap(analysis):
    outlets = analysis.get("portfolio_outlets") or ["All Outlets"]
    categories = analysis.get("categories") or {}

    rows = []
    for outlet in outlets[:5]:
        row = {"outlet": outlet, "cells": []}
        for key, label, icon in CATEGORY_ORDER:
            info = categories.get(key) or {}
            summary_text = str(info.get("summary", ""))
            issues = info.get("top_issues") or []
            praises = info.get("top_praises") or []
            issues_text = " ".join(str(item) for item in issues)
            praises_text = " ".join(str(item) for item in praises)
            status = "na"
            reason = "No clear outlet-level signal yet"
            score = float(info.get("score", 0) or 0)
            outlet_issue = _text_mentions_outlet(issues_text, outlet)
            outlet_strength = _text_mentions_outlet(praises_text, outlet)
            outlet_summary = _text_mentions_outlet(summary_text, outlet)

            if outlet_issue:
                status = "negative"
                reason = issues[0] if issues else "Risk flagged in recent reviews"
            elif outlet_strength:
                status = "positive"
                reason = praises[0] if praises else "Positive feedback in recent reviews"
            elif outlet_summary:
                if score >= 4.1:
                    status = "positive"
                    reason = summary_text or "Strong portfolio performance"
                elif score >= 3.2:
                    status = "neutral"
                    reason = summary_text or "Mixed but manageable feedback"
                elif score > 0:
                    status = "negative"
                    reason = summary_text or "Under pressure in reviews"
            elif score >= 4.4 and key != "coffee_quality":
                status = "positive"
                reason = summary_text or "Strong portfolio-wide signal"
            elif score >= 3.5 and key != "coffee_quality":
                status = "neutral"
                reason = summary_text or "Mixed portfolio-wide signal"
            elif key == "coffee_quality" and score == 0:
                status = "na"
                reason = "Not enough direct feedback"

            row["cells"].append(
                {
                    "label": label,
                    "icon": icon,
                    "status": status,
                    "reason": str(reason),
                }
            )
        rows.append(row)
    return rows


def _render_item_rows(items, empty_label, tone):
    if not items:
        return f"<div class='empty-block'>{escape(empty_label)}</div>"

    rows = []
    for index, item in enumerate(items, start=1):
        name = str(item.get("item", "Unknown"))
        mentions = int(item.get("mentions", 0) or 0)
        sentiment = _normalize_sentiment(item.get("sentiment"))
        badge = sentiment if sentiment != "na" else tone
        rows.append(
            """
            <div class="list-row">
              <div class="item-rank">{rank}</div>
              <div class="item-thumb">{thumb}</div>
              <div class="item-copy">
                <div class="item-name">{name}</div>
                <div class="item-meta">{mentions} mention{plural}</div>
              </div>
              <span class="pill pill-{badge}">{badge_label}</span>
            </div>
            """.format(
                rank=index,
                thumb=escape(name[:1].upper()),
                name=escape(name),
                mentions=mentions,
                plural="" if mentions == 1 else "s",
                badge=escape(badge),
                badge_label=escape(badge.title()),
            )
        )
    return "".join(rows)


def _render_heatmap(rows):
    if not rows:
        return "<div class='empty-block'>No outlet heatmap available.</div>"

    header_cells = "".join(
        """
        <div class="heat-header-cell">
          <div class="heat-icon">{icon}</div>
          <div>{label}</div>
        </div>
        """.format(icon=escape(icon), label=escape(label))
        for _, label, icon in CATEGORY_ORDER
    )

    row_html = []
    for row in rows:
        cells = "".join(
            """
            <div class="heat-cell heat-{status}" title="{reason}">
              <span>{display}</span>
            </div>
            """.format(
                status=escape(cell["status"]),
                reason=escape(cell["reason"]),
                display="N/A" if cell["status"] == "na" else escape(cell["icon"]),
            )
            for cell in row["cells"]
        )
        row_html.append(
            """
            <div class="heat-row">
              <div class="heat-outlet">{outlet}</div>
              {cells}
            </div>
            """.format(outlet=escape(row["outlet"]), cells=cells)
        )

    return """
    <div class="heat-grid">
      <div class="heat-head">
        <div></div>
        {header_cells}
      </div>
      {rows}
    </div>
    """.format(header_cells=header_cells, rows="".join(row_html))


def _render_mentions_board(items, mention_sources=None):
    if not items:
        return "<div class='empty-block'>No item trends available.</div>"

    mention_sources = mention_sources or {}
    cards = []
    for index, item in enumerate(items[:8], start=1):
        mentions = int(item.get("mentions", 0) or 0)
        sentiment = _normalize_sentiment(item.get("sentiment"))
        item_name = str(item.get("item", "Unknown"))
        sources = mention_sources.get(item_name, [])[:3]
        source_html = ""
        if sources:
            links = []
            for source_index, source in enumerate(sources, start=1):
                outlet = escape(str(source.get("outlet", "Outlet")))
                location = escape(str(source.get("location", "")).strip())
                author = escape(str(source.get("author", "Anonymous")))
                rating = escape(str(source.get("rating", "N/A")))
                date_time = escape(_format_display_datetime(source.get("date_time", "Unknown time")))
                review_text = escape(str(source.get("text", "")).strip() or "Review text unavailable.")
                links.append(
                    """
                    <article class="mention-source-card">
                      <div class="mention-source-header">Source {index}: {outlet}</div>
                      <div class="mention-source-meta">Reviewer: {author} · Rating: {rating} · {date_time}</div>
                      <div class="mention-source-meta">{location}</div>
                      <p>{review_text}</p>
                    </article>
                    """.format(
                        index=source_index,
                        outlet=outlet,
                        author=author,
                        rating=rating,
                        date_time=date_time,
                        location=location,
                        review_text=review_text,
                    )
                )
            source_html = (
                "<details class='mention-sources'>"
                "<summary class='mention-sources-toggle'>View referenced reviews</summary>"
                "<div class='mention-sources-panel'>"
                "<div class='mention-sources-title'>Reviews mentioning this item</div>"
                f"{''.join(links)}"
                "</div>"
                "</details>"
            )
        cards.append(
            """
            <article class="mention-card mention-{sentiment}">
              <div class="mention-rank">{rank}</div>
              <div class="mention-body">
                <h4>{name}</h4>
                <div class="mention-meta">
                  <span>{mentions} mention{plural}</span>
                  <span class="pill pill-{sentiment}">{sentiment_label}</span>
                </div>
                {source_html}
              </div>
            </article>
            """.format(
                rank=index,
                name=escape(item_name),
                mentions=mentions,
                plural="" if mentions == 1 else "s",
                sentiment=escape(sentiment),
                sentiment_label=escape(sentiment.title() if sentiment != "na" else "N/A"),
                source_html=source_html,
            )
        )
    return "".join(cards)


def _render_alerts(analysis):
    issues = analysis.get("top_3_urgent_issues") or []
    failed_outlets = analysis.get("portfolio_failed_outlets") or []
    alerts = []
    no_issue_phrases = (
        "no urgent",
        "no negative",
        "no issues",
        "all 17 reviews are 5-star",
        "all reviews are 5-star",
    )

    for index, issue in enumerate(issues):
        normalized_issue = str(issue).strip().lower()
        is_positive_status = index == 0 and any(phrase in normalized_issue for phrase in no_issue_phrases)
        kicker = "Clear" if is_positive_status else "Urgent" if index == 0 else "Watchlist"
        impact = "impact-low" if is_positive_status else "impact-high" if index == 0 else "impact-medium"
        status = "Stable" if is_positive_status else "In Progress" if index == 0 else "Monitoring"
        alerts.append(
            """
            <div class="alert-card {tone}">
              <div class="alert-kicker">{kicker}</div>
              <h4>{title}</h4>
              <p>{body}</p>
              <div class="alert-meta">
                <span class="impact {impact}">{impact_label}</span>
                <span class="status-chip">{status}</span>
              </div>
            </div>
            """.format(
                tone="alert-clear" if is_positive_status else "alert-urgent" if index == 0 else "alert-warning",
                kicker=escape(kicker),
                title=escape(issue),
                body=escape(
                    "No immediate corrective action is required from the latest review cycle."
                    if is_positive_status
                    else "Highest-priority issue surfaced from the latest review cycle."
                    if index == 0
                    else "Keep this under observation in the next review cycle."
                ),
                impact=impact,
                impact_label="Low Risk" if is_positive_status else "High Impact" if index == 0 else "Medium Impact",
                status=escape(status),
            )
        )

    for failed in failed_outlets:
        alerts.append(
            """
            <div class="alert-card alert-warning">
              <div class="alert-kicker">Warning</div>
              <h4>{title}</h4>
              <p>{body}</p>
              <div class="alert-meta">
                <span class="impact impact-medium">Medium Impact</span>
                <span class="status-chip">Needs Review</span>
              </div>
            </div>
            """.format(
                title=escape(f"{failed['name']}: data unavailable"),
                body=escape(str(failed.get("error", "This outlet did not contribute fresh reviews today."))),
            )
        )

    return "".join(alerts) or "<div class='empty-block'>No urgent issues available.</div>"


def _render_recommendations(items):
    if not items:
        return "<div class='empty-block'>No recommendations available.</div>"

    cards = []
    for item in items[:6]:
        focus = str(item.get("location_focus", "Portfolio-wide"))
        metric = str(item.get("success_metric", "Set a measurable KPI before rollout"))
        next_steps = str(item.get("action", "Define owner, rollout steps, and follow-up review checkpoints."))
        timeline = str(item.get("timeline", "")).strip()
        if timeline and timeline.lower() not in next_steps.lower():
            next_steps = f"{next_steps} Timing: {timeline}."
        cards.append(
            """
            <article class="action-row">
              <div class="action-topline">
                <div class="action-icon">→</div>
                <div class="action-copy">
                  <div class="action-title">{title}</div>
                  <div class="action-meta">{focus}</div>
                </div>
              </div>
              <div class="action-metrics">
                <span class="action-chip metric-chip">
                  <strong>Target</strong>
                  <span>{metric}</span>
                </span>
              </div>
              <div class="action-strategy">
                <strong>Next Steps</strong>
                <p>{next_steps}</p>
              </div>
            </article>
            """.format(
                title=escape(str(item.get("title", "Untitled recommendation"))),
                focus=escape(focus),
                metric=escape(metric),
                next_steps=escape(next_steps),
            )
        )
    return "<div class='recommendations-grid'>{}</div>".format("".join(cards))


def _recommendation_key(item):
    return (
        str(item.get("title", "")).strip().lower(),
        str(item.get("location_focus", "")).strip().lower(),
    )


def _specific_recommendation_fallbacks(analysis):
    fallbacks = []
    issues = analysis.get("top_3_urgent_issues") or []
    strengths = analysis.get("top_3_strengths") or []
    items = analysis.get("most_mentioned_items") or []
    brand = str(analysis.get("brand_name", "Auberry The Bake Shop - All Outlets"))

    if any("coffee" in issue.lower() or "beverage" in issue.lower() for issue in issues):
        fallbacks.append(
            {
                "title": "Run Beverage Feedback Recovery Sprint",
                "location_focus": brand,
                "action": "Within 7 days, add one beverage upsell prompt at billing, offer a coffee sample during peak hours, and ask every beverage buyer for a QR review before exit.",
                "success_metric": "Collect at least 10 beverage-specific reviews and lift coffee mentions from 0 to 8+ within 14 days.",
            }
        )

    if any("appearance" in issue.lower() or "staff" in issue.lower() for issue in issues):
        fallbacks.append(
            {
                "title": "Correct Staff Conduct at Irrummanzil",
                "location_focus": "Auberry The Bake Shop - Irrummanzil",
                "action": "Within 48 hours, coach front-of-house staff on guest-facing language, prohibit personal comments, and have the manager review the next 20 interactions during peak hours.",
                "success_metric": "Reach 0 appearance-related complaints and 100% compliance on manager spot checks for the next 30 days.",
            }
        )

    donut_item = next((item for item in items if "donut" in str(item.get("item", "")).lower()), None)
    if donut_item:
        mentions = int(donut_item.get("mentions", 0) or 0)
        fallbacks.append(
            {
                "title": "Standardize Donut Hero Display",
                "location_focus": "Irrummanzil and Kukatpally first, then portfolio-wide",
                "action": "Within 10 days, create one front-counter donut display standard, add hero signage, and require staff to recommend the featured donut in every qualifying order.",
                "success_metric": f"Increase donut review mentions from {mentions} to at least {max(mentions + 3, 6)} per day and improve attach rate by 15% within 21 days.",
            }
        )

    if any("premchand" in strength.lower() or "arun" in strength.lower() for strength in strengths):
        fallbacks.append(
            {
                "title": "Turn Named Staff Praise into a Training Script",
                "location_focus": "Panjagutta and Kondapur as pilot outlets",
                "action": "Within 14 days, record the exact greeting, recommendation, and checkout behaviors that earned named praise and train every cashier and floor staff member on that sequence.",
                "success_metric": "Generate at least 5 named-staff mentions per week across the pilot outlets within 30 days.",
            }
        )

    if any("text" in issue.lower() or "detailed feedback" in issue.lower() for issue in issues):
        fallbacks.append(
            {
                "title": "Replace Generic QR Prompts with Guided Review Questions",
                "location_focus": "Auberry The Bake Shop - Kondapur",
                "action": "Within 5 days, update the review ask to request one food comment and one service comment, and have staff mention those prompts verbally at handoff.",
                "success_metric": "Cut text-less reviews below 10% and raise average review text length to 15+ words within 2 weeks.",
            }
        )

    top_item = items[0] if items else {}
    top_item_name = str(top_item.get("item", "")).strip()
    top_item_mentions = int(top_item.get("mentions", 0) or 0) if top_item else 0
    if top_item_name:
        fallbacks.append(
            {
                "title": f"Turn {top_item_name} Praise into a Counter Script",
                "location_focus": brand,
                "action": f"Within 7 days, give every cashier a one-line prompt for {top_item_name}: mention the exact item at checkout, point to the display, and ask buyers to name it in their Google review.",
                "success_metric": f"Lift {top_item_name} review mentions from {top_item_mentions} to at least {max(top_item_mentions + 4, 6)} in the next 14 days.",
            }
        )

    if any("coffee" not in issue.lower() and "beverage" not in issue.lower() for issue in issues) or not issues:
        fallbacks.append(
            {
                "title": "Add Beverage Attach Prompts to Donut Orders",
                "location_focus": "portfolio-wide",
                "action": "Within 10 days, require staff to offer one coffee or cold beverage pairing on every donut order and track whether the customer accepts, declines, or asks for a recommendation.",
                "success_metric": "Generate at least 8 beverage mentions and reach a 20% beverage attach rate on donut orders within 30 days.",
            }
        )

    fallbacks.append(
        {
            "title": "Create a Daily Outlet Review Quality Scorecard",
            "location_focus": "all participating outlets",
            "action": "Starting tomorrow, have each outlet manager log review count, named item mentions, named staff mentions, and text-less reviews before closing, then share the lowest-scoring outlet in the morning huddle.",
            "success_metric": "Reach at least 3 text reviews per outlet per day and reduce text-less reviews below 15% within 21 days.",
        }
    )

    return fallbacks


def _normalize_recommendations(analysis):
    existing = list(
        analysis.get("top_6_recommendations")
        or analysis.get("top_5_recommendations")
        or analysis.get("top_3_recommendations")
        or []
    )
    seen = {_recommendation_key(item) for item in existing}

    for item in _specific_recommendation_fallbacks(analysis):
        key = _recommendation_key(item)
        if key in seen:
            continue
        existing.append(item)
        seen.add(key)
        if len(existing) >= 6:
            break

    return existing[:6]


def _render_review_references(items):
    if not items:
        return "<div class='empty-block'>No new reviews were captured today.</div>"

    avatar_palette = [
        ("#7c3aed", "#ede9fe"),
        ("#0369a1", "#e0f2fe"),
        ("#047857", "#d1fae5"),
        ("#b45309", "#fef3c7"),
        ("#be185d", "#fce7f3"),
        ("#1d4ed8", "#dbeafe"),
    ]

    def _stars(rating):
        try:
            r = float(rating)
        except (TypeError, ValueError):
            return '<span class="rv-stars rv-stars-none">&#x2605;&#x2605;&#x2605;&#x2605;&#x2605;</span>'
        full = int(r)
        half = 1 if (r - full) >= 0.5 else 0
        empty = 5 - full - half
        return (
            '<span class="rv-stars">'
            + '&#x2605;' * full
            + ('&#x2BE8;' if half else '')
            + '<span class="rv-star-empty">' + '&#x2605;' * empty + '</span>'
            + '</span>'
        )

    cards = []
    for i, item in enumerate(items):
        rating = item.get("rating")
        try:
            rating_num = float(rating)
            rating_label = f"{rating_num:.1f}"
            if rating_num >= 4.5:
                rating_cls = "rv-rating-high"
            elif rating_num >= 3.5:
                rating_cls = "rv-rating-mid"
            else:
                rating_cls = "rv-rating-low"
        except (TypeError, ValueError):
            rating_label = "—"
            rating_cls = "rv-rating-mid"

        author_raw = str(item.get("author", "Anonymous")).strip() or "Anonymous"
        author = escape(author_raw)
        initial = author_raw[0].upper() if author_raw else "?"
        bg, fg = avatar_palette[i % len(avatar_palette)]

        author_url = str(item.get("author_url", "")).strip()
        author_link = (
            f'<a href="{escape(author_url)}" target="_blank" rel="noopener noreferrer" class="rv-name">{author}</a>'
            if author_url else f'<span class="rv-name">{author}</span>'
        )

        source_url = str(item.get("source_url", "")).strip()
        source_link = (
            f'<a href="{escape(source_url)}" target="_blank" rel="noopener noreferrer" class="rv-source-link">View on Google ↗</a>'
            if source_url else ""
        )

        outlet_short = escape(_display_outlet_name(str(item.get("outlet", "Unknown outlet"))))
        date_fmt = escape(_format_display_datetime(item.get("date_time", "")))
        text = escape(str(item.get("text", "")).strip())

        cards.append(
            """
            <article class="review-card">
              <div class="rv-header">
                <div class="rv-avatar" style="background:{bg};color:{fg}">{initial}</div>
                <div class="rv-author-block">
                  {author_link}
                  <div class="rv-date">{date_fmt}</div>
                </div>
                <div class="rv-rating-pill {rating_cls}">{rating_label}</div>
              </div>
              <div class="rv-stars-row">{stars}</div>
              <p class="rv-text">{text}</p>
              <div class="rv-footer">
                <span class="rv-outlet-tag">{outlet_short}</span>
                {source_link}
              </div>
            </article>
            """.format(
                bg=bg, fg=fg, initial=initial,
                author_link=author_link,
                date_fmt=date_fmt,
                rating_label=rating_label,
                rating_cls=rating_cls,
                stars=_stars(rating),
                text=text,
                outlet_short=outlet_short,
                source_link=source_link,
            )
        )
    return "<div class='review-grid'>{}</div>".format("".join(cards))


def _render_complaint_spikes(spikes):
    if not spikes:
        return "<div class='empty-block'>No complaint velocity spikes detected for this cycle.</div>"

    cards = []
    for spike in spikes[:6]:
        severity = str(spike.get("severity", "medium")).lower()
        cards.append(
            """
            <article class="insight-card insight-{severity}">
              <div class="insight-kicker">{severity_label} Spike</div>
              <h4>{category}</h4>
              <p>{outlet} recorded {today_count} negative mention{plural}, versus a {baseline_avg} seven-day baseline.</p>
              <div class="insight-meta">
                <span>{spike_percent}% vs baseline</span>
                <span>{trend}</span>
              </div>
            </article>
            """.format(
                severity=escape(severity),
                severity_label=escape(severity.title()),
                category=escape(str(spike.get("category", "general")).replace("_", " ").title()),
                outlet=escape(str(spike.get("outlet_id", "Unknown outlet"))),
                today_count=int(spike.get("today_count", 0) or 0),
                plural="" if int(spike.get("today_count", 0) or 0) == 1 else "s",
                baseline_avg=escape(str(spike.get("baseline_avg", 0))),
                spike_percent=escape(str(spike.get("spike_percent", 0))),
                trend=escape(str(spike.get("trend", "stable")).title()),
            )
        )
    return "<div class='insight-grid'>{}</div>".format("".join(cards))


def _render_outlet_ranking(outlet_ranking):
    ranked = (outlet_ranking or {}).get("ranked_outlets") or []
    summary = (outlet_ranking or {}).get("summary") or {}
    if not ranked:
        return "<div class='empty-block'>No outlet ranking available for this cycle.</div>"

    rows = []
    for outlet in ranked:
        status = str(outlet.get("status", "middle")).lower()
        confidence = "Low confidence" if outlet.get("low_confidence") else "Normal confidence"
        rows.append(
            """
            <div class="ranking-row ranking-{status}">
              <div class="ranking-rank">#{rank}</div>
              <div class="ranking-main">
                <div class="ranking-outlet">{outlet}</div>
                <div class="ranking-meta">{reviews} review{plural} · {confidence}</div>
              </div>
              <div class="ranking-score">
                <strong>{score}</strong>
                <span>{rating}★ · {positive_ratio}% positive</span>
              </div>
            </div>
            """.format(
                status=escape(status),
                rank=int(outlet.get("rank", 0) or 0),
                outlet=escape(str(outlet.get("outlet_id", "Unknown outlet"))),
                reviews=int(outlet.get("review_count", 0) or 0),
                plural="" if int(outlet.get("review_count", 0) or 0) == 1 else "s",
                confidence=escape(confidence),
                score=escape(str(outlet.get("score", 0))),
                rating=escape(str(outlet.get("avg_rating", 0))),
                positive_ratio=round(float(outlet.get("positive_ratio", 0) or 0) * 100),
            )
        )

    summary_html = """
    <div class="gap-summary">
      <div><span>Best</span><strong>{best}</strong></div>
      <div><span>Worst</span><strong>{worst}</strong></div>
      <div class="gap-num-cell"><span>Rating Gap</span><strong class="gap-num">{rating_gap}★</strong></div>
      <div class="gap-num-cell"><span>Score Gap</span><strong class="gap-num">{score_gap}</strong></div>
    </div>
    """.format(
        best=escape(str(summary.get("best_outlet") or "N/A")),
        worst=escape(str(summary.get("worst_outlet") or "N/A")),
        rating_gap=escape(str(summary.get("rating_gap", 0))),
        score_gap=escape(str(summary.get("score_gap", 0))),
    )
    return summary_html + "<div class='ranking-list'>{}</div>".format("".join(rows))


def _render_competitor_section(competitor_benchmarks, auberry_avg_rating):
    if not competitor_benchmarks:
        return ""
    snapshots = competitor_benchmarks.get("snapshots") or []
    gap = competitor_benchmarks.get("gap_analysis") or {}
    if not snapshots or not gap:
        return ""

    summary = escape(str(gap.get("summary", "")))
    strategic = escape(str(gap.get("strategic_implication", "")))

    auberry_advantages = gap.get("auberry_advantages") or []
    competitor_advantages = gap.get("competitor_advantages") or []

    advantage_items = "".join(
        f"<li>{escape(str(item))}</li>" for item in auberry_advantages[:4]
    )
    gap_items = "".join(
        f"<li>{escape(str(item))}</li>" for item in competitor_advantages[:4]
    )

    snapshot_cards = []
    for snap in snapshots:
        avg = float(snap.get("avg_rating", 0) or 0)
        sentiment = int(snap.get("sentiment_pct", 0) or 0)
        count = int(snap.get("review_count", 0) or 0)
        outlet_count = int(snap.get("outlet_count", 1) or 1)
        rating_color = "#67dd69" if avg >= auberry_avg_rating else "#ef6464"
        outlet_label = f"{outlet_count} outlet{'s' if outlet_count != 1 else ''} · " if outlet_count > 1 else ""
        snapshot_cards.append(
            """
            <div class="comp-card">
              <div class="comp-name">{name}</div>
              <div class="comp-rating" style="color:{color};">{avg}</div>
              <div class="comp-meta">{outlet_label}{sentiment}% positive · {count} reviews sampled</div>
            </div>
            """.format(
                name=escape(str(snap.get("name", "Competitor"))),
                color=rating_color,
                avg=f"{avg:.1f}",
                outlet_label=outlet_label,
                sentiment=sentiment,
                count=count,
            )
        )

    category_comparison = gap.get("category_comparison") or {}
    category_labels = {
        "food_quality": "Food Quality",
        "service": "Service",
        "value_for_money": "Value for Money",
        "coffee_quality": "Coffee Quality",
    }
    comparison_rows = []
    for key, label in category_labels.items():
        data = category_comparison.get(key) or {}
        auberry_score = float(data.get("auberry_score", 0) or 0)
        comp_avg = float(data.get("competitor_avg", 0) or 0)
        gap_value = str(data.get("gap", "tied")).lower()
        note = escape(str(data.get("note", "")))
        gap_pill_class = "pill-positive" if gap_value == "ahead" else "pill-negative" if gap_value == "behind" else "pill-neutral"
        gap_label = gap_value.title()
        comparison_rows.append(
            """
            <div class="comp-compare-row">
              <div class="comp-compare-label">{label}</div>
              <div class="comp-compare-scores">
                <span class="comp-score-auberry">{auberry_score:.1f}</span>
                <span class="comp-score-sep">vs</span>
                <span class="comp-score-comp">{comp_avg:.1f}</span>
                <span class="pill {pill_class}">{gap_label}</span>
              </div>
              <div class="comp-compare-note">{note}</div>
            </div>
            """.format(
                label=escape(label),
                auberry_score=auberry_score,
                comp_avg=comp_avg,
                pill_class=gap_pill_class,
                gap_label=gap_label,
                note=note,
            )
        )

    return """
    <section class="card competitor-panel" id="competitor-benchmarking">
      <h3 class="panel-title">Competitor Benchmarking</h3>
      <p class="panel-subtitle">{summary}</p>
      <div class="comp-snapshot-row">
        <div class="comp-card comp-card-auberry">
          <div class="comp-name">Auberry (You)</div>
          <div class="comp-rating" style="color:#67dd69;">{auberry_avg:.1f}</div>
          <div class="comp-meta">Your current avg rating</div>
        </div>
        {snapshot_cards}
      </div>
      <div class="comp-body">
        <div class="comp-category-block">
          <h4>Category Comparison</h4>
          <div class="comp-compare-grid">{comparison_rows}</div>
        </div>
        <div class="comp-gaps-block">
          <div class="comp-gap-col">
            <div class="comp-gap-title comp-gap-positive">Where Auberry Leads</div>
            <ul class="comp-gap-list">{advantage_items}</ul>
          </div>
          <div class="comp-gap-col">
            <div class="comp-gap-title comp-gap-negative">Where Competitors Lead</div>
            <ul class="comp-gap-list">{gap_items}</ul>
          </div>
        </div>
      </div>
      <div class="comp-strategic">{strategic}</div>
    </section>
    """.format(
        summary=summary,
        auberry_avg=auberry_avg_rating,
        snapshot_cards="".join(snapshot_cards),
        comparison_rows="".join(comparison_rows),
        advantage_items=advantage_items or "<li>No clear advantages identified yet.</li>",
        gap_items=gap_items or "<li>No competitive gaps identified yet.</li>",
        strategic=strategic,
    )


def _render_root_cause_patterns(patterns):
    if not patterns:
        return "<div class='empty-block'>No repeating root-cause pattern detected yet.</div>"

    cards = []
    for pattern in patterns[:5]:
        severity = str(pattern.get("severity", "medium")).lower()
        cards.append(
            """
            <article class="pattern-card pattern-{severity}">
              <div class="pattern-type">{pattern_type}</div>
              <p>{message}</p>
              <span>{count} signal{plural}</span>
            </article>
            """.format(
                severity=escape(severity),
                pattern_type=escape(str(pattern.get("pattern_type", "pattern")).replace("_", " ").title()),
                message=escape(str(pattern.get("message", "Pattern detected."))),
                count=int(pattern.get("count", 0) or 0),
                plural="" if int(pattern.get("count", 0) or 0) == 1 else "s",
            )
        )
    return "<div class='pattern-grid'>{}</div>".format("".join(cards))


def generate_html_dashboard(analysis, output_dir="output", trend_data=None):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    brand = str(analysis.get("brand_name", "Restaurant Report"))
    date_str = datetime.now().strftime("%b %d, %Y")
    safe_name = _safe_filename(brand)
    filename = output_path / f"{safe_name}_Dashboard_{datetime.now().strftime('%Y%m%d')}.html"

    categories = analysis.get("categories") or {}
    items = analysis.get("most_mentioned_items") or []
    recommendations = _normalize_recommendations(analysis)
    review_references = analysis.get("new_reviews_today") or []
    mention_sources = analysis.get("mention_sources") or {}
    outlets = analysis.get("portfolio_outlets") or []
    top_items, underperforming = _derive_item_panels(items)
    heatmap_rows = _build_heatmap(analysis)
    complaint_spikes = analysis.get("complaint_spikes") or []
    outlet_ranking = analysis.get("outlet_ranking") or {}
    root_cause_patterns = analysis.get("root_cause_patterns") or []
    competitor_benchmarks = analysis.get("competitor_benchmarks") or {}

    avg_rating = float(analysis.get("average_rating", 0) or 0)
    trend_data_json = json.dumps(trend_data or [])
    competitor_section_html = _render_competitor_section(competitor_benchmarks, avg_rating)
    previous_avg_rating = _comparison_value(analysis, "average_rating", avg_rating)
    positive_categories = sum(
        1 for info in categories.values() if float((info or {}).get("score", 0) or 0) >= 4.0
    )
    sentiment_pct = 0
    if categories:
        sentiment_pct = round((positive_categories / len(categories)) * 100)
    previous_sentiment_pct = _comparison_value(analysis, "sentiment_pct", sentiment_pct)
    total_reviews = int(analysis.get("total_reviews_analyzed", 0) or 0)
    previous_total_reviews = int(_comparison_value(analysis, "total_reviews", total_reviews))

    review_window = _format_review_window(analysis.get("review_window", "Dates unavailable"))
    report_scope = str(analysis.get("report_scope", "Today only"))
    risk_level = str(analysis.get("rating_risk", "Unknown")).title()
    risk_tone = "low" if risk_level.lower() == "low" else "medium" if risk_level.lower() == "medium" else "high"

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{brand} Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #171b31;
      --panel: #232941;
      --panel-2: #2a314c;
      --border: #343c5a;
      --text: #f3f4ff;
      --muted: #b2b8d1;
      --green: #63d85f;
      --green-bg: #4caf5030;
      --yellow: #f1bc2e;
      --yellow-bg: #f1bc2e2e;
      --red: #ef6464;
      --red-bg: #ef646428;
      --purple: #ab7df4;
      --purple-bg: #ab7df426;
      --blue: #6fa7ff;
      --chip: #1e2439;
      --shadow: 0 20px 40px rgba(7, 10, 22, 0.32);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(171,125,244,0.12), transparent 22%),
        radial-gradient(circle at top right, rgba(99,216,95,0.10), transparent 18%),
        linear-gradient(180deg, #161a30 0%, #13182c 100%);
      color: var(--text);
      font-family: 'Inter', Arial, Helvetica, sans-serif;
      animation: page-fade 700ms cubic-bezier(.22,1,.36,1);
    }}
    .page {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 24px;
    }}
    .dashboard {{
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 24px;
      align-items: stretch;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(40,47,74,0.98), rgba(33,39,63,0.98));
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      transition:
        transform 220ms cubic-bezier(.22,1,.36,1),
        box-shadow 220ms cubic-bezier(.22,1,.36,1),
        border-color 220ms ease,
        background 220ms ease,
        filter 220ms ease;
    }}
    .card:hover {{
      transform: translateY(-6px);
      box-shadow: 0 28px 54px rgba(7, 10, 22, 0.42);
      border-color: rgba(171,125,244,0.32);
    }}
    .topbar {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      padding: 10px 8px 4px;
    }}
    .brand-block {{
      display: flex;
      gap: 0;
      align-items: center;
    }}
    .brand-copy h1 {{
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: -0.02em;
      font-weight: 800;
      font-family: 'Inter', Arial, Helvetica, sans-serif;
      color: var(--text);
    }}
    .brand-copy .brand-sub {{
      margin: 3px 0 0;
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .filters {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .filter-text {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      line-height: 1.5;
      white-space: nowrap;
    }}
    .filter-text strong {{
      color: var(--text);
      font-weight: 700;
      letter-spacing: 0;
      text-transform: none;
      font-size: 13px;
    }}
    .kpis {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }}
    .intelligence-panel {{
      grid-column: 1 / -1;
      padding: 24px;
    }}
    .intelligence-grid {{
      display: grid;
      grid-template-columns: minmax(0, 8fr) minmax(320px, 4fr);
      gap: 16px;
      margin-top: 16px;
      align-items: stretch;
    }}
    .intelligence-section {{
      background: rgba(20, 25, 43, 0.52);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      padding: 16px;
      min-width: 0;
      min-height: 100%;
    }}
    .ranking-section {{
      background: linear-gradient(180deg, rgba(35,42,68,0.82), rgba(24,30,52,0.72));
    }}
    .signal-stack {{
      display: grid;
      grid-template-rows: repeat(2, minmax(0, 1fr));
      gap: 16px;
      height: 100%;
      min-height: 100%;
    }}
    .signal-section {{
      display: flex;
      flex-direction: column;
      min-height: 0;
    }}
    .intelligence-section h4 {{
      margin: 0 0 10px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--muted);
      line-height: 1.35;
    }}
    .insight-grid,
    .pattern-grid,
    .ranking-list {{
      display: grid;
      gap: 10px;
    }}
    .insight-card,
    .pattern-card,
    .ranking-row {{
      border-radius: 12px;
      background: rgba(255,255,255,0.045);
      border: 1px solid rgba(255,255,255,0.08);
      padding: 12px;
    }}
    .insight-card h4 {{
      margin: 4px 0 6px;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--text);
    }}
    .insight-card p,
    .pattern-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .insight-kicker,
    .pattern-type {{
      color: var(--yellow);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .insight-meta {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}
    .insight-meta span,
    .pattern-card span {{
      color: var(--text);
      background: var(--chip);
      border-radius: 999px;
      padding: 5px 8px;
      font-size: 12px;
      display: inline-flex;
      margin-top: 10px;
    }}
    .gap-summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .gap-summary div {{
      background: rgba(255,255,255,0.045);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      padding: 10px 12px;
    }}
    .gap-summary span,
    .ranking-meta,
    .ranking-score span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .gap-summary strong {{
      display: block;
      margin-top: 4px;
      font-size: 13px;
      color: var(--text);
      overflow-wrap: anywhere;
    }}
    .gap-num {{
      font-size: 26px;
      font-weight: 900;
      letter-spacing: -0.02em;
      color: var(--text);
    }}
    .ranking-row {{
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr) 124px;
      gap: 12px;
      align-items: center;
      min-height: 66px;
    }}
    .ranking-rank {{
      width: 34px;
      height: 34px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      background: var(--purple-bg);
      color: var(--text);
      font-weight: 800;
    }}
    .ranking-outlet {{
      font-size: 13px;
      font-weight: 800;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .ranking-score {{
      text-align: right;
      min-width: 112px;
    }}
    .ranking-score strong {{
      display: block;
      font-size: 18px;
    }}
    .ranking-top .ranking-rank {{
      background: var(--green-bg);
      color: var(--green);
    }}
    .ranking-underperforming .ranking-rank {{
      background: var(--red-bg);
      color: var(--red);
    }}
    .kpi-card {{
      padding: 18px 18px 14px;
      display: grid;
      grid-template-columns: 60px 1fr 110px;
      gap: 14px;
      align-items: center;
    }}
    .kpi-icon {{
      width: 56px;
      height: 56px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      font-size: 26px;
      font-weight: 800;
    }}
    .kpi-icon.gold {{ background: #7d6a3638; color: #ffcb47; }}
    .kpi-icon.green {{ background: #39644d45; color: #66e26c; }}
    .kpi-icon.red {{ background: #6a434943; color: #ff7474; }}
    .kpi-icon.purple {{ background: #51427345; color: #c094ff; }}
    .kpi-title {{ color: var(--muted); font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }}
    .kpi-value {{ font-size: 30px; font-weight: 900; margin-top: 6px; letter-spacing: -0.02em; }}
    .kpi-sub {{ color: var(--muted); margin-top: 6px; font-size: 12px; font-weight: 500; }}
    .kpi-sub.positive {{ color: var(--green); }}
    .kpi-sub.negative {{ color: var(--red); }}
    .sparkline {{
      align-self: stretch;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 60px;
    }}
    .sparkline canvas {{ width: 100% !important; height: 60px !important; }}
    .items-row,
    .signals-row {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 24px;
      align-items: stretch;
    }}
    .items-row .list-panel {{
      grid-column: span 4;
    }}
    .items-row .bubbles-panel {{
      grid-column: span 8;
    }}
    .signals-row .heatmap-panel {{
      grid-column: span 8;
    }}
    .signals-row .side-panel {{
      grid-column: span 4;
    }}
    .panel-title {{
      margin: 0;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .panel-subtitle {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 400;
      letter-spacing: 0;
    }}
    .panel-header {{
      padding: 0;
    }}
    .list-panel {{
      padding: 24px;
      min-height: 100%;
    }}
    .list-body {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      padding: 16px 0 0;
      min-width: 0;
    }}
    .list-row {{
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      min-height: 118px;
      padding: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      background: rgba(255,255,255,0.04);
      transition:
        transform 180ms cubic-bezier(.22,1,.36,1),
        background 180ms ease,
        border-color 180ms ease;
    }}
    .list-row:hover {{
      transform: translateY(-4px);
      background: rgba(255,255,255,0.035);
      border-color: rgba(255,255,255,0.12);
    }}
    .item-copy {{
      min-width: 0;
    }}
    .item-rank {{
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: rgba(255,255,255,0.08);
      color: #eef1ff;
      display: grid;
      place-items: center;
      font-weight: 800;
    }}
    .item-thumb {{ display: none; }}
    .item-name {{
      font-weight: 700;
      line-height: 1.25;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .item-meta {{ color: var(--muted); font-size: 13px; margin-top: 2px; }}
    .list-row .pill {{
      grid-column: 2 / -1;
      width: max-content;
      margin-top: 6px;
    }}
    .pill {{
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }}
    .pill-positive {{ background: var(--green-bg); color: var(--green); }}
    .pill-negative {{ background: var(--red-bg); color: var(--red); }}
    .pill-neutral {{ background: var(--yellow-bg); color: var(--yellow); }}
    .pill-na {{ background: rgba(170,177,204,0.18); color: #c3c8db; }}
    .list-footer {{
      padding: 12px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .heatmap-panel {{
      padding: 24px;
      min-height: 100%;
    }}
    .legend {{
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 13px;
      margin-top: 10px;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .legend i {{
      width: 14px;
      height: 14px;
      border-radius: 4px;
      display: inline-block;
    }}
    .heat-grid {{
      margin-top: 22px;
      display: grid;
      gap: 10px;
      overflow-x: auto;
    }}
    .heat-head, .heat-row {{
      display: grid;
      grid-template-columns: minmax(150px, 1.35fr) repeat(5, minmax(68px, 1fr));
      gap: 8px;
      align-items: stretch;
    }}
    .heat-header-cell {{
      text-align: center;
      color: #d8dcef;
      font-size: 14px;
      font-weight: 700;
      display: grid;
      gap: 6px;
      justify-items: center;
    }}
    .heat-icon {{
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: rgba(255,255,255,0.06);
      display: grid;
      place-items: center;
    }}
    .heat-outlet {{
      display: flex;
      align-items: center;
      padding: 0 10px;
      font-weight: 700;
      line-height: 1.25;
      overflow-wrap: anywhere;
      word-break: break-word;
      font-size: 16px;
    }}
    .heat-cell {{
      min-height: 58px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-size: 18px;
      font-weight: 800;
      letter-spacing: 0.02em;
      border: 1px solid rgba(255,255,255,0.05);
      transition:
        transform 180ms cubic-bezier(.22,1,.36,1),
        filter 180ms ease,
        box-shadow 180ms ease;
    }}
    .heat-cell:hover {{
      transform: translateY(-4px);
      filter: brightness(1.04);
      box-shadow: 0 14px 22px rgba(7, 10, 22, 0.2);
    }}
    .heat-positive {{ background: #58b958; color: white; }}
    .heat-neutral {{ background: #dba923; color: white; }}
    .heat-negative {{ background: #e85f68; color: white; }}
    .heat-na {{ background: #5a637d; color: #eef2ff; }}
    .bubbles-panel {{
      padding: 24px;
      min-height: 100%;
    }}
    .bubble-wrap {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 14px;
      padding-top: 14px;
      align-content: start;
      align-items: start;
    }}
    .mention-card {{
      position: relative;
      z-index: 0;
      border-radius: 16px;
      padding: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr);
      gap: 10px;
      align-items: start;
      align-self: start;
      min-height: 150px;
      transition:
        transform 180ms cubic-bezier(.22,1,.36,1),
        border-color 180ms ease,
        box-shadow 180ms ease,
        filter 180ms ease;
    }}
    .mention-card:hover {{
      z-index: 2;
      transform: translateY(-5px);
      border-color: rgba(255,255,255,0.16);
      box-shadow: 0 18px 28px rgba(6, 9, 21, 0.24);
      filter: brightness(1.03);
    }}
    .mention-card:has(.mention-sources[open]) {{
      z-index: 60;
      transform: none;
      filter: none;
    }}
    .mention-card:has(.mention-sources[open]):hover {{
      transform: none;
      filter: none;
    }}
    .mention-positive {{ background: linear-gradient(180deg, rgba(76,170,75,0.22), rgba(65,137,63,0.18)); }}
    .mention-neutral {{ background: linear-gradient(180deg, rgba(219,169,35,0.20), rgba(145,113,35,0.16)); }}
    .mention-negative {{ background: linear-gradient(180deg, rgba(232,95,104,0.20), rgba(140,58,72,0.16)); }}
    .mention-na {{ background: rgba(255,255,255,0.045); }}
    .mention-rank {{
      width: 34px;
      height: 34px;
      border-radius: 10px;
      background: rgba(255,255,255,0.08);
      display: grid;
      place-items: center;
      font-weight: 800;
    }}
    .mention-body {{
      min-width: 0;
    }}
    .mention-body h4 {{
      margin: 0;
      font-size: 17px;
      line-height: 1.18;
      overflow-wrap: anywhere;
      word-break: normal;
      hyphens: auto;
    }}
    .mention-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    .mention-sources {{
      position: relative;
      grid-column: 1 / -1;
      margin-top: 12px;
      border-radius: 14px;
      border: 1px solid rgba(111,167,255,0.18);
      background: rgba(23, 27, 49, 0.78);
      overflow: visible;
      z-index: 1;
    }}
    .mention-sources[open] {{
      z-index: 30;
    }}
    .mention-sources-toggle {{
      list-style: none;
      cursor: pointer;
      padding: 10px 12px;
      color: #b9d6ff;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.45;
      user-select: none;
    }}
    .mention-sources-toggle::-webkit-details-marker {{
      display: none;
    }}
    .mention-sources-toggle::after {{
      content: " +";
      float: right;
      color: rgba(255,255,255,0.7);
    }}
    .mention-sources[open] .mention-sources-toggle::after {{
      content: " -";
    }}
    .mention-sources-panel {{
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      width: 100%;
      min-width: 260px;
      display: grid;
      gap: 10px;
      max-height: 300px;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding: 12px;
      border: 1px solid rgba(111,167,255,0.22);
      border-radius: 14px;
      background: #151a30;
      box-shadow: 0 28px 64px rgba(5, 8, 18, 0.68);
      animation: mention-slide-down 220ms cubic-bezier(.22,1,.36,1);
    }}
    .mention-sources-panel::-webkit-scrollbar {{
      width: 8px;
    }}
    .mention-sources-panel::-webkit-scrollbar-thumb {{
      background: rgba(185,214,255,0.22);
      border-radius: 999px;
    }}
    .mention-sources-title {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(255,255,255,0.68);
      margin-bottom: 2px;
    }}
    .mention-source-card {{
      display: grid;
      gap: 6px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
    }}
    .mention-source-header {{
      font-size: 13px;
      font-weight: 700;
      color: #f0f4ff;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .mention-source-meta {{
      font-size: 12px;
      line-height: 1.45;
      color: rgba(255,255,255,0.72);
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .mention-source-meta:nth-child(3) {{
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .mention-source-card p {{
      margin: 0;
      font-size: 13px;
      line-height: 1.6;
      color: #f7f8ff;
      overflow-wrap: anywhere;
      word-break: break-word;
      display: -webkit-box;
      -webkit-line-clamp: 5;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .side-panel {{
      padding: 24px;
      min-height: 100%;
    }}
    .side-panel.danger h3 {{ color: #ff6d6d; }}
    .alert-card {{
      margin-top: 14px;
      border-radius: 16px;
      padding: 14px 14px 12px;
      border: 1px solid transparent;
      transition:
        transform 180ms cubic-bezier(.22,1,.36,1),
        box-shadow 180ms ease,
        border-color 180ms ease,
        filter 180ms ease;
    }}
    .alert-card:hover {{
      transform: translateY(-5px);
      box-shadow: 0 18px 30px rgba(8, 11, 26, 0.22);
      filter: brightness(1.03);
    }}
    .alert-urgent {{ background: #3b2633; border-color: #8a3c56; }}
    .alert-warning {{ background: #3a3423; border-color: #8d7235; }}
    .alert-info {{ background: #2e2942; border-color: #715ca6; }}
    .alert-clear {{ background: rgba(66, 118, 80, 0.22); border-color: rgba(99,216,95,0.42); }}
    .alert-kicker {{
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .alert-card h4 {{ margin: 0; font-size: 16px; }}
    .alert-card p {{
      color: var(--muted);
      line-height: 1.45;
      font-size: 14px;
      margin: 8px 0 0;
    }}
    .alert-meta {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .impact, .status-chip {{
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid rgba(255,255,255,0.08);
    }}
    .impact-high {{ background: var(--red-bg); color: var(--red); }}
    .impact-medium {{ background: var(--yellow-bg); color: var(--yellow); }}
    .impact-low {{ background: var(--green-bg); color: var(--green); }}
    .status-chip {{ background: rgba(255,255,255,0.04); color: #e9ecfb; }}
    .recommendations-panel {{
      grid-column: 1 / -1;
      padding: 20px;
      height: max-content;
    }}
    .recommendations-panel .panel-title {{
      color: #bc93ff;
    }}
    .recommendations-panel .panel-subtitle {{
      margin-top: 6px;
      max-width: 820px;
      line-height: 1.5;
    }}
    .recommendations-grid {{
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      min-width: 0;
    }}
    .reviews-panel {{
      grid-column: 1 / -1;
      padding: 20px;
      height: max-content;
    }}
    .reviews-panel .panel-title {{
      color: #8fc5ff;
    }}
    .review-grid {{
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .review-card {{
      border-radius: 18px;
      padding: 18px 20px 16px;
      border: 1px solid rgba(111,167,255,0.14);
      background: linear-gradient(160deg, rgba(40,50,82,0.98), rgba(32,40,66,0.98));
      display: flex;
      flex-direction: column;
      gap: 12px;
      transition: transform 200ms cubic-bezier(.22,1,.36,1), box-shadow 200ms ease, border-color 200ms ease;
    }}
    .review-card:hover {{
      transform: translateY(-4px);
      box-shadow: 0 18px 36px rgba(7,10,22,0.38);
      border-color: rgba(111,167,255,0.28);
    }}
    .rv-header {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .rv-avatar {{
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-size: 17px;
      font-weight: 800;
      flex-shrink: 0;
      letter-spacing: -0.01em;
    }}
    .rv-author-block {{
      flex: 1;
      min-width: 0;
    }}
    .rv-name {{
      display: block;
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
      text-decoration: none;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .rv-name:hover {{ text-decoration: underline; }}
    .rv-date {{
      font-size: 11px;
      color: var(--muted);
      margin-top: 1px;
      font-weight: 500;
    }}
    .rv-rating-pill {{
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 800;
      white-space: nowrap;
      flex-shrink: 0;
      letter-spacing: -0.01em;
    }}
    .rv-rating-high {{ background: rgba(99,216,95,0.16); color: #63d85f; border: 1px solid rgba(99,216,95,0.22); }}
    .rv-rating-mid  {{ background: rgba(241,188,46,0.16); color: #f1bc2e; border: 1px solid rgba(241,188,46,0.22); }}
    .rv-rating-low  {{ background: rgba(239,100,100,0.16); color: #ef6464; border: 1px solid rgba(239,100,100,0.22); }}
    .rv-stars-row {{ line-height: 1; margin-top: -4px; }}
    .rv-stars {{ font-size: 16px; color: #f1bc2e; letter-spacing: 1px; }}
    .rv-stars-none {{ color: #4a5070; }}
    .rv-star-empty {{ color: #3a4060; }}
    .rv-text {{
      margin: 0;
      color: #e8eaf8;
      font-size: 13px;
      line-height: 1.65;
      overflow-wrap: anywhere;
      word-break: break-word;
      flex: 1;
    }}
    .rv-footer {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-top: 2px;
    }}
    .rv-outlet-tag {{
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(171,125,244,0.14);
      border: 1px solid rgba(171,125,244,0.2);
      color: #c094ff;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 60%;
    }}
    .rv-source-link {{
      font-size: 11px;
      font-weight: 600;
      color: #8fc5ff;
      text-decoration: none;
      white-space: nowrap;
    }}
    .rv-source-link:hover {{ text-decoration: underline; }}
    .action-row {{
      display: grid;
      gap: 14px;
      align-content: start;
      padding: 18px;
      min-height: 100%;
      border-radius: 18px;
      border: 1px solid rgba(171,125,244,0.16);
      background: linear-gradient(180deg, rgba(57,62,97,0.95), rgba(44,48,78,0.95));
      color: inherit;
      transition:
        transform 200ms cubic-bezier(.22,1,.36,1),
        filter 200ms ease,
        border-color 200ms ease,
        box-shadow 200ms ease,
        background 200ms ease;
    }}
    .action-topline {{
      display: grid;
      grid-template-columns: 28px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      min-width: 0;
    }}
    .action-icon {{
      width: 28px;
      height: 28px;
      border-radius: 8px;
      background: rgba(171,125,244,0.18);
      color: #caafff;
      display: grid;
      place-items: center;
      font-weight: 800;
    }}
    .action-copy {{
      min-width: 0;
    }}
    .action-title {{
      font-weight: 700;
      font-size: 17px;
      line-height: 1.3;
    }}
    .action-title, .action-meta {{
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .action-meta {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 6px;
      line-height: 1.45;
    }}
    .action-metrics {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }}
    .action-chip {{
      display: grid;
      gap: 4px;
      padding: 14px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
      min-width: 0;
      align-content: start;
    }}
    .action-chip strong {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(255,255,255,0.68);
    }}
    .action-chip span {{
      overflow-wrap: anywhere;
      word-break: break-word;
      color: #f7f8ff;
      font-size: 13px;
      line-height: 1.4;
    }}
    .metric-chip {{
      background: linear-gradient(180deg, rgba(111,167,255,0.14), rgba(111,167,255,0.06));
      border-color: rgba(111,167,255,0.18);
    }}
    .action-row:hover {{
      filter: brightness(1.05);
      transform: translateY(-4px);
      border-color: rgba(255,255,255,0.12);
      box-shadow: 0 22px 34px rgba(9, 11, 28, 0.24);
    }}
    .action-strategy {{
      display: grid;
      gap: 8px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.025));
    }}
    .action-strategy strong {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(255,255,255,0.68);
    }}
    .action-strategy p {{
      margin: 0;
      color: #f7f8ff;
      font-size: 14px;
      line-height: 1.55;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .competitor-panel {{
      grid-column: 1 / -1;
      padding: 24px;
    }}
    .comp-snapshot-row {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin: 16px 0;
    }}
    .comp-card {{
      background: rgba(255,255,255,0.045);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 14px;
      padding: 16px 20px;
      min-width: 150px;
      flex: 1;
      max-width: 220px;
    }}
    .comp-card-auberry {{
      border-color: rgba(103,221,105,0.30);
      background: rgba(103,221,105,0.07);
    }}
    .comp-name {{
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
      margin-bottom: 6px;
      overflow-wrap: anywhere;
    }}
    .comp-rating {{
      font-size: 32px;
      font-weight: 800;
      line-height: 1;
    }}
    .comp-meta {{
      font-size: 12px;
      color: var(--muted);
      margin-top: 6px;
    }}
    .comp-body {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 20px;
      margin-top: 4px;
    }}
    .comp-category-block h4 {{
      margin: 0 0 12px;
      font-size: 14px;
      color: var(--text);
    }}
    .comp-compare-grid {{
      display: grid;
      gap: 10px;
    }}
    .comp-compare-row {{
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 10px 14px;
    }}
    .comp-compare-label {{
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 6px;
    }}
    .comp-compare-scores {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .comp-score-auberry {{
      font-size: 18px;
      font-weight: 800;
      color: var(--green);
    }}
    .comp-score-sep {{
      font-size: 12px;
      color: var(--muted);
    }}
    .comp-score-comp {{
      font-size: 18px;
      font-weight: 800;
      color: var(--text);
    }}
    .comp-compare-note {{
      font-size: 12px;
      color: var(--muted);
      margin-top: 6px;
      line-height: 1.4;
    }}
    .comp-gaps-block {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }}
    .comp-gap-col {{
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      padding: 14px 16px;
    }}
    .comp-gap-title {{
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 10px;
    }}
    .comp-gap-positive {{ color: var(--green); }}
    .comp-gap-negative {{ color: var(--red); }}
    .comp-gap-list {{
      margin: 0;
      padding: 0 0 0 16px;
      display: grid;
      gap: 8px;
    }}
    .comp-gap-list li {{
      font-size: 13px;
      color: var(--text);
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .comp-strategic {{
      margin-top: 16px;
      padding: 14px 18px;
      border-radius: 14px;
      background: rgba(171,125,244,0.08);
      border: 1px solid rgba(171,125,244,0.18);
      font-size: 14px;
      line-height: 1.6;
      color: #e8e2ff;
    }}
    @media (max-width: 980px) {{
      .comp-body {{
        grid-template-columns: 1fr;
      }}
      .comp-gaps-block {{
        grid-template-columns: 1fr;
      }}
    }}
    .empty-block {{
      color: var(--muted);
      padding: 18px 0 6px;
    }}
    .list-body .empty-block,
    .bubble-wrap .empty-block {{
      grid-column: 1 / -1;
      min-height: 118px;
      display: flex;
      align-items: center;
      padding: 16px;
      border-radius: 14px;
      border: 1px dashed rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.035);
    }}
    .intelligence-section .empty-block {{
      min-height: 86px;
      flex: 1;
      display: flex;
      align-items: center;
      padding: 14px;
      border-radius: 12px;
      border: 1px dashed rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.035);
      font-size: 14px;
      line-height: 1.45;
    }}
    .footer-note {{
      grid-column: 1 / -1;
      text-align: center;
      color: #d9ddf2;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.4;
      padding: 6px 4px 8px;
      animation: footer-slide-in 900ms cubic-bezier(.22,1,.36,1) 120ms both;
    }}
    @media (max-width: 1360px) {{
      .recommendations-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .review-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .intelligence-grid {{
        grid-template-columns: 1fr;
      }}
      .signals-row .heatmap-panel,
      .signals-row .side-panel {{
        grid-column: 1 / -1;
      }}
    }}
    @media (max-width: 1120px) {{
      .dashboard {{
        gap: 20px;
      }}
      .items-row .list-panel,
      .items-row .bubbles-panel {{
        grid-column: 1 / -1;
      }}
    }}
    @media (max-width: 980px) {{
      .kpis {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .kpi-card {{
        grid-template-columns: 56px 1fr;
      }}
      .sparkline {{
        display: none;
      }}
      .heat-head, .heat-row {{
        grid-template-columns: minmax(170px, 1.2fr) repeat(5, minmax(58px, 0.8fr));
      }}
      .filters {{
        justify-content: flex-start;
      }}
      .recommendations-grid {{
        grid-template-columns: 1fr;
      }}
      .review-grid {{
        grid-template-columns: 1fr;
      }}
      .gap-summary {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 720px) {{
      .page {{
        padding: 14px;
      }}
      .kpis {{
        grid-template-columns: 1fr;
      }}
      .topbar {{
        grid-template-columns: 1fr;
      }}
      .filter-text {{
        white-space: normal;
      }}
      .list-row {{
        grid-template-columns: 36px minmax(0, 1fr);
      }}
      .list-row .pill {{
        grid-column: 2 / -1;
        justify-self: start;
      }}
      .items-row,
      .signals-row {{
        gap: 16px;
      }}
      .heat-header-cell {{
        font-size: 11px;
      }}
      .heat-cell {{
        min-height: 46px;
        font-size: 13px;
      }}
      .heat-outlet {{
        font-size: 13px;
      }}
      .bubble-wrap {{
        grid-template-columns: 1fr;
      }}
      .mention-sources-panel {{
        position: static;
        width: auto;
        min-width: 0;
        max-height: 240px;
        margin-top: 0;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
        padding: 0 12px 12px;
      }}
      .action-metrics {{
        grid-template-columns: 1fr;
      }}
      .action-row {{
        padding: 16px;
      }}
      .ranking-row {{
        grid-template-columns: 38px minmax(0, 1fr);
      }}
      .ranking-score {{
        grid-column: 2 / -1;
        text-align: left;
      }}
      .gap-summary {{
        grid-template-columns: 1fr;
      }}
    }}
    @keyframes page-fade {{
      from {{
        opacity: 0;
        transform: translateY(18px);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    @keyframes footer-slide-in {{
      from {{
        opacity: 0;
        transform: translateX(-18px);
      }}
      to {{
        opacity: 1;
        transform: translateX(0);
      }}
    }}
    @keyframes mention-slide-down {{
      from {{
        opacity: 0;
        transform: translateY(-8px);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    .dp-overlay {{
      position: fixed;
      top: 14px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 9999;
    }}
    .dp-wrap {{
      position: relative;
      display: inline-flex;
    }}
    .dp-btn {{
      background: var(--panel-2);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      font-family: Arial, Helvetica, sans-serif;
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
      box-shadow: 0 4px 16px rgba(7,10,22,0.4);
      transition: border-color 180ms, background 180ms;
    }}
    .dp-btn:hover {{
      border-color: var(--purple);
      background: var(--panel);
    }}
    .dp-btn strong {{
      color: var(--text);
      font-weight: 600;
    }}
    .dp-chevron {{
      color: var(--muted);
      font-size: 10px;
    }}
    .dp-menu {{
      display: none;
      position: absolute;
      left: 50%;
      transform: translateX(-50%);
      top: calc(100% + 8px);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      box-shadow: 0 20px 50px rgba(7,10,22,0.6);
      min-width: 240px;
      max-height: 320px;
      overflow-y: auto;
      z-index: 100;
      animation: mention-slide-down 180ms cubic-bezier(.22,1,.36,1);
    }}
    .dp-menu.open {{
      display: block;
    }}
    .dp-option {{
      padding: 11px 18px;
      cursor: pointer;
      font-size: 13px;
      color: var(--text);
      transition: background 150ms;
      border-bottom: 1px solid var(--border);
    }}
    .dp-option:last-child {{
      border-bottom: none;
    }}
    .dp-option:hover {{
      background: var(--panel-2);
    }}
    .dp-option.active {{
      color: var(--purple);
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="dashboard">
      <div class="topbar">
        <div class="brand-block">
          <div class="brand-copy">
            <h1>{brand}</h1>
            <div class="brand-sub">Executive Intelligence Dashboard</div>
          </div>
        </div>
        <div class="filters">
          <div class="filter-text"><strong>Scope:</strong> All Outlets</div>
          <div class="filter-text"><strong>Window:</strong> {review_window}</div>
        </div>
      </div>

      <section class="kpis">
        <article class="card kpi-card">
          <div class="kpi-icon gold">★</div>
          <div>
            <div class="kpi-title">Overall Rating</div>
            <div class="kpi-value">{avg_rating:.1f} <span style="font-size:18px;font-weight:600;">/ 5</span></div>
            <div class="kpi-sub positive">↑ {rating_delta}</div>
          </div>
          <div class="sparkline"><canvas id="chart-rating"></canvas></div>
        </article>
        <article class="card kpi-card">
          <div class="kpi-icon green">☺</div>
          <div>
            <div class="kpi-title">Positive Sentiment</div>
            <div class="kpi-value">{sentiment_pct}%</div>
            <div class="kpi-sub positive">↑ {sentiment_delta}</div>
          </div>
          <div class="sparkline"><canvas id="chart-sentiment"></canvas></div>
        </article>
        <article class="card kpi-card">
          <div class="kpi-icon red">⛨</div>
          <div>
            <div class="kpi-title">Risk Level</div>
            <div class="kpi-value" style="color:{risk_color};">{risk_level}</div>
            <div class="kpi-sub">{report_scope}</div>
          </div>
          <div class="sparkline"><canvas id="chart-risk"></canvas></div>
        </article>
        <article class="card kpi-card">
          <div class="kpi-icon purple">◔</div>
          <div>
            <div class="kpi-title">Total Reviews</div>
            <div class="kpi-value">{total_reviews}</div>
            <div class="kpi-sub positive">↑ {review_delta}</div>
          </div>
          <div class="sparkline"><canvas id="chart-reviews"></canvas></div>
        </article>
      </section>

      <section class="card intelligence-panel" id="operational-intelligence">
        <h3 class="panel-title">Operational Intelligence</h3>
        <div class="panel-subtitle">Deterministic signals from review volume, outlet performance, and root-cause patterns.</div>
        <div class="intelligence-grid">
          <div class="intelligence-section ranking-section">
            <h4>Outlet Performance Ranking</h4>
            {outlet_ranking_html}
          </div>
          <div class="signal-stack">
            <div class="intelligence-section signal-section">
              <h4>Complaint Velocity Spikes</h4>
              {complaint_spikes_html}
            </div>
            <div class="intelligence-section signal-section">
              <h4>Root Cause Patterns</h4>
              {root_cause_patterns_html}
            </div>
          </div>
        </div>
      </section>

      <div class="items-row">
        <section class="card list-panel" id="underperforming-items">
          <div class="panel-header">
            <h3 class="panel-title">Underperforming Items</h3>
            <div class="panel-subtitle">By Mentions</div>
          </div>
          <div class="list-body">{underperforming_html}</div>
          <div class="list-footer">Most-mentioned risk items from the latest review cycle.</div>
        </section>

        <section class="card bubbles-panel" id="items-overview">
          <h3 class="panel-title">Most Mentioned Items <span style="color:var(--muted);font-weight:600;">({outlet_scope})</span></h3>
          <div class="legend">
            <span><i style="background:#58b958;"></i> Positive</span>
            <span><i style="background:#dba923;"></i> Neutral</span>
            <span><i style="background:#e85f68;"></i> Negative</span>
          </div>
          <div class="bubble-wrap">{mentions_board_html}</div>
        </section>
      </div>

      <div class="signals-row">
        <section class="card heatmap-panel" id="outlet-heatmap">
          <h3 class="panel-title">Outlet Sentiment Heatmap</h3>
          <div class="legend">
            <span><i style="background:#58b958;"></i> Positive</span>
            <span><i style="background:#dba923;"></i> Neutral</span>
            <span><i style="background:#e85f68;"></i> Negative</span>
            <span><i style="background:#5a637d;"></i> N/A</span>
          </div>
          {heatmap_html}
        </section>

        <section class="card side-panel danger">
          <h3 class="panel-title">Urgent &amp; Important</h3>
          {alerts_html}
        </section>
      </div>

      {competitor_section_html}

      <section class="card recommendations-panel" id="recommendations">
        <h3 class="panel-title">Top 6 Recommendations</h3>
        <div class="panel-subtitle">Specific action plans with measurable targets and timing included in the next-step strategy.</div>
        {recommendations_html}
      </section>

      <section class="card reviews-panel" id="review-references">
        <h3 class="panel-title">New Reviews Today</h3>
        <div class="panel-subtitle">Exact review references used in today’s dashboard, including outlet, location, timestamp, and source link.</div>
        {review_references_html}
      </section>

      <div class="footer-note">{brand}</div>
    </section>
  </main>
  <div class="dp-overlay">
    <div class="dp-wrap" id="dpWrap">
      <button class="dp-btn" id="dpBtn">&#128197;&nbsp;<strong><span id="dpLabel">&#8230;</span></strong><span class="dp-chevron">&#9662;</span></button>
      <div class="dp-menu" id="dpMenu"></div>
    </div>
  </div>
  <script>
  (function() {{
    var td = {trend_data_json};
    if (td && td.length >= 2) {{
      var lbl = td.map(function(d) {{
        var p = d.date.split('-');
        return new Date(+p[0], +p[1]-1, +p[2]).toLocaleDateString('en-IN', {{day:'numeric', month:'short'}});
      }});
      var cfg = {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{display: false}},
          tooltip: {{callbacks: {{title: function(i) {{ return lbl[i[0].dataIndex]; }}}}}}
        }},
        scales: {{x: {{display: false}}, y: {{display: false}}}},
        elements: {{line: {{tension: 0.4, borderWidth: 2}}, point: {{radius: 3, hoverRadius: 5}}}}
      }};
      function mc(id, data, color, bg) {{
        var c = document.getElementById(id);
        if (!c) return;
        new Chart(c, {{type:'line', data:{{labels:lbl, datasets:[{{data:data, borderColor:color, backgroundColor:bg, fill:true, pointBackgroundColor:color}}]}}, options:cfg}});
      }}
      mc('chart-rating',   td.map(function(d){{return d.avg_rating;}}),    '#63d85f', 'rgba(99,216,95,0.15)');
      mc('chart-sentiment',td.map(function(d){{return d.sentiment_pct;}}), '#63d85f', 'rgba(99,216,95,0.15)');
      mc('chart-risk',     td.map(function(d){{return d.risk_score;}}),     '#ef6464', 'rgba(239,100,100,0.15)');
      mc('chart-reviews',  td.map(function(d){{return d.total_reviews;}}),  '#ab7df4', 'rgba(171,125,244,0.15)');
    }}
  }})();
  (function() {{
    var isArchive = /\/archive\//.test(window.location.pathname);
    var base = isArchive ? '../' : './';
    var activeDate = null;
    if (isArchive) {{
      var m = window.location.pathname.match(/(\d{{4}}-\d{{2}}-\d{{2}})\.html/);
      if (m) activeDate = m[1];
    }}
    function fmt(d) {{
      var p = d.split('-');
      var dt = new Date(+p[0], +p[1]-1, +p[2]);
      return dt.toLocaleDateString('en-IN', {{weekday:'short', day:'numeric', month:'short', year:'numeric'}});
    }}
    document.getElementById('dpBtn').addEventListener('click', function(e) {{
      e.stopPropagation();
      document.getElementById('dpMenu').classList.toggle('open');
    }});
    document.addEventListener('click', function(e) {{
      var w = document.getElementById('dpWrap');
      if (w && !w.contains(e.target)) document.getElementById('dpMenu').classList.remove('open');
    }});
    fetch(base + 'dates.json')
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        var dates = data.dates || [];
        var lbl = document.getElementById('dpLabel');
        var menu = document.getElementById('dpMenu');
        if (!dates.length) {{ lbl.textContent = 'No history'; return; }}
        var active = activeDate || dates[0];
        lbl.textContent = fmt(active);
        dates.forEach(function(d, i) {{
          var el = document.createElement('div');
          el.className = 'dp-option' + (d === active ? ' active' : '');
          el.textContent = fmt(d) + (i === 0 ? ' — Latest' : '');
          el.addEventListener('click', function() {{
            window.location.href = i === 0 ? base + 'index.html' : base + 'archive/' + d + '.html';
          }});
          menu.appendChild(el);
        }});
      }})
      .catch(function() {{ document.getElementById('dpLabel').textContent = 'Select date'; }});
  }})();
  </script>
</body>
</html>
""".format(
        brand=escape(brand),
        review_window=escape(review_window),
        avg_rating=avg_rating,
        rating_delta=escape(_metric_delta(round(avg_rating - previous_avg_rating, 1), "vs yesterday", "vs yesterday")),
        sentiment_pct=sentiment_pct,
        sentiment_delta=escape(_metric_delta(sentiment_pct - previous_sentiment_pct, "vs yesterday", "vs yesterday")),
        risk_level=escape(risk_level),
        risk_color={"low": "#69dd74", "medium": "#f1bc2e", "high": "#ef6464"}.get(risk_tone, "#d9ddf2"),
        report_scope=escape(report_scope),
        total_reviews=escape(str(total_reviews)),
        review_delta=escape(_metric_delta(total_reviews - previous_total_reviews, "vs yesterday", "vs yesterday")),
        top_items_html=_render_item_rows(top_items, "No top items available yet.", "positive"),
        underperforming_html=_render_item_rows(
            underperforming,
            "No underperforming items flagged yet.",
            "negative",
        ),
        heatmap_html=_render_heatmap(heatmap_rows),
        mentions_board_html=_render_mentions_board(items, mention_sources),
        alerts_html=_render_alerts(analysis),
        complaint_spikes_html=_render_complaint_spikes(complaint_spikes),
        outlet_ranking_html=_render_outlet_ranking(outlet_ranking),
        root_cause_patterns_html=_render_root_cause_patterns(root_cause_patterns),
        competitor_section_html=competitor_section_html,
        recommendations_html=_render_recommendations(recommendations),
        review_references_html=_render_review_references(review_references),
        outlet_scope=escape("All Outlets" if len(outlets) != 1 else outlets[0]),
        date_str=escape(date_str),
        trend_data_json=trend_data_json,
    )

    filename.write_text(html, encoding="utf-8")
    return str(filename)

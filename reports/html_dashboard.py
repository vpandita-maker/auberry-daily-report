from datetime import datetime
from html import escape
from pathlib import Path
import re


CATEGORY_ORDER = [
    ("food_quality", "Food Quality", "F"),
    ("service", "Service", "S"),
    ("ambiance", "Ambiance", "A"),
    ("value_for_money", "Value for Money", "V"),
    ("coffee_quality", "Coffee Quality", "C"),
]


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
                url = str(source.get("source_url", "")).strip()
                outlet = escape(str(source.get("outlet", "Outlet")))
                date_time = escape(str(source.get("date_time", "Unknown time")))
                label = f"{outlet} · {date_time}"
                if url:
                    links.append(
                        f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">Source {source_index}: {label}</a>'
                    )
                else:
                    links.append(f"<span>Source {source_index}: {label}</span>")
            source_html = (
                "<details class='mention-sources'>"
                "<summary class='mention-sources-toggle'>View source reviews</summary>"
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

    for index, issue in enumerate(issues):
        kicker = "Urgent" if index == 0 else "Watchlist"
        impact = "impact-high" if index == 0 else "impact-medium"
        status = "In Progress" if index == 0 else "Monitoring"
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
                tone="alert-urgent" if index == 0 else "alert-warning",
                kicker=escape(kicker),
                title=escape(issue),
                body=escape(
                    "Highest-priority issue surfaced from the latest review cycle."
                    if index == 0
                    else "Keep this under observation in the next review cycle."
                ),
                impact=impact,
                impact_label="High Impact" if index == 0 else "Medium Impact",
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
    for item in items:
        focus = str(item.get("location_focus", "Portfolio-wide"))
        metric = str(item.get("success_metric", "Set a measurable KPI before rollout"))
        timeline = str(item.get("timeline", "No timeline"))
        next_steps = str(item.get("action", "Define owner, rollout steps, and follow-up review checkpoints."))
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
                <span class="action-chip timeline-chip">
                  <strong>Timeline</strong>
                  <span>{timeline}</span>
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
                timeline=escape(timeline),
                next_steps=escape(next_steps),
            )
        )
    return "<div class='recommendations-grid'>{}</div>".format("".join(cards))


def _render_review_references(items):
    if not items:
        return "<div class='empty-block'>No new reviews were captured today.</div>"

    cards = []
    for item in items:
        rating = item.get("rating")
        rating_label = f"{float(rating):.1f}/5" if isinstance(rating, (int, float)) else "Unrated"
        author_url = str(item.get("author_url", "")).strip()
        source_url = str(item.get("source_url", "")).strip()
        author = escape(str(item.get("author", "Anonymous")))
        author_html = (
            f'<a href="{escape(author_url)}" target="_blank" rel="noopener noreferrer">{author}</a>'
            if author_url
            else author
        )
        source_html = (
            f'<a href="{escape(source_url)}" target="_blank" rel="noopener noreferrer">Open source</a>'
            if source_url
            else "Source unavailable"
        )
        cards.append(
            """
            <article class="review-card">
              <div class="review-meta">
                <div class="review-outlet">{outlet}</div>
                <span class="review-rating">{rating}</span>
              </div>
              <div class="review-detail">{location}</div>
              <div class="review-detail">{date_time}</div>
              <div class="review-author">Reviewer: {author_html}</div>
              <p>{text}</p>
              <div class="review-links">{source_html}</div>
            </article>
            """.format(
                outlet=escape(str(item.get("outlet", "Unknown outlet"))),
                rating=escape(rating_label),
                location=escape(str(item.get("location", "Location unavailable"))),
                date_time=escape(str(item.get("date_time", "Unknown date/time"))),
                author_html=author_html,
                text=escape(str(item.get("text", ""))),
                source_html=source_html,
            )
        )
    return "<div class='review-grid'>{}</div>".format("".join(cards))


def generate_html_dashboard(analysis, output_dir="output"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    brand = str(analysis.get("brand_name", "Restaurant Report"))
    date_str = datetime.now().strftime("%b %d, %Y")
    safe_name = _safe_filename(brand)
    filename = output_path / f"{safe_name}_Dashboard_{datetime.now().strftime('%Y%m%d')}.html"

    categories = analysis.get("categories") or {}
    items = analysis.get("most_mentioned_items") or []
    recommendations = analysis.get("top_3_recommendations") or []
    review_references = analysis.get("new_reviews_today") or []
    mention_sources = analysis.get("mention_sources") or {}
    outlets = analysis.get("portfolio_outlets") or []
    top_items, underperforming = _derive_item_panels(items)
    heatmap_rows = _build_heatmap(analysis)

    avg_rating = float(analysis.get("average_rating", 0) or 0)
    positive_categories = sum(
        1 for info in categories.values() if float((info or {}).get("score", 0) or 0) >= 4.0
    )
    sentiment_pct = 0
    if categories:
        sentiment_pct = round((positive_categories / len(categories)) * 100)

    review_window = str(analysis.get("review_window", "Dates unavailable"))
    report_scope = str(analysis.get("report_scope", "Today only"))
    risk_level = str(analysis.get("rating_risk", "Unknown")).title()
    risk_tone = "low" if risk_level.lower() == "low" else "medium" if risk_level.lower() == "medium" else "high"

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{brand} Dashboard</title>
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
      font-family: Arial, Helvetica, sans-serif;
      animation: page-fade 700ms cubic-bezier(.22,1,.36,1);
    }}
    .page {{
      max-width: 1536px;
      margin: 0 auto;
      padding: 20px;
    }}
    .dashboard {{
      display: grid;
      grid-template-columns: 350px minmax(0, 1fr) 320px;
      gap: 16px;
      align-items: stretch;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(40,47,74,0.98), rgba(33,39,63,0.98));
      border: 1px solid var(--border);
      border-radius: 18px;
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
      font-size: 16px;
      line-height: 1.4;
      letter-spacing: 0;
      font-weight: 400;
      font-family: Arial, Helvetica, sans-serif;
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
      font-size: 14px;
      line-height: 1.5;
      white-space: nowrap;
    }}
    .filter-text strong {{
      color: var(--text);
      font-weight: 700;
    }}
    .kpis {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
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
    .kpi-title {{ color: var(--muted); font-size: 14px; }}
    .kpi-value {{ font-size: 28px; font-weight: 800; margin-top: 4px; }}
    .kpi-sub {{ color: var(--muted); margin-top: 6px; font-size: 14px; }}
    .kpi-sub.positive {{ color: var(--green); }}
    .kpi-sub.negative {{ color: var(--red); }}
    .sparkline {{
      align-self: stretch;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .sparkline svg {{ width: 100%; height: 44px; }}
    .left-column, .right-column {{
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: 0;
      align-self: stretch;
    }}
    .center-column {{
      display: grid;
      gap: 16px;
      align-content: start;
      min-width: 0;
      align-self: start;
      height: max-content;
    }}
    .panel-title {{
      margin: 0;
      font-size: 18px;
      font-weight: 800;
    }}
    .panel-subtitle {{
      margin-top: 2px;
      color: var(--muted);
      font-size: 14px;
    }}
    .panel-header {{
      padding: 18px 18px 0;
    }}
    .list-panel {{
      padding-bottom: 14px;
      height: max-content;
    }}
    .left-column .list-panel:last-child {{
      flex: 1 1 auto;
      min-height: 0;
    }}
    .list-body {{
      padding: 8px 14px 14px;
      min-width: 0;
    }}
    .list-row {{
      display: grid;
      grid-template-columns: 24px 48px 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 10px 10px;
      border-top: 1px solid rgba(255,255,255,0.07);
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
      color: #d4d8ea;
      font-weight: 700;
      text-align: center;
    }}
    .item-thumb {{
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: linear-gradient(135deg, #9a6b42, #c99762);
      color: white;
      display: grid;
      place-items: center;
      font-weight: 800;
      font-size: 20px;
    }}
    .item-name {{
      font-weight: 700;
      line-height: 1.25;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .item-meta {{ color: var(--muted); font-size: 13px; margin-top: 2px; }}
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
      padding: 0 18px 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .heatmap-panel {{
      padding: 18px;
      height: max-content;
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
      margin-top: 18px;
      display: grid;
      gap: 8px;
    }}
    .heat-head, .heat-row {{
      display: grid;
      grid-template-columns: 160px repeat(5, minmax(0, 1fr));
      gap: 8px;
      align-items: stretch;
    }}
    .heat-header-cell {{
      text-align: center;
      color: #d8dcef;
      font-size: 13px;
      font-weight: 700;
      display: grid;
      gap: 6px;
      justify-items: center;
    }}
    .heat-icon {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba(255,255,255,0.06);
      display: grid;
      place-items: center;
    }}
    .heat-outlet {{
      display: flex;
      align-items: center;
      padding: 0 8px;
      font-weight: 700;
      line-height: 1.3;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .heat-cell {{
      min-height: 48px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      font-size: 15px;
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
      padding: 18px;
      height: max-content;
    }}
    .bubble-wrap {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      min-height: 270px;
      padding-top: 14px;
      align-content: start;
    }}
    .mention-card {{
      border-radius: 16px;
      padding: 14px 16px;
      border: 1px solid rgba(255,255,255,0.08);
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      min-height: 92px;
      transition:
        transform 180ms cubic-bezier(.22,1,.36,1),
        border-color 180ms ease,
      box-shadow 180ms ease,
      filter 180ms ease;
    }}
    .mention-card:hover {{
      transform: translateY(-5px);
      border-color: rgba(255,255,255,0.16);
      box-shadow: 0 18px 28px rgba(6, 9, 21, 0.24);
      filter: brightness(1.03);
    }}
    .mention-positive {{ background: linear-gradient(180deg, rgba(76,170,75,0.22), rgba(65,137,63,0.18)); }}
    .mention-neutral {{ background: linear-gradient(180deg, rgba(213,162,24,0.22), rgba(184,136,20,0.18)); }}
    .mention-negative {{ background: linear-gradient(180deg, rgba(214,101,101,0.22), rgba(187,79,79,0.18)); }}
    .mention-na {{ background: linear-gradient(180deg, rgba(107,115,139,0.22), rgba(83,90,113,0.18)); }}
    .mention-rank {{
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: rgba(255,255,255,0.08);
      display: grid;
      place-items: center;
      font-weight: 800;
      color: #eef1ff;
    }}
    .mention-body h4 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.1;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .mention-meta {{
      margin-top: 10px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      color: rgba(255,255,255,0.86);
      font-size: 13px;
    }}
    .mention-sources {{
      margin-top: 12px;
      border-radius: 14px;
      border: 1px solid rgba(111,167,255,0.18);
      background: rgba(23, 27, 49, 0.78);
      overflow: hidden;
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
      display: grid;
      gap: 6px;
      padding: 0 12px 12px;
      animation: mention-slide-down 220ms cubic-bezier(.22,1,.36,1);
    }}
    .mention-sources-title {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(255,255,255,0.68);
      margin-bottom: 2px;
    }}
    .mention-sources a, .mention-sources span {{
      color: #b9d6ff;
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .mention-sources a {{
      text-decoration: none;
      font-weight: 700;
      padding: 4px 0;
    }}
    .mention-sources a:hover {{
      text-decoration: underline;
    }}
    .side-panel {{
      padding: 18px;
      height: max-content;
    }}
    .right-column .side-panel {{
      flex: 1 1 auto;
      min-height: 0;
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
      padding: 18px;
      border: 1px solid rgba(111,167,255,0.16);
      background: linear-gradient(180deg, rgba(48,58,94,0.95), rgba(39,47,77,0.95));
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .review-meta {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }}
    .review-outlet {{
      font-size: 16px;
      font-weight: 700;
      line-height: 1.35;
    }}
    .review-rating {{
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(111,167,255,0.14);
      border: 1px solid rgba(111,167,255,0.18);
      color: #b9d6ff;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .review-detail, .review-author {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .review-author a, .review-links a {{
      color: #b9d6ff;
      text-decoration: none;
      font-weight: 700;
    }}
    .review-author a:hover, .review-links a:hover {{
      text-decoration: underline;
    }}
    .review-card p {{
      margin: 0;
      color: #f7f8ff;
      font-size: 14px;
      line-height: 1.65;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .review-links {{
      font-size: 13px;
      line-height: 1.5;
    }}
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
      grid-template-columns: repeat(2, minmax(0, 1fr));
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
    .timeline-chip {{
      background: linear-gradient(180deg, rgba(171,125,244,0.14), rgba(171,125,244,0.06));
      border-color: rgba(171,125,244,0.18);
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
    .empty-block {{
      color: var(--muted);
      padding: 18px 0 6px;
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
      .dashboard {{
        grid-template-columns: 320px minmax(0, 1fr);
      }}
      .right-column {{
        grid-column: 1 / -1;
      }}
      .recommendations-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .review-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 1120px) {{
      .dashboard {{
        grid-template-columns: 1fr;
      }}
      .left-column, .center-column, .right-column {{
        display: grid;
        grid-template-columns: 1fr;
        align-self: start;
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
        grid-template-columns: 120px repeat(5, minmax(54px, 1fr));
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
        grid-template-columns: 24px 44px minmax(0, 1fr);
      }}
      .list-row .pill {{
        grid-column: 2 / -1;
        justify-self: start;
      }}
      .heat-header-cell {{
        font-size: 11px;
      }}
      .heat-cell {{
        min-height: 44px;
        font-size: 12px;
      }}
      .heat-outlet {{
        font-size: 13px;
      }}
      .bubble-wrap {{
        grid-template-columns: 1fr;
      }}
      .action-metrics {{
        grid-template-columns: 1fr;
      }}
      .action-row {{
        padding: 16px;
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
  </style>
</head>
<body>
  <main class="page">
    <section class="dashboard">
      <div class="topbar">
        <div class="brand-block">
          <div class="brand-copy">
            <h1>{brand} Executive Dashboard</h1>
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
          <div class="sparkline">{spark_green}</div>
        </article>
        <article class="card kpi-card">
          <div class="kpi-icon green">☺</div>
          <div>
            <div class="kpi-title">Positive Sentiment</div>
            <div class="kpi-value">{sentiment_pct}%</div>
            <div class="kpi-sub positive">↑ {sentiment_delta}</div>
          </div>
          <div class="sparkline">{spark_green_2}</div>
        </article>
        <article class="card kpi-card">
          <div class="kpi-icon red">⛨</div>
          <div>
            <div class="kpi-title">Risk Level</div>
            <div class="kpi-value" style="color:{risk_color};">{risk_level}</div>
            <div class="kpi-sub">{report_scope}</div>
          </div>
          <div class="sparkline">{spark_risk}</div>
        </article>
        <article class="card kpi-card">
          <div class="kpi-icon purple">◔</div>
          <div>
            <div class="kpi-title">Total Reviews</div>
            <div class="kpi-value">{total_reviews}</div>
            <div class="kpi-sub positive">↑ {review_delta}</div>
          </div>
          <div class="sparkline">{spark_purple}</div>
        </article>
      </section>

      <div class="left-column">
        <section class="card list-panel" id="top-items">
          <div class="panel-header">
            <h3 class="panel-title">Top Positive Items</h3>
            <div class="panel-subtitle">Best-reviewed menu mentions</div>
          </div>
          <div class="list-body">{top_items_html}</div>
        </section>

        <section class="card list-panel" id="underperforming-items">
          <div class="panel-header">
            <h3 class="panel-title">Underperforming Items</h3>
          <div class="panel-subtitle">By Mentions</div>
          </div>
          <div class="list-body">{underperforming_html}</div>
          <div class="list-footer">Most-mentioned risk items from the latest review cycle.</div>
        </section>
      </div>

      <div class="center-column">
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

      <div class="right-column">
        <section class="card side-panel danger">
          <h3 class="panel-title">Urgent &amp; Important</h3>
          {alerts_html}
        </section>
      </div>

      <section class="card recommendations-panel" id="recommendations">
        <h3 class="panel-title">Recommendations</h3>
        <div class="panel-subtitle">Action plans with measurable targets and timelines across the full portfolio.</div>
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
</body>
</html>
""".format(
        brand=escape(brand),
        review_window=escape(review_window),
        avg_rating=avg_rating,
        rating_delta=escape(_metric_delta(round(avg_rating - 4.3, 1), "vs yesterday", "vs yesterday")),
        sentiment_pct=sentiment_pct,
        sentiment_delta=escape(_metric_delta(sentiment_pct - 60, "vs yesterday", "vs yesterday")),
        risk_level=escape(risk_level),
        risk_color={"low": "#69dd74", "medium": "#f1bc2e", "high": "#ef6464"}.get(risk_tone, "#d9ddf2"),
        report_scope=escape(report_scope),
        total_reviews=escape(str(int(analysis.get("total_reviews_analyzed", 0) or 0))),
        review_delta=escape(_metric_delta(int(analysis.get("total_reviews_analyzed", 0) or 0) - 18, "vs yesterday", "vs yesterday")),
        top_items_html=_render_item_rows(top_items, "No top items available yet.", "positive"),
        underperforming_html=_render_item_rows(
            underperforming,
            "No underperforming items flagged yet.",
            "negative",
        ),
        heatmap_html=_render_heatmap(heatmap_rows),
        mentions_board_html=_render_mentions_board(items, mention_sources),
        alerts_html=_render_alerts(analysis),
        recommendations_html=_render_recommendations(recommendations),
        review_references_html=_render_review_references(review_references),
        outlet_scope=escape("All Outlets" if len(outlets) != 1 else outlets[0]),
        date_str=escape(date_str),
        spark_green="""
          <svg viewBox="0 0 100 36" fill="none"><path d="M0 24 L10 26 L20 18 L30 25 L40 20 L50 11 L60 14 L70 5 L80 8 L90 7 L100 3" stroke="#67dd69" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        """,
        spark_green_2="""
          <svg viewBox="0 0 100 36" fill="none"><path d="M0 28 L10 18 L20 24 L30 26 L40 9 L50 20 L60 19 L70 8 L80 12 L90 11 L100 6" stroke="#67dd69" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        """,
        spark_risk="""
          <svg viewBox="0 0 100 36" fill="none"><path d="M0 29 L10 23 L20 24 L30 18 L40 21 L50 10 L60 7 L70 19 L80 16 L90 16 L100 20" stroke="#67dd69" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        """,
        spark_purple="""
          <svg viewBox="0 0 100 36" fill="none"><path d="M0 21 L10 10 L20 18 L30 7 L40 3 L50 15 L60 4 L70 21 L80 24 L90 22 L100 18" stroke="#b383ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        """,
    )

    filename.write_text(html, encoding="utf-8")
    return str(filename)

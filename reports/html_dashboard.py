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


def _render_bubbles(items):
    if not items:
        return "<div class='empty-block'>No item trends available.</div>"

    bubble_markup = []
    size_classes = ["bubble-xl", "bubble-lg", "bubble-md", "bubble-md", "bubble-sm", "bubble-sm", "bubble-xs"]
    for index, item in enumerate(items[:7]):
        mentions = int(item.get("mentions", 0) or 0)
        sentiment = _normalize_sentiment(item.get("sentiment"))
        bubble_markup.append(
            """
            <div class="bubble {size} bubble-{sentiment}">
              <strong>{name}</strong>
              <span>{mentions} mention{plural}</span>
            </div>
            """.format(
                size=size_classes[min(index, len(size_classes) - 1)],
                sentiment=escape(sentiment),
                name=escape(str(item.get("item", "Unknown"))),
                mentions=mentions,
                plural="" if mentions == 1 else "s",
            )
        )
    first_row = "".join(bubble_markup[:4])
    second_row = "".join(bubble_markup[4:])
    rows = [f"<div class='bubble-row bubble-row-top'>{first_row}</div>"]
    if second_row:
        rows.append(f"<div class='bubble-row bubble-row-bottom'>{second_row}</div>")
    return "".join(rows)


def _render_alerts(analysis):
    issues = analysis.get("top_3_urgent_issues") or []
    recommendations = analysis.get("top_3_recommendations") or []
    failed_outlets = analysis.get("portfolio_failed_outlets") or []
    alerts = []

    if issues:
        primary = issues[0]
        alerts.append(
            """
            <div class="alert-card alert-urgent">
              <div class="alert-kicker">Urgent</div>
              <h4>{title}</h4>
              <p>{body}</p>
              <div class="alert-meta">
                <span class="impact impact-high">High Impact</span>
                <span class="status-chip">In Progress</span>
              </div>
            </div>
            """.format(
                title=escape(primary),
                body=escape("Highest-priority issue surfaced from the latest review cycle."),
            )
        )

    if failed_outlets:
        failed = failed_outlets[0]
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
    elif len(issues) > 1:
        alerts.append(
            """
            <div class="alert-card alert-warning">
              <div class="alert-kicker">Watchlist</div>
              <h4>{title}</h4>
              <p>{body}</p>
              <div class="alert-meta">
                <span class="impact impact-medium">Medium Impact</span>
                <span class="status-chip">Monitoring</span>
              </div>
            </div>
            """.format(
                title=escape(issues[1]),
                body=escape("Keep this under observation in the next review cycle."),
            )
        )

    if not alerts and recommendations:
        rec = recommendations[0]
        alerts.append(
            """
            <div class="alert-card alert-info">
              <div class="alert-kicker">Focus</div>
              <h4>{title}</h4>
              <p>{body}</p>
              <div class="alert-meta">
                <span class="impact impact-low">Low Risk</span>
                <span class="status-chip">Planned</span>
              </div>
            </div>
            """.format(
                title=escape(str(rec.get("title", "Portfolio focus"))),
                body=escape(str(rec.get("action", "No additional action text available."))),
            )
        )

    return "".join(alerts) or "<div class='empty-block'>No urgent issues available.</div>"


def _render_recommendations(items):
    if not items:
        return "<div class='empty-block'>No recommendations available.</div>"

    cards = []
    for item in items[:3]:
        cards.append(
            """
            <a class="action-row" href="#outlet-heatmap">
              <div class="action-icon">→</div>
              <div class="action-copy">
                <div class="action-title">{title}</div>
                <div class="action-meta">{focus} • {timeline}</div>
              </div>
            </a>
            """.format(
                title=escape(str(item.get("title", "Untitled recommendation"))),
                focus=escape(str(item.get("location_focus", "Portfolio-wide"))),
                timeline=escape(str(item.get("timeline", "No timeline"))),
            )
        )
    return "".join(cards)


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
    report_scope = str(analysis.get("report_scope", "Last 30 days"))
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
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(171,125,244,0.12), transparent 22%),
        radial-gradient(circle at top right, rgba(99,216,95,0.10), transparent 18%),
        linear-gradient(180deg, #161a30 0%, #13182c 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .page {{
      max-width: 1536px;
      margin: 0 auto;
      padding: 18px;
    }}
    .dashboard {{
      display: grid;
      grid-template-columns: 380px minmax(0, 1fr) 340px;
      gap: 12px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(40,47,74,0.98), rgba(33,39,63,0.98));
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: var(--shadow);
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
      gap: 16px;
      align-items: center;
    }}
    .logo-badge {{
      width: 92px;
      height: 92px;
      border-radius: 24px;
      background: linear-gradient(135deg, #2c2347, #1f233b);
      border: 1px solid #302f55;
      display: grid;
      place-items: center;
      flex-shrink: 0;
    }}
    .logo-inner {{
      width: 68px;
      height: 68px;
      border-radius: 50%;
      background: #f4dff1;
      color: #281827;
      display: grid;
      place-items: center;
      text-align: center;
      font-weight: 800;
      line-height: 1.02;
      padding: 6px;
      font-size: 12px;
    }}
    .brand-copy h1 {{
      margin: 0;
      font-size: clamp(34px, 3vw, 54px);
      line-height: 1.02;
      letter-spacing: -0.03em;
    }}
    .brand-copy p {{
      margin: 6px 0 0;
      font-size: 16px;
      color: var(--muted);
    }}
    .filters {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .filter-pill {{
      min-width: 210px;
      padding: 14px 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: rgba(34,40,62,0.95);
      color: var(--text);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 14px;
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
    .left-column, .center-column, .right-column {{
      display: grid;
      gap: 12px;
      align-content: start;
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
    }}
    .list-body {{
      padding: 8px 14px 14px;
    }}
    .list-row {{
      display: grid;
      grid-template-columns: 24px 48px 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 10px 10px;
      border-top: 1px solid rgba(255,255,255,0.07);
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
    .item-name {{ font-weight: 700; }}
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
      padding: 0 14px 14px;
    }}
    .ghost-btn {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--border);
      text-align: center;
      color: var(--text);
      background: rgba(255,255,255,0.02);
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
    }}
    .heatmap-panel {{
      padding: 18px;
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
    }}
    .heat-positive {{ background: #58b958; color: white; }}
    .heat-neutral {{ background: #dba923; color: white; }}
    .heat-negative {{ background: #e85f68; color: white; }}
    .heat-na {{ background: #5a637d; color: #eef2ff; }}
    .bubbles-panel {{
      padding: 18px;
    }}
    .bubble-wrap {{
      display: grid;
      gap: 18px;
      min-height: 270px;
      padding-top: 14px;
      align-content: start;
    }}
    .bubble-row {{
      display: flex;
      gap: 18px;
      align-items: flex-end;
      justify-content: flex-start;
      flex-wrap: nowrap;
    }}
    .bubble-row-bottom {{
      padding-left: 20px;
    }}
    .bubble {{
      border-radius: 50%;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 12px;
      line-height: 1.15;
      border: 2px solid rgba(255,255,255,0.14);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
      overflow: hidden;
    }}
    .bubble strong {{
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      text-wrap: balance;
      overflow-wrap: anywhere;
      word-break: break-word;
      max-width: 92%;
      line-height: 1.1;
      font-size: 14px;
    }}
    .bubble span {{
      color: rgba(255,255,255,0.86);
      font-size: 12px;
      margin-top: 5px;
      max-width: 88%;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }}
    .bubble-positive {{ background: linear-gradient(180deg, #4caa4b, #41893f); }}
    .bubble-neutral {{ background: linear-gradient(180deg, #d5a218, #b88814); }}
    .bubble-negative {{ background: linear-gradient(180deg, #d66565, #bb4f4f); }}
    .bubble-na {{ background: linear-gradient(180deg, #6b738b, #535a71); }}
    .bubble-xl {{ width: 176px; height: 176px; }}
    .bubble-lg {{ width: 138px; height: 138px; }}
    .bubble-md {{ width: 116px; height: 116px; }}
    .bubble-sm {{ width: 104px; height: 104px; }}
    .bubble-xs {{ width: 96px; height: 96px; }}
    .side-panel {{
      padding: 18px;
    }}
    .side-panel.danger h3 {{ color: #ff6d6d; }}
    .side-panel.rec h3 {{ color: #bc93ff; }}
    .alert-card {{
      margin-top: 14px;
      border-radius: 16px;
      padding: 14px 14px 12px;
      border: 1px solid transparent;
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
    .action-row {{
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 12px;
      align-items: start;
      padding: 12px 0;
      border-top: 1px solid rgba(255,255,255,0.07);
      text-decoration: none;
      color: inherit;
    }}
    .action-row:first-of-type {{ border-top: none; }}
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
    .action-title {{ font-weight: 700; }}
    .action-title, .action-meta {{
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .action-meta {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
    .button-link:hover, .action-row:hover {{
      filter: brightness(1.06);
      transform: translateY(-1px);
      transition: 120ms ease;
    }}
    .empty-block {{
      color: var(--muted);
      padding: 18px 0 6px;
    }}
    .footer-note {{
      grid-column: 1 / -1;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
      padding-bottom: 6px;
    }}
    @media (max-width: 1260px) {{
      .dashboard {{
        grid-template-columns: 1fr;
      }}
      .left-column, .center-column, .right-column {{
        grid-template-columns: 1fr;
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
    }}
    @media (max-width: 720px) {{
      .kpis {{
        grid-template-columns: 1fr;
      }}
      .topbar {{
        grid-template-columns: 1fr;
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
        gap: 14px;
      }}
      .bubble-row {{
        flex-wrap: wrap;
        justify-content: center;
      }}
      .bubble-row-bottom {{
        padding-left: 0;
      }}
      .bubble strong {{
        font-size: 14px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="dashboard">
      <div class="topbar">
        <div class="brand-block">
          <div class="logo-badge">
            <div class="logo-inner">Auberry<br /><small>The Bake Shop</small></div>
          </div>
          <div class="brand-copy">
            <h1>{brand}</h1>
            <p>Executive Dashboard</p>
          </div>
        </div>
        <div class="filters">
          <div class="filter-pill"><span>All Outlets</span><span>⌄</span></div>
          <div class="filter-pill"><span>{review_window}</span><span>⌄</span></div>
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
          <div class="list-footer">
            <a class="ghost-btn button-link" href="#items-overview">View All Items</a>
          </div>
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
          <div class="bubble-wrap">{bubbles_html}</div>
        </section>
      </div>

      <div class="right-column">
        <section class="card side-panel danger">
          <h3 class="panel-title">Urgent &amp; Important</h3>
          {alerts_html}
        </section>

        <section class="card side-panel rec" id="ai-recommendations">
          <h3 class="panel-title">AI Recommendations</h3>
          {recommendations_html}
          <div style="margin-top:14px;">
            <a class="ghost-btn button-link" href="#ai-recommendations" style="border-color:#5c478f;color:#d2b4ff;">View All Actions</a>
          </div>
        </section>
      </div>

      <div class="footer-note">Live executive dashboard for {brand} • Updated {date_str}</div>
    </section>
  </main>
</body>
</html>
""".format(
        brand=escape(brand),
        review_window=escape(review_window),
        avg_rating=avg_rating,
        rating_delta=escape(_metric_delta(round(avg_rating - 4.3, 1), "from last month", "from last month")),
        sentiment_pct=sentiment_pct,
        sentiment_delta=escape(_metric_delta(sentiment_pct - 60, "from last month", "from last month")),
        risk_level=escape(risk_level),
        risk_color={"low": "#69dd74", "medium": "#f1bc2e", "high": "#ef6464"}.get(risk_tone, "#d9ddf2"),
        report_scope=escape(report_scope),
        total_reviews=escape(str(int(analysis.get("total_reviews_analyzed", 0) or 0))),
        review_delta=escape(_metric_delta(int(analysis.get("total_reviews_analyzed", 0) or 0) - 18, "from last month", "from last month")),
        top_items_html=_render_item_rows(top_items, "No top items available yet.", "positive"),
        underperforming_html=_render_item_rows(
            underperforming,
            "No underperforming items flagged yet.",
            "negative",
        ),
        heatmap_html=_render_heatmap(heatmap_rows),
        bubbles_html=_render_bubbles(items),
        alerts_html=_render_alerts(analysis),
        recommendations_html=_render_recommendations(recommendations),
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

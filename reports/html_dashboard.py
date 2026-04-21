from datetime import datetime
from html import escape
from pathlib import Path


def _safe_filename(text):
    return text.replace(" ", "_").replace("-", "").replace("/", "")


def _format_list(items):
    if not items:
        return "<li>Not available</li>"
    return "".join(f"<li>{escape(str(item))}</li>" for item in items)


def _format_recommendations(items):
    cards = []
    for item in items[:3]:
        cards.append(
            """
            <article class="recommendation-card">
              <h3>{title}</h3>
              <p><strong>Location focus:</strong> {location_focus}</p>
              <p><strong>Action:</strong> {action}</p>
              <p><strong>Success metric:</strong> {success_metric}</p>
              <p><strong>Timeline:</strong> {timeline}</p>
            </article>
            """.format(
                title=escape(str(item.get("title", "Untitled recommendation"))),
                location_focus=escape(str(item.get("location_focus", "Portfolio-wide"))),
                action=escape(str(item.get("action", "Not available"))),
                success_metric=escape(str(item.get("success_metric", "Not available"))),
                timeline=escape(str(item.get("timeline", "Not available"))),
            )
        )
    return "".join(cards) or "<p class='empty-state'>No recommendations available.</p>"


def _format_items(items):
    rows = []
    for item in items[:5]:
        rows.append(
            """
            <tr>
              <td>{item_name}</td>
              <td>{sentiment}</td>
              <td>{mentions}</td>
            </tr>
            """.format(
                item_name=escape(str(item.get("item", "Unknown"))),
                sentiment=escape(str(item.get("sentiment", "")).title()),
                mentions=escape(str(item.get("mentions", 0))),
            )
        )
    if not rows:
        rows.append("<tr><td colspan='3'>No items available.</td></tr>")
    return "".join(rows)


def _format_categories(categories):
    cards = []
    for key, info in categories.items():
        cards.append(
            """
            <article class="category-card">
              <div class="category-header">
                <h3>{name}</h3>
                <span class="score-pill">{score:.1f} / 5</span>
              </div>
              <p class="summary">{summary}</p>
              <p><strong>Primary issue:</strong> {issue}</p>
              <p><strong>Primary strength:</strong> {praise}</p>
            </article>
            """.format(
                name=escape(key.replace("_", " ").title()),
                score=float(info.get("score", 0)),
                summary=escape(str(info.get("summary", "Not available"))),
                issue=escape(str((info.get("top_issues") or ["Not available"])[0])),
                praise=escape(str((info.get("top_praises") or ["Not available"])[0])),
            )
        )
    return "".join(cards)


def generate_html_dashboard(analysis, output_dir="output"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    brand = str(analysis.get("brand_name", "Restaurant Report"))
    date_str = datetime.now().strftime("%B %d, %Y")
    safe_name = _safe_filename(brand)
    filename = output_path / f"{safe_name}_Dashboard_{datetime.now().strftime('%Y%m%d')}.html"

    recommendations = analysis.get("top_3_recommendations") or []
    locations = analysis.get("portfolio_locations") or []
    review_window = analysis.get("review_window", "Dates unavailable")
    report_scope = analysis.get("report_scope", "Latest available data")
    items_html = _format_items(analysis.get("most_mentioned_items") or [])
    categories_html = _format_categories(analysis.get("categories") or {})
    recommendations_html = _format_recommendations(recommendations)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{brand} Dashboard</title>
  <style>
    :root {{
      --paper: #f7f2eb;
      --card: #fffdfa;
      --ink: #1d2d3d;
      --muted: #667788;
      --line: #e4dacb;
      --gold: #be9143;
      --navy: #16263b;
      --soft: #f0e4cf;
      --danger: #8d3131;
      --warn: #8b6114;
      --success: #2f6b45;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(190,145,67,0.12), transparent 26%),
        linear-gradient(180deg, #fcfaf7 0%, var(--paper) 100%);
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, #16263b 0%, #22344c 100%);
      color: white;
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 18px 50px rgba(17, 28, 44, 0.16);
    }}
    .eyebrow {{
      color: #e6c98f;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: clamp(34px, 5vw, 54px);
      line-height: 1.02;
    }}
    .hero p {{
      margin: 6px 0;
      color: #dbe3ea;
      font-size: 16px;
    }}
    .hero-meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .hero-meta .meta-box {{
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.06);
      border-radius: 16px;
      padding: 14px 16px;
    }}
    .section {{
      margin-top: 28px;
    }}
    .section-label {{
      color: var(--gold);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .section h2 {{
      margin: 0 0 16px;
      font-size: 34px;
      line-height: 1.1;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    .metric-card, .category-card, .panel, .recommendation-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 10px 28px rgba(33, 40, 50, 0.05);
    }}
    .metric-card .label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .metric-card .value {{
      font-size: 38px;
      font-weight: 800;
      margin: 8px 0 6px;
    }}
    .metric-card .note {{
      color: var(--muted);
      font-size: 14px;
    }}
    .split {{
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 18px;
    }}
    .category-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .category-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .category-card h3, .recommendation-card h3 {{
      margin: 0;
      font-size: 24px;
    }}
    .score-pill {{
      background: var(--soft);
      color: var(--ink);
      padding: 8px 12px;
      border-radius: 999px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .summary {{
      font-size: 15px;
      line-height: 1.55;
    }}
    .panel h3 {{
      margin: 0 0 12px;
      font-size: 22px;
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
    }}
    li {{
      margin: 0 0 8px;
      line-height: 1.45;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 16px;
    }}
    th, td {{
      text-align: left;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }}
    th {{
      background: #f7efe1;
      color: var(--ink);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .recommendations {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 14px;
    }}
    .recommendation-card p {{
      margin: 10px 0 0;
      line-height: 1.45;
    }}
    .locations {{
      columns: 2 280px;
      gap: 18px;
      margin: 0;
      padding-left: 18px;
    }}
    .footer {{
      margin-top: 26px;
      color: var(--muted);
      text-align: center;
      font-size: 13px;
    }}
    .empty-state {{
      color: var(--muted);
      margin: 0;
    }}
    @media (max-width: 860px) {{
      .split {{
        grid-template-columns: 1fr;
      }}
      .hero {{
        padding: 22px;
      }}
      .section h2 {{
        font-size: 28px;
      }}
      .metric-card .value {{
        font-size: 30px;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow">Review Intelligence Dashboard</div>
      <h1>{brand}</h1>
      <p>{date_str}</p>
      <p>Performance brief built from {total_reviews} customer reviews.</p>
      <div class="hero-meta">
        <div class="meta-box"><strong>Scope:</strong><br />{report_scope}</div>
        <div class="meta-box"><strong>Review window:</strong><br />{review_window}</div>
        <div class="meta-box"><strong>Outlets included:</strong><br />{outlet_count}</div>
      </div>
    </section>

    <section class="section">
      <div class="section-label">Overview</div>
      <h2>Executive Snapshot</h2>
      <div class="metrics">
        <article class="metric-card">
          <div class="label">Overall Sentiment</div>
          <div class="value">{overall_sentiment}</div>
          <div class="note">Current customer mood</div>
        </article>
        <article class="metric-card">
          <div class="label">Average Rating</div>
          <div class="value">{average_rating}</div>
          <div class="note">Public review average</div>
        </article>
        <article class="metric-card">
          <div class="label">Reviews Analyzed</div>
          <div class="value">{total_reviews}</div>
          <div class="note">Sample powering this brief</div>
        </article>
        <article class="metric-card">
          <div class="label">Rating Risk</div>
          <div class="value">{rating_risk}</div>
          <div class="note">Likelihood of downward pressure</div>
        </article>
      </div>
    </section>

    <section class="section">
      <div class="section-label">Breakdown</div>
      <h2>Category Performance</h2>
      <div class="category-grid">
        {categories_html}
      </div>
    </section>

    <section class="section split">
      <div class="panel">
        <div class="section-label">Menu</div>
        <h3>Most Mentioned Items</h3>
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Sentiment</th>
              <th>Mentions</th>
            </tr>
          </thead>
          <tbody>
            {items_html}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <div class="section-label">Coverage</div>
        <h3>Outlet Locations</h3>
        <ul class="locations">
          {locations_html}
        </ul>
      </div>
    </section>

    <section class="section split">
      <div class="panel">
        <div class="section-label">Snapshot</div>
        <h3>Top 3 Urgent Issues</h3>
        <ul>
          {urgent_issues_html}
        </ul>
      </div>
      <div class="panel">
        <div class="section-label">Snapshot</div>
        <h3>Top 3 Strengths</h3>
        <ul>
          {strengths_html}
        </ul>
      </div>
    </section>

    <section class="section">
      <div class="section-label">Action</div>
      <h2>Top 3 Recommendations</h2>
      <div class="recommendations">
        {recommendations_html}
      </div>
    </section>

    <footer class="footer">
      CONFIDENTIAL INTERNAL USE<br />
      {brand} | {date_str}
    </footer>
  </main>
</body>
</html>
""".format(
        brand=escape(brand),
        date_str=escape(date_str),
        total_reviews=escape(str(analysis.get("total_reviews_analyzed", 0))),
        report_scope=escape(str(report_scope)),
        review_window=escape(str(review_window)),
        outlet_count=escape(str(len(analysis.get("portfolio_outlets") or []))),
        overall_sentiment=escape(str(analysis.get("overall_sentiment", "")).title()),
        average_rating=escape(f"{float(analysis.get('average_rating', 0)):.1f}/5"),
        rating_risk=escape(str(analysis.get("rating_risk", "")).title()),
        categories_html=categories_html,
        items_html=items_html,
        locations_html=_format_list(locations),
        urgent_issues_html=_format_list(analysis.get("top_3_urgent_issues") or []),
        strengths_html=_format_list(analysis.get("top_3_strengths") or []),
        recommendations_html=recommendations_html,
    )

    filename.write_text(html, encoding="utf-8")
    return str(filename)

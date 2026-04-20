from datetime import datetime
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PAGE_WIDTH, PAGE_HEIGHT = A4

NAVY = colors.HexColor("#132238")
INK = colors.HexColor("#1E2B36")
SLATE = colors.HexColor("#607080")
STONE = colors.HexColor("#8F99A3")
GOLD = colors.HexColor("#C79A4A")
GOLD_SOFT = colors.HexColor("#F3E6CF")
MIST = colors.HexColor("#F5F1EA")
PAPER = colors.HexColor("#FBF8F3")
WHITE = colors.white
LINE = colors.HexColor("#E6DED2")
SUCCESS_BG = colors.HexColor("#E8F3EC")
SUCCESS_TEXT = colors.HexColor("#2F6B45")
WARN_BG = colors.HexColor("#FFF0D9")
WARN_TEXT = colors.HexColor("#8A5A12")
DANGER_BG = colors.HexColor("#FBE4E4")
DANGER_TEXT = colors.HexColor("#8F2F2F")


def _truncate(text, limit):
    if not text:
        return "Not mentioned"
    cleaned = str(text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3].rstrip() + "..."


def _sentiment_colors(value):
    value = str(value).strip().lower()
    if value == "positive":
        return SUCCESS_BG, SUCCESS_TEXT
    if value == "neutral":
        return WARN_BG, WARN_TEXT
    return DANGER_BG, DANGER_TEXT


def _risk_colors(value):
    value = str(value).strip().lower()
    if value == "low":
        return SUCCESS_BG, SUCCESS_TEXT
    if value == "medium":
        return WARN_BG, WARN_TEXT
    return DANGER_BG, DANGER_TEXT


def _score_colors(score):
    if score >= 4.2:
        return SUCCESS_BG, SUCCESS_TEXT
    if score >= 3.4:
        return WARN_BG, WARN_TEXT
    return DANGER_BG, DANGER_TEXT


def _score_to_bar(score, max_score=5, segments=10):
    filled = max(0, min(segments, round((score / max_score) * segments)))
    return filled, segments - filled


def _score_bar_flowable(score, styles, width=2.2 * inch, segments=10):
    filled, empty = _score_to_bar(score, segments=segments)
    segment_width = width / segments
    score_bg, _score_text = _score_colors(score)

    label = Paragraph("<b>Score bar</b>", styles["small"])
    bar = Table([[""] * segments], colWidths=[segment_width] * segments, rowHeights=[0.12 * inch])
    style_commands = [
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, WHITE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    for idx in range(segments):
        fill = score_bg if idx < filled else colors.HexColor("#E9E2D8")
        style_commands.append(("BACKGROUND", (idx, 0), (idx, 0), fill))
    bar.setStyle(TableStyle(style_commands))

    caption = Paragraph(f"{score:.1f} / 5 across {segments} segments", styles["small"])
    container = Table([[label, bar, caption]], colWidths=[0.9 * inch, width, 1.55 * inch])
    container.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return container


def _build_styles():
    return {
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=GOLD_SOFT,
            leading=10,
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "hero_title": ParagraphStyle(
            "HeroTitle",
            fontName="Helvetica-Bold",
            fontSize=19,
            textColor=WHITE,
            leading=23,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "hero_meta": ParagraphStyle(
            "HeroMeta",
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#DCE2E8"),
            leading=14,
            alignment=TA_LEFT,
        ),
        "hero_body": ParagraphStyle(
            "HeroBody",
            fontName="Helvetica",
            fontSize=10.5,
            textColor=colors.HexColor("#E9EEF2"),
            leading=15,
            alignment=TA_LEFT,
        ),
        "section_label": ParagraphStyle(
            "SectionLabel",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=GOLD,
            leading=10,
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "section_title": ParagraphStyle(
            "SectionTitle",
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=NAVY,
            leading=19,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=10,
            textColor=INK,
            leading=14,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "Small",
            fontName="Helvetica",
            fontSize=8.5,
            textColor=SLATE,
            leading=11,
            alignment=TA_LEFT,
        ),
        "small_center": ParagraphStyle(
            "SmallCenter",
            fontName="Helvetica",
            fontSize=8.5,
            textColor=SLATE,
            leading=11,
            alignment=TA_CENTER,
        ),
        "card_label": ParagraphStyle(
            "CardLabel",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=SLATE,
            leading=10,
            alignment=TA_LEFT,
        ),
        "card_value": ParagraphStyle(
            "CardValue",
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=NAVY,
            leading=19,
            alignment=TA_LEFT,
        ),
        "card_note": ParagraphStyle(
            "CardNote",
            fontName="Helvetica",
            fontSize=8.5,
            textColor=STONE,
            leading=11,
            alignment=TA_LEFT,
        ),
        "chip": ParagraphStyle(
            "Chip",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            textColor=INK,
            leading=10,
            alignment=TA_CENTER,
        ),
        "category_title": ParagraphStyle(
            "CategoryTitle",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=NAVY,
            leading=14,
            alignment=TA_LEFT,
        ),
        "list_item": ParagraphStyle(
            "ListItem",
            fontName="Helvetica",
            fontSize=10,
            textColor=INK,
            leading=15,
            leftIndent=0,
            alignment=TA_LEFT,
        ),
        "footer": ParagraphStyle(
            "Footer",
            fontName="Helvetica",
            fontSize=7.5,
            textColor=STONE,
            leading=10,
            alignment=TA_CENTER,
        ),
    }


def _metric_card(label, value, note, styles):
    table = Table(
        [
            [Paragraph(label.upper(), styles["card_label"])],
            [Paragraph(value, styles["card_value"])],
            [Paragraph(note, styles["card_note"])],
        ],
        colWidths=[2.85 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (0, 0), 4),
                ("BOTTOMPADDING", (0, 1), (0, 1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _pill(text, bg_color, text_color, styles, width):
    pill_style = ParagraphStyle(
        f"pill_{text}_{width}",
        parent=styles["chip"],
        textColor=text_color,
    )
    table = Table([[Paragraph(text.upper(), pill_style)]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                ("BOX", (0, 0), (-1, -1), 0, bg_color),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return table


def _section_header(label, title, styles):
    return [
        Paragraph(label.upper(), styles["section_label"]),
        Paragraph(title, styles["section_title"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=10, spaceBefore=0),
    ]


def _category_card(cat_key, cat_info, styles):
    name = cat_key.replace("_", " ").title()
    score = float(cat_info.get("score", 0))
    score_bg, score_text = _score_colors(score)
    summary = _truncate(cat_info.get("summary"), 135)
    issue = _truncate((cat_info.get("top_issues") or ["No issue surfaced"])[0], 85)
    praise = _truncate((cat_info.get("top_praises") or ["No standout praise surfaced"])[0], 85)

    header = Table(
        [[
            Paragraph(name, styles["category_title"]),
            _pill(f"{score:.1f} / 5", score_bg, score_text, styles, 0.95 * inch),
        ]],
        colWidths=[3.95 * inch, 1.1 * inch],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    body = Table(
        [
            [header],
            [Paragraph(summary, styles["body"])],
            [_score_bar_flowable(score, styles)],
            [Paragraph(f"<b>Primary issue:</b> {issue}", styles["small"])],
            [Paragraph(f"<b>Primary strength:</b> {praise}", styles["small"])],
        ],
        colWidths=[6.0 * inch],
    )
    body.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return body


def _item_table(items, styles):
    data = [[
        Paragraph("Item", styles["card_label"]),
        Paragraph("Sentiment", styles["card_label"]),
        Paragraph("Mentions", styles["card_label"]),
    ]]
    for item in items[:5]:
        data.append(
            [
                Paragraph(_truncate(item.get("item"), 32), styles["body"]),
                Paragraph(str(item.get("sentiment", "")).title(), styles["body"]),
                Paragraph(str(item.get("mentions", 0)), styles["body"]),
            ]
        )

    table = Table(data, colWidths=[3.9 * inch, 1.2 * inch, 0.9 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), MIST),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#FCFAF6")]),
            ]
        )
    )
    return table


def _numbered_list(title, items, styles):
    content = []
    content.extend(_section_header("Snapshot", title, styles))
    for index, item in enumerate(items, start=1):
        content.append(Paragraph(f"<b>{index}.</b> {_truncate(item, 220)}", styles["list_item"]))
        content.append(Spacer(1, 4))
    content.append(Spacer(1, 6))
    return content


def _page_background(canvas, _doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.rect(0.78 * inch, PAGE_HEIGHT - 0.82 * inch, 1.05 * inch, 0.08 * inch, stroke=0, fill=1)
    canvas.restoreState()


def generate_pdf_report(analysis, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)

    styles = _build_styles()
    brand = analysis["brand_name"]
    display_brand = brand.replace(" - ", "<br/>")
    date_str = datetime.now().strftime("%B %d, %Y")
    safe_name = brand.replace(" ", "_").replace("-", "").replace("/", "")
    filename = f"{output_dir}/{safe_name}_Report_{datetime.now().strftime('%Y%m%d')}.pdf"

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=0.78 * inch,
        leftMargin=0.78 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.72 * inch,
    )

    story = []

    sentiment_bg, sentiment_text = _sentiment_colors(analysis.get("overall_sentiment"))
    risk_bg, risk_text = _risk_colors(analysis.get("rating_risk"))

    hero = Table(
        [
            [Paragraph("REVIEW INTELLIGENCE REPORT", styles["eyebrow"])],
            [Paragraph(display_brand, styles["hero_title"])],
            [
                Paragraph(
                    f"{date_str}<br/>Performance brief built from {analysis['total_reviews_analyzed']} customer reviews.",
                    styles["hero_meta"],
                )
            ],
            [Paragraph(
                f"<b>This week's priority action:</b> {_truncate(analysis.get('week_priority_action'), 180)}",
                styles["hero_body"],
            )],
        ],
        colWidths=[6.0 * inch],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 0, NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (0, 0), 18),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4),
                ("BOTTOMPADDING", (0, 2), (0, 2), 10),
                ("BOTTOMPADDING", (0, 3), (0, 3), 18),
            ]
        )
    )
    story.append(hero)
    story.append(Spacer(1, 14))

    summary_row = Table(
        [[
            _pill(str(analysis["overall_sentiment"]), sentiment_bg, sentiment_text, styles, 1.45 * inch),
            _pill(f"Risk: {analysis['rating_risk']}", risk_bg, risk_text, styles, 1.45 * inch),
            Paragraph(f"<b>Average rating:</b> {analysis['average_rating']:.1f} / 5", styles["small"]),
        ]],
        colWidths=[1.6 * inch, 1.6 * inch, 2.8 * inch],
    )
    summary_row.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ]
        )
    )
    story.append(summary_row)
    story.append(Spacer(1, 22))

    story.extend(_section_header("Overview", "Executive Snapshot", styles))
    metrics = [
        _metric_card("Overall sentiment", str(analysis["overall_sentiment"]).title(), "Current customer mood", styles),
        _metric_card("Average rating", f"{analysis['average_rating']:.1f}/5", "Public review average", styles),
        _metric_card("Reviews analyzed", str(analysis["total_reviews_analyzed"]), "Sample powering this brief", styles),
        _metric_card("Rating risk", str(analysis["rating_risk"]).title(), "Likelihood of downward pressure", styles),
    ]
    metric_grid = Table([metrics[:2], metrics[2:]], colWidths=[3.0 * inch, 3.0 * inch])
    metric_grid.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(metric_grid)
    story.append(Spacer(1, 18))

    story.extend(_section_header("Breakdown", "Category Performance", styles))
    for cat_key, cat_info in analysis["categories"].items():
        story.append(_category_card(cat_key, cat_info, styles))
        story.append(Spacer(1, 10))

    if analysis.get("most_mentioned_items"):
        story.append(Spacer(1, 4))
        story.extend(_section_header("Menu", "Most Mentioned Items", styles))
        story.append(_item_table(analysis["most_mentioned_items"], styles))
        story.append(Spacer(1, 18))

    story.extend(_numbered_list("Top 3 Urgent Issues", analysis["top_3_urgent_issues"], styles))
    story.extend(_numbered_list("Top 3 Strengths", analysis["top_3_strengths"], styles))

    closing = Table(
        [
            [Paragraph("CONFIDENTIAL INTERNAL USE", styles["section_label"])],
            [Paragraph(f"Generated by Vansh Pandita for {brand}.", styles["small_center"])],
        ],
        colWidths=[6.0 * inch],
    )
    closing.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), MIST),
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, 0), (0, 0), 4),
                ("BOTTOMPADDING", (0, 1), (0, 1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(closing)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"{brand} | {date_str}", styles["footer"]))

    doc.build(story, onFirstPage=_page_background, onLaterPages=_page_background)
    print(f"\nReport saved: {filename}")
    return filename

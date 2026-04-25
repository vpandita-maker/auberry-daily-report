import json
import os

import anthropic
from dotenv import load_dotenv

from scrapers.google import get_google_reviews

load_dotenv()


def _compute_snapshot(reviews, competitor_name):
    if not reviews:
        return None
    ratings = [r["rating"] for r in reviews if r.get("rating") is not None]
    if not ratings:
        return None
    avg_rating = round(sum(ratings) / len(ratings), 1)
    positive = sum(1 for r in ratings if r >= 4)
    sentiment_pct = round((positive / len(ratings)) * 100)
    return {
        "name": competitor_name,
        "avg_rating": avg_rating,
        "review_count": len(reviews),
        "sentiment_pct": sentiment_pct,
        "reviews": reviews,
    }


def get_competitor_snapshots(competitors):
    snapshots = []
    for competitor in competitors:
        name = competitor.get("name", "")
        place_id = competitor.get("place_id", "").strip()
        if not place_id:
            print(f"Skipping competitor {name!r}: no place_id configured.")
            continue
        try:
            print(f"Fetching reviews for competitor: {name}")
            reviews = get_google_reviews(place_id)
            snapshot = _compute_snapshot(reviews, name)
            if snapshot:
                snapshots.append(snapshot)
                print(f"Competitor snapshot ready: {name} — {snapshot['avg_rating']}/5 from {snapshot['review_count']} reviews")
        except Exception as exc:
            print(f"Skipped competitor {name!r}: {exc}")
    return snapshots


def analyze_competitive_position(auberry_analysis, competitor_snapshots):
    if not competitor_snapshots:
        return {}

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    auberry_summary = {
        "avg_rating": auberry_analysis.get("average_rating", 0),
        "categories": {
            k: {"score": float((v or {}).get("score", 0) or 0), "summary": str((v or {}).get("summary", ""))}
            for k, v in (auberry_analysis.get("categories") or {}).items()
        },
        "top_3_strengths": auberry_analysis.get("top_3_strengths") or [],
        "top_3_urgent_issues": auberry_analysis.get("top_3_urgent_issues") or [],
    }

    competitor_text = ""
    for snap in competitor_snapshots:
        name = snap["name"]
        sample_reviews = "\n".join(
            f"  - {r.get('rating')}/5: {str(r.get('text', ''))[:200]}"
            for r in snap["reviews"][:5]
        )
        competitor_text += (
            f"\n\n{name}: {snap['avg_rating']}/5 avg, "
            f"{snap['sentiment_pct']}% positive, "
            f"{snap['review_count']} reviews sampled\n"
            f"Sample reviews:\n{sample_reviews}"
        )

    brand = str(auberry_analysis.get("brand_name", "Auberry The Bake Shop"))

    prompt = f"""You are a competitive intelligence analyst for "{brand}", an Indian bakery/café chain with multiple outlets in Hyderabad.

Auberry's latest performance data:
{json.dumps(auberry_summary, indent=2)}

Competitor data from Google Reviews:{competitor_text}

Analyze the competitive landscape and return ONLY a valid JSON object. No preamble, no explanation.

Requirements:
- Be specific — name the exact competitor when noting an advantage or gap.
- Base scores on available data; if a category has no direct signal, use the overall avg_rating.
- Gap field must be exactly "ahead", "behind", or "tied".

{{
  "summary": "one-sentence competitive positioning of Auberry vs the sampled competitors",
  "auberry_advantages": ["specific strength Auberry has over competitors, name the competitor"],
  "competitor_advantages": ["specific area a named competitor outperforms Auberry"],
  "category_comparison": {{
    "food_quality": {{"auberry_score": 0.0, "competitor_avg": 0.0, "gap": "ahead", "note": "one sentence"}},
    "service": {{"auberry_score": 0.0, "competitor_avg": 0.0, "gap": "ahead", "note": "one sentence"}},
    "value_for_money": {{"auberry_score": 0.0, "competitor_avg": 0.0, "gap": "ahead", "note": "one sentence"}},
    "coffee_quality": {{"auberry_score": 0.0, "competitor_avg": 0.0, "gap": "ahead", "note": "one sentence"}}
  }},
  "strategic_implication": "two sentences on the single most important competitive action Auberry should take"
}}"""

    print("Analyzing competitive position...")
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
    print("Competitive analysis complete.")
    return result

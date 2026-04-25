import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

def analyze_reviews(reviews, brand_name):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    reviews_text = ""
    for i, r in enumerate(reviews):
        reviews_text += (
            f"{i+1}. [{r['source']}] "
            f"Date: {r.get('date_exact') or r.get('date') or 'Unknown'} | "
            f"Location: {r.get('outlet_address', 'Unknown')} | "
            f"Rating: {r['rating']}/5 | "
            f"{r['text'][:500]}\n\n"
        )
    
    prompt = f"""You are analyzing customer reviews for "{brand_name}", an Indian bakery/cafe brand with multiple outlets.

Analyze these reviews and return ONLY a valid JSON object. No preamble, no explanation, just JSON.

Requirements:
- Treat this as one combined portfolio-wide report, not separate branch mini-reports.
- Focus only on today's reviews provided in the input.
- Keep the output concise, strategic, and executive-friendly.
- Whenever praise or criticism clearly belongs to a specific outlet, mention the exact outlet and/or location in the wording.
- Use the review dates provided to ground the analysis in time; do not invent dates.
- Give exactly 6 highly specific recommendations with measurable success metrics.
- Each recommendation must name the exact outlet, item, category, staff behavior, or review pattern that triggered it when available.
- Do not give generic advice like "improve service" or "promote products"; specify the action, target location/item, owner behavior, and timing inside the action text.
- Do not use vague phrases like "some outlets" when an outlet/location is identifiable from the input.

{{
    "brand_name": "{brand_name}",
    "overall_sentiment": "positive or neutral or negative",
    "average_rating": 0.0,
    "total_reviews_analyzed": 0,
    "categories": {{
        "food_quality": {{"score": 0.0, "summary": "one sentence with outlet names if relevant", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "service": {{"score": 0.0, "summary": "one sentence with outlet names if relevant", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "ambiance": {{"score": 0.0, "summary": "one sentence with outlet names if relevant", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "value_for_money": {{"score": 0.0, "summary": "one sentence with outlet names if relevant", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "coffee_quality": {{"score": 0.0, "summary": "one sentence with outlet names if relevant", "top_issues": ["issue1"], "top_praises": ["praise1"]}}
    }},
    "most_mentioned_items": [
        {{"item": "item name", "sentiment": "positive or negative", "mentions": 0}}
    ],
    "top_3_urgent_issues": ["issue with outlet/location if identifiable", "issue2", "issue3"],
    "top_3_strengths": ["strength with outlet/location if identifiable", "strength2", "strength3"],
    "rating_risk": "low or medium or high",
    "top_6_recommendations": [
        {{
            "title": "short strategic action",
            "location_focus": "specific outlet/location or portfolio-wide",
            "action": "specific next steps including timing, owner behavior, and rollout detail",
            "success_metric": "numeric target or measurable KPI"
        }}
    ]
}}

Reviews to analyze:
{reviews_text}"""

    print("Sending to Claude for analysis...")
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2800,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    analysis = json.loads(raw)
    print("Analysis complete!\n")
    return analysis

import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

def analyze_reviews(reviews, brand_name):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    reviews_text = ""
    for i, r in enumerate(reviews):
        reviews_text += f"{i+1}. [{r['source']}] Rating: {r['rating']}/5 | {r['text'][:400]}\n\n"
    
    prompt = f"""You are analyzing customer reviews for "{brand_name}", an Indian bakery/cafe brand.

Analyze these reviews and return ONLY a valid JSON object. No preamble, no explanation, just JSON.

{{
    "brand_name": "{brand_name}",
    "overall_sentiment": "positive or neutral or negative",
    "average_rating": 0.0,
    "total_reviews_analyzed": 0,
    "categories": {{
        "food_quality": {{"score": 0.0, "summary": "one sentence", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "service": {{"score": 0.0, "summary": "one sentence", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "ambiance": {{"score": 0.0, "summary": "one sentence", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "value_for_money": {{"score": 0.0, "summary": "one sentence", "top_issues": ["issue1"], "top_praises": ["praise1"]}},
        "coffee_quality": {{"score": 0.0, "summary": "one sentence", "top_issues": ["issue1"], "top_praises": ["praise1"]}}
    }},
    "most_mentioned_items": [
        {{"item": "item name", "sentiment": "positive or negative", "mentions": 0}}
    ],
    "top_3_urgent_issues": ["issue1", "issue2", "issue3"],
    "top_3_strengths": ["strength1", "strength2", "strength3"],
    "rating_risk": "low or medium or high",
    "week_priority_action": "One specific actionable recommendation"
}}

Reviews to analyze:
{reviews_text}"""

    print("Sending to Claude for analysis...")
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    analysis = json.loads(raw)
    print("Analysis complete!\n")
    return analysis

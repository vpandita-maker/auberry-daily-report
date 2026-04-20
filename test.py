from scrapers.google import get_google_reviews
from analyzer.ai_analysis import analyze_reviews
from reports.pdf_generator import generate_pdf_report

place_id = "ChIJtVnlYUyTyzsRqFxHmIIV7Sc"
brand_name = "Auberry The Bake Shop - Kondapur"

reviews = get_google_reviews(place_id)

if reviews:
    analysis = analyze_reviews(reviews, brand_name)
    pdf_path = generate_pdf_report(analysis)
    print(f"\nDone! Open the file: {pdf_path}")
else:
    print("No reviews to analyze")

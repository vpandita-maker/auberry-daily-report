import os
from pathlib import Path

from send_report import build_combined_report, load_outlets, publish_dashboard_site


def main():
    html_path, analysis, failed_outlets = build_combined_report(load_outlets())
    site_index = publish_dashboard_site(html_path, analysis=analysis)

    print(f"Published dashboard site to {site_index}")
    print(f"Source dashboard file: {Path(html_path).resolve()}")

    if failed_outlets:
        print("Outlets skipped during publish:")
        for failed in failed_outlets:
            print(f"- {failed['name']}: {failed['error']}")

    dashboard_url = os.getenv("DASHBOARD_URL", "").strip()
    if dashboard_url:
        print(f"Configured dashboard URL: {dashboard_url}")


if __name__ == "__main__":
    main()

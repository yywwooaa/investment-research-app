from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import _with_local_overrides, provider, settings


def main() -> None:
    result = provider.refresh()
    records = [_with_local_overrides(record) for record in provider.list_companies()]
    output_dir = settings.local_data_dir / "weekly_updates"
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    payload = {
        "date": today,
        "refresh": result.model_dump(mode="json"),
        "companies": [
            {
                "ticker": record.profile.ticker,
                "name": record.profile.name,
                "recommendation": record.recommendation.model_dump(mode="json"),
                "market": record.market.model_dump(mode="json"),
                "thesis": {
                    "one_liner": record.thesis.one_liner,
                    "variant_view": record.thesis.variant_view,
                    "risks": record.thesis.risks,
                    "watch_items": record.thesis.watch_items,
                },
                "news": [item.model_dump(mode="json") for item in record.news],
            }
            for record in records
        ],
    }

    json_path = output_dir / f"{today}.json"
    markdown_path = output_dir / f"{today}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Weekly Research Update - {today}",
        "",
        f"Refresh source: {result.source}",
        result.message,
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## {record.profile.ticker} - {record.profile.name}",
                f"- Recommendation: {record.recommendation.rating} ({record.recommendation.confidence})",
                f"- Score: {record.recommendation.score:.0f}",
                f"- Source status: {record.recommendation.source_status}",
                f"- Rationale: {record.recommendation.rationale}",
                "- News:",
            ]
        )
        lines.extend(f"  - {item.published_at} / {item.source}: {item.title}" for item in record.news)
        lines.append("")

    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()

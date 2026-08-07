"""실제 넥슨 API 응답을 tests/fixtures/ 에 저장한다. 개발 중 한 번만 실행하면 된다.

사용법:
    $env:NEXON_API_KEY = "..."
    .venv/Scripts/python scripts/fetch_fixtures.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.api.nexon.com"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def fetch(path: str, params: dict | None = None) -> dict:
    response = requests.get(
        BASE_URL + path,
        headers={"x-nxopen-api-key": os.environ["NEXON_API_KEY"]},
        params=params or {},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    if "NEXON_API_KEY" not in os.environ:
        print("NEXON_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    FIXTURES.mkdir(parents=True, exist_ok=True)

    listing = fetch("/maplestory/v1/notice-event")
    (FIXTURES / "notice_event_list.json").write_text(
        json.dumps(listing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("목록 응답 최상위 키:", list(listing.keys()))

    items = next(v for v in listing.values() if isinstance(v, list))
    print("목록 항목 키:", list(items[0].keys()))

    notice_id = items[0][next(k for k in items[0] if "id" in k.lower())]
    detail = fetch("/maplestory/v1/notice-event/detail", {"notice_id": notice_id})
    (FIXTURES / "notice_event_detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("상세 응답 키:", list(detail.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

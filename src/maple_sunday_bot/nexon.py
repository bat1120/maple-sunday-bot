"""넥슨 오픈 API 클라이언트. HTTP 경계를 이 파일 안에만 둔다."""

from __future__ import annotations

import sys
import time
from typing import Any

import requests

from maple_sunday_bot.notice import Notice

BASE_URL = "https://open.api.nexon.com"
API_KEY_HEADER = "x-nxopen-api-key"
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}


class NexonApiError(Exception):
    """넥슨 API 호출이 최종적으로 실패했을 때."""


class NexonClient:
    def __init__(self, api_key: str, session=None, sleep=time.sleep):
        self._api_key = api_key
        self._session = session if session is not None else requests.Session()
        self._sleep = sleep

    def get_event_notices(self) -> list[Notice]:
        """이벤트 공지 목록을 최신순으로 가져온다.

        항목 하나가 깨져 있어도(필드 누락, 타입 이상 등) 전체 목록을 포기하지
        않는다 — 관심 없는 이벤트의 이상한 항목 하나 때문에 진짜 썬데이 공지를
        놓치면 안 된다. 깨진 항목은 건너뛰고 stderr에 남긴다.
        """
        data = self._get("/maplestory/v1/notice-event")
        items = data.get("event_notice") or []
        notices = []
        for item in items:
            try:
                notices.append(_to_notice(item))
            except (KeyError, TypeError, ValueError) as exc:
                notice_id = item.get("notice_id") if isinstance(item, dict) else None
                print(
                    f"공지 항목 파싱 실패(notice_id={notice_id!r}): {exc}",
                    file=sys.stderr,
                )
        return notices

    def get_event_notice_detail(self, notice_id: int) -> str:
        """공지 본문 HTML을 가져온다. 본문이 비어 있으면 빈 문자열."""
        data = self._get(
            "/maplestory/v1/notice-event/detail", {"notice_id": notice_id}
        )
        return data.get("contents") or ""

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """재시도를 포함한 GET. 지수 백오프로 1초, 2초 쉰다.

        상태 코드가 200이어도 본문이 올바른 JSON이 아니면(ValueError) 다른
        재시도 가능한 실패와 같은 경로를 탄다 — 재시도 후에도 계속 실패하면
        NexonApiError로 감싸 던진다.
        """
        url = BASE_URL + path
        headers = {API_KEY_HEADER: self._api_key}
        last_error = ""

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._session.get(
                    url, headers=headers, params=params or {}, timeout=TIMEOUT_SECONDS
                )
                if response.status_code == 200:
                    return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = f"요청 실패: {exc}"
            else:
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUS:
                    break

            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(2.0**attempt)

        raise NexonApiError(f"{url} 호출 실패 — {last_error}")


def _to_notice(item: dict[str, Any]) -> Notice:
    return Notice(
        notice_id=int(item["notice_id"]),
        title=item.get("title") or "",
        url=item.get("url") or "",
        date=item.get("date") or "",
        date_event_start=item.get("date_event_start"),
        date_event_end=item.get("date_event_end"),
    )

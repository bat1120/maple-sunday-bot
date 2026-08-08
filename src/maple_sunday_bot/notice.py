"""공지 데이터 모델과 순수 파싱 로직. 네트워크를 타지 않는다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

# 제목 표기가 "썬데이 메이플" / "스페셜 썬데이 메이플" / "썬데이메이플" 로 갈려서
# 공백을 모두 지운 뒤 부분 문자열로 확인한다.
_SUNDAY_KEYWORD = "썬데이메이플"


@dataclass(frozen=True)
class Notice:
    """이벤트 공지 하나."""

    notice_id: int
    title: str
    url: str
    date: str
    date_event_start: str | None
    date_event_end: str | None


def is_sunday(title: str) -> bool:
    """제목이 썬데이 메이플 공지인지 판별한다."""
    return _SUNDAY_KEYWORD in re.sub(r"\s+", "", title)


_IMG_SRC = re.compile(r"""<img[^>]+?src\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def extract_images(html: str) -> list[str]:
    """본문 HTML에서 이미지 URL을 등장 순서대로, 중복 없이 뽑는다."""
    urls: list[str] = []
    for raw in _IMG_SRC.findall(html or ""):
        url = unescape(raw.strip())
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith(("http://", "https://")):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _to_date(value: str) -> str:
    """'2026-08-09T00:00+09:00' -> '2026.08.09'. 넥슨 응답은 항상 ISO8601이라 앞 10자만 쓴다."""
    return value[:10].replace("-", ".")


def event_period(notice: Notice) -> str:
    """디스코드에 보여줄 이벤트 기간 문자열. 정보가 불완전하면 빈 문자열."""
    if not notice.date_event_start or not notice.date_event_end:
        return ""
    return f"{_to_date(notice.date_event_start)} ~ {_to_date(notice.date_event_end)}"

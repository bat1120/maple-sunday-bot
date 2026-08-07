"""공지 데이터 모델과 순수 파싱 로직. 네트워크를 타지 않는다."""

from __future__ import annotations

import re
from dataclasses import dataclass

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

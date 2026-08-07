"""이미 알림을 보낸 공지 ID를 파일에 기록한다. 목록은 최신이 앞에 온다."""

from __future__ import annotations

import json
from pathlib import Path

MAX_SEEN = 100


def load_seen(path: Path) -> list[int]:
    """기록된 notice_id 목록을 읽는다. 파일이 없거나 깨졌으면 빈 목록."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    seen = data.get("seen") if isinstance(data, dict) else None
    if not isinstance(seen, list):
        return []
    return [item for item in seen if isinstance(item, int)]


def save_seen(path: Path, seen: list[int]) -> None:
    """최신 MAX_SEEN개만 남겨 저장한다. 깃 diff가 보기 좋도록 들여쓰기와 끝 개행을 넣는다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"seen": seen[:MAX_SEEN]}, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")

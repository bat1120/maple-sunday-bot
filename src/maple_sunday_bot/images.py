"""이미지 URL을 업로드 가능한 조각들로 바꾼다.

디스코드도, 공지 데이터도 모른다. 책임은 하나: 다운로드하고 필요하면 세로로 자른다.
"""

from __future__ import annotations

import io
import math
import re

import requests
from PIL import Image

MAX_ASPECT_RATIO = 1.2  # 조각 높이는 가로의 1.2배까지
DOWNLOAD_TIMEOUT_SECONDS = 30

_UNSAFE_STEM_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


class ImageError(Exception):
    """이미지를 받아오거나 분할하지 못했을 때."""


def _safe_stem(stem: str) -> str:
    cleaned = _UNSAFE_STEM_CHARS.sub("_", stem).strip("_")
    return cleaned or "image"


def slice_image(data: bytes, stem: str) -> list[tuple[str, bytes]]:
    """이미지 바이트를 세로로 균등 분할한다. (파일명, PNG 바이트) 목록을 반환한다."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ImageError(f"이미지 디코드 실패: {type(exc).__name__}") from exc

    safe_stem = _safe_stem(stem)
    width, height = image.size
    is_animated = getattr(image, "n_frames", 1) > 1

    if is_animated or height <= width * MAX_ASPECT_RATIO:
        # 애니메이션은 자르면 죽고, 짧은 이미지는 자를 필요가 없다.
        # 둘 다 재인코딩 없이 원본 바이트를 그대로 담아 돌려준다.
        return [(f"{safe_stem}_01.png", data)]

    parts = math.ceil(height / (width * MAX_ASPECT_RATIO))
    piece_height = math.ceil(height / parts)

    pieces: list[tuple[str, bytes]] = []
    for i in range(parts):
        top = i * piece_height
        if top >= height:
            break
        bottom = min(top + piece_height, height)
        crop = image.crop((0, top, width, bottom))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
        pieces.append((f"{safe_stem}_{i + 1:02d}.png", buffer.getvalue()))

    return pieces


def fetch_and_slice(
    url: str, stem: str, session: requests.Session | None = None
) -> list[tuple[str, bytes]]:
    """url에서 이미지를 받아 slice_image에 넘긴다."""
    sess = session if session is not None else requests.Session()

    try:
        response = sess.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ImageError(f"이미지 다운로드 실패({url}): {type(exc).__name__}") from exc

    status_code = getattr(response, "status_code", None)
    content = getattr(response, "content", b"")
    if status_code != 200 or not content:
        raise ImageError(f"이미지 다운로드 실패({url}): HTTP {status_code}")

    return slice_image(content, stem)

import io
import math

import pytest
import requests
from PIL import Image

from maple_sunday_bot.images import (
    DOWNLOAD_TIMEOUT_SECONDS,
    MAX_ASPECT_RATIO,
    ImageError,
    fetch_and_slice,
    slice_image,
)


def _png_bytes(width, height, color="white"):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _animated_gif_bytes(width, height):
    frame1 = Image.new("RGB", (width, height), "red")
    frame2 = Image.new("RGB", (width, height), "blue")
    buffer = io.BytesIO()
    frame1.save(buffer, format="GIF", save_all=True, append_images=[frame2])
    return buffer.getvalue()


def test_세로로_긴_이미지는_예상_조각_수로_균등_분할된다():
    width, height = 876, 3666
    data = _png_bytes(width, height)

    pieces = slice_image(data, "notice")

    expected_parts = math.ceil(height / (width * MAX_ASPECT_RATIO))
    assert len(pieces) == expected_parts

    total_height = 0
    for _, blob in pieces:
        piece = Image.open(io.BytesIO(blob))
        assert piece.width == width
        total_height += piece.height
    assert total_height == height


def test_짧은_이미지는_자르지_않고_원본_바이트를_그대로_반환한다():
    data = _png_bytes(100, 120)  # 120 <= 100 * 1.2

    pieces = slice_image(data, "notice")

    assert len(pieces) == 1
    name, blob = pieces[0]
    assert blob == data  # 재인코딩 없이 원본 바이트 그대로
    assert name == "notice_01.png"


def test_애니메이션_이미지는_자르지_않고_1개로_반환된다():
    # 세로로 길어서(500 > 100 * 1.2) 애니메이션 검사가 없으면 잘렸을 크기
    data = _animated_gif_bytes(100, 500)

    pieces = slice_image(data, "notice")

    assert len(pieces) == 1
    assert pieces[0][1] == data


def test_이미지가_아닌_바이트는_ImageError():
    with pytest.raises(ImageError):
        slice_image(b"this is not an image", "notice")


def test_파일명이_stem_밑줄_두자리_인덱스_점png_형식이다():
    width, height = 876, 3666
    data = _png_bytes(width, height)

    pieces = slice_image(data, "1356_01")

    names = [name for name, _ in pieces]
    assert names == [f"1356_01_{i:02d}.png" for i in range(1, len(pieces) + 1)]


class _FakeGetSession:
    """fetch_and_slice가 사용할 가짜 session. get()만 흉내낸다."""

    def __init__(self, status_code=200, content=b"", raise_exc=None):
        self.status_code = status_code
        self.content = content
        self.raise_exc = raise_exc
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if self.raise_exc is not None:
            raise self.raise_exc

        status_code = self.status_code
        content = self.content

        class _Response:
            pass

        response = _Response()
        response.status_code = status_code
        response.content = content
        return response


def test_fetch_and_slice는_200이_아니면_ImageError():
    session = _FakeGetSession(status_code=404, content=b"not found")

    with pytest.raises(ImageError):
        fetch_and_slice("https://file.nexon.com/a.png", "notice", session)

    assert session.calls[0]["timeout"] == DOWNLOAD_TIMEOUT_SECONDS


def test_fetch_and_slice는_다운로드_예외에서_ImageError():
    session = _FakeGetSession(raise_exc=requests.ConnectionError("boom"))

    with pytest.raises(ImageError):
        fetch_and_slice("https://file.nexon.com/a.png", "notice", session)


def test_fetch_and_slice_예외_메시지에_원본_예외_문자열이_그대로_들어가지_않는다():
    secret = "S3cr3tDetailInExceptionString"
    session = _FakeGetSession(raise_exc=requests.ConnectionError(secret))

    with pytest.raises(ImageError) as excinfo:
        fetch_and_slice("https://file.nexon.com/a.png", "notice", session)

    message = str(excinfo.value)
    assert secret not in message
    assert "ConnectionError" in message


def test_fetch_and_slice_성공하면_slice_image_결과를_그대로_돌려준다():
    data = _png_bytes(100, 120)
    session = _FakeGetSession(status_code=200, content=data)

    pieces = fetch_and_slice("https://file.nexon.com/a.png", "notice", session)

    assert pieces == [("notice_01.png", data)]

"""디스코드 웹훅 페이로드 조립과 전송.

디스코드 임베드는 하나당 이미지가 한 장만 보이므로, 이미지 개수만큼 임베드를 만든다.
한 메시지에 임베드는 10개까지라 넘치면 메시지를 나눈다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import requests

from maple_sunday_bot.notice import Notice, event_period

MAX_EMBEDS_PER_MESSAGE = 10
MAX_FILES_PER_MESSAGE = 10
MAX_BYTES_PER_MESSAGE = 7 * 1024 * 1024  # 디스코드 제한보다 보수적으로
EMBED_COLOR = 0xFF8C00
TIMEOUT_SECONDS = 15
OK_STATUS = {200, 204}
RATE_LIMIT_STATUS = 429
MAX_ATTEMPTS_PER_MESSAGE = 3
DEFAULT_RETRY_AFTER_SECONDS = 1.0


class WebhookError(Exception):
    """디스코드 웹훅 전송이 실패했을 때."""


@dataclass(frozen=True)
class Message:
    """웹훅으로 보낼 메시지 하나. 첨부가 있으면 multipart로, 없으면 json으로 나간다."""

    payload: dict
    files: tuple[tuple[str, bytes], ...] = field(default_factory=tuple)


def _head_embed(notice: Notice) -> dict:
    head: dict = {
        "title": notice.title,
        "url": notice.url,
        "color": EMBED_COLOR,
    }
    period = event_period(notice)
    if period:
        head["description"] = period
    return head


def build_messages(notice: Notice, images: list[str]) -> list[Message]:
    """공지 하나를 보내기 위한 웹훅 메시지 목록을 만든다 (URL 임베드 방식)."""
    head = _head_embed(notice)
    if images:
        head["image"] = {"url": images[0]}

    embeds = [head] + [{"image": {"url": url}} for url in images[1:]]

    return [
        Message(payload={"embeds": embeds[i : i + MAX_EMBEDS_PER_MESSAGE]})
        for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)
    ]


def build_attachment_messages(
    notice: Notice, slices: list[tuple[str, bytes]]
) -> list[Message]:
    """공지 하나를 보내기 위한 웹훅 메시지 목록을 만든다 (첨부 방식).

    첫 메시지 payload에만 임베드(제목/링크/색/기간)를 싣는다. 이미지는 첨부로 가므로
    임베드에 image 키는 넣지 않는다. 첨부는 순서를 지키며 메시지당 개수 상한
    (MAX_FILES_PER_MESSAGE)과 용량 상한(MAX_BYTES_PER_MESSAGE) 중 먼저 걸리는 쪽에서
    다음 메시지로 넘어간다.
    """
    for name, blob in slices:
        if len(blob) > MAX_BYTES_PER_MESSAGE:
            raise ValueError(
                f"조각 '{name}'({len(blob)} bytes)이 메시지당 용량 상한"
                f"({MAX_BYTES_PER_MESSAGE} bytes)을 단독으로 넘습니다."
            )

    head_embed = _head_embed(notice)

    if not slices:
        return [Message(payload={"embeds": [head_embed]})]

    batches: list[list[tuple[str, bytes]]] = []
    current: list[tuple[str, bytes]] = []
    current_bytes = 0
    for item in slices:
        _, blob = item
        exceeds_count = len(current) + 1 > MAX_FILES_PER_MESSAGE
        exceeds_bytes = current_bytes + len(blob) > MAX_BYTES_PER_MESSAGE
        if current and (exceeds_count or exceeds_bytes):
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(item)
        current_bytes += len(blob)
    batches.append(current)

    return [
        Message(
            payload={"embeds": [head_embed]} if i == 0 else {},
            files=tuple(batch),
        )
        for i, batch in enumerate(batches)
    ]


def send(webhook_url: str, messages: list[Message], session=None, sleep=time.sleep) -> None:
    """메시지를 순서대로 전송한다. 하나라도 실패하면 WebhookError.

    디스코드 웹훅은 초당 요청 수를 제한한다. 429가 오면 응답의 Retry-After
    (초 단위, 소수 가능)만큼 쉬었다가 같은 메시지를 다시 보낸다. 메시지당
    최대 MAX_ATTEMPTS_PER_MESSAGE번까지만 시도하고, 그래도 안 되면 포기한다.
    이건 같은 회차 안에서의 재시도일 뿐이다 — 회차를 넘어선 이어보내기는
    하지 않는다(드물게 중복 발송을 허용하는 게 설계다).

    msg.files가 비어 있으면 지금처럼 json으로, 있으면 multipart(payload_json + files)로 보낸다.
    """
    session = session if session is not None else requests.Session()

    for index, message in enumerate(messages, start=1):
        for attempt in range(1, MAX_ATTEMPTS_PER_MESSAGE + 1):
            try:
                if message.files:
                    response = session.post(
                        webhook_url,
                        data={"payload_json": json.dumps(message.payload)},
                        files={
                            f"files[{i}]": (name, blob, "image/png")
                            for i, (name, blob) in enumerate(message.files)
                        },
                        timeout=TIMEOUT_SECONDS,
                    )
                else:
                    response = session.post(
                        webhook_url, json=message.payload, timeout=TIMEOUT_SECONDS
                    )
            except requests.RequestException as exc:
                raise WebhookError(
                    f"{index}번째 메시지 전송 실패: {type(exc).__name__}"
                ) from exc

            if response.status_code in OK_STATUS:
                break

            if (
                response.status_code == RATE_LIMIT_STATUS
                and attempt < MAX_ATTEMPTS_PER_MESSAGE
            ):
                sleep(_retry_after_seconds(response))
                continue

            raise WebhookError(
                f"{index}번째 메시지 전송 실패: HTTP {response.status_code}"
            )


def _retry_after_seconds(response) -> float:
    """429 응답의 Retry-After 헤더를 초 단위 float로. 없거나 이상하면 기본값."""
    headers = getattr(response, "headers", None)
    value = headers.get("Retry-After") if headers else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS

"""디스코드 웹훅 페이로드 조립과 전송.

디스코드 임베드는 하나당 이미지가 한 장만 보이므로, 이미지 개수만큼 임베드를 만든다.
한 메시지에 임베드는 10개까지라 넘치면 메시지를 나눈다.
"""

from __future__ import annotations

import time

import requests

from maple_sunday_bot.notice import Notice, event_period

MAX_EMBEDS_PER_MESSAGE = 10
EMBED_COLOR = 0xFF8C00
TIMEOUT_SECONDS = 15
OK_STATUS = {200, 204}
RATE_LIMIT_STATUS = 429
MAX_ATTEMPTS_PER_MESSAGE = 3
DEFAULT_RETRY_AFTER_SECONDS = 1.0


class WebhookError(Exception):
    """디스코드 웹훅 전송이 실패했을 때."""


def build_messages(notice: Notice, images: list[str]) -> list[dict]:
    """공지 하나를 보내기 위한 웹훅 메시지 페이로드 목록을 만든다."""
    head: dict = {
        "title": notice.title,
        "url": notice.url,
        "color": EMBED_COLOR,
    }
    period = event_period(notice)
    if period:
        head["description"] = period
    if images:
        head["image"] = {"url": images[0]}

    embeds = [head] + [{"image": {"url": url}} for url in images[1:]]

    return [
        {"embeds": embeds[i : i + MAX_EMBEDS_PER_MESSAGE]}
        for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)
    ]


def send(webhook_url: str, messages: list[dict], session=None, sleep=time.sleep) -> None:
    """메시지를 순서대로 전송한다. 하나라도 실패하면 WebhookError.

    디스코드 웹훅은 초당 요청 수를 제한한다. 429가 오면 응답의 Retry-After
    (초 단위, 소수 가능)만큼 쉬었다가 같은 메시지를 다시 보낸다. 메시지당
    최대 MAX_ATTEMPTS_PER_MESSAGE번까지만 시도하고, 그래도 안 되면 포기한다.
    이건 같은 회차 안에서의 재시도일 뿐이다 — 회차를 넘어선 이어보내기는
    하지 않는다(드물게 중복 발송을 허용하는 게 설계다).
    """
    session = session if session is not None else requests.Session()

    for index, message in enumerate(messages, start=1):
        for attempt in range(1, MAX_ATTEMPTS_PER_MESSAGE + 1):
            try:
                response = session.post(webhook_url, json=message, timeout=TIMEOUT_SECONDS)
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

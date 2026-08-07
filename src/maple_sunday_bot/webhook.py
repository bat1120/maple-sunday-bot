"""디스코드 웹훅 페이로드 조립과 전송.

디스코드 임베드는 하나당 이미지가 한 장만 보이므로, 이미지 개수만큼 임베드를 만든다.
한 메시지에 임베드는 10개까지라 넘치면 메시지를 나눈다.
"""

from __future__ import annotations

import requests

from maple_sunday_bot.notice import Notice, event_period

MAX_EMBEDS_PER_MESSAGE = 10
EMBED_COLOR = 0xFF8C00
TIMEOUT_SECONDS = 15
OK_STATUS = {200, 204}


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


def send(webhook_url: str, messages: list[dict], session=None) -> None:
    """메시지를 순서대로 전송한다. 하나라도 실패하면 WebhookError."""
    session = session if session is not None else requests.Session()

    for index, message in enumerate(messages, start=1):
        try:
            response = session.post(webhook_url, json=message, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise WebhookError(f"{index}번째 메시지 전송 실패: {exc}") from exc
        if response.status_code not in OK_STATUS:
            raise WebhookError(
                f"{index}번째 메시지 전송 실패: HTTP {response.status_code}"
            )

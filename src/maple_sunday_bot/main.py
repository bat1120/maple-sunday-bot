"""진입점. 어떤 순서로 무엇을 할지만 담당한다."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from maple_sunday_bot import webhook as webhook_module
from maple_sunday_bot.nexon import NexonApiError, NexonClient
from maple_sunday_bot.notice import extract_images, is_sunday
from maple_sunday_bot.state import load_seen, save_seen

DEFAULT_STATE_PATH = Path("state/seen.json")


def run(client, webhook_url, state_path, bootstrap=False, session=None) -> int:
    """새 썬데이 공지를 찾아 발송한다. 발송한 공지 수를 반환한다."""
    seen = load_seen(state_path)
    fresh = [
        n
        for n in client.get_event_notices()
        if is_sunday(n.title) and n.notice_id not in seen
    ]

    if not fresh:
        return 0

    if bootstrap:
        save_seen(state_path, [n.notice_id for n in fresh] + seen)
        print(f"bootstrap: {len(fresh)}건을 발송 없이 기록했습니다.")
        return 0

    sent_count = 0
    for notice in fresh:
        try:
            images = extract_images(client.get_event_notice_detail(notice.notice_id))
        except NexonApiError as exc:
            # 이미지 누락보다 알림 누락이 나쁘다. 제목과 링크만이라도 보낸다.
            print(f"본문 조회 실패({notice.notice_id}): {exc}", file=sys.stderr)
            images = []

        webhook_module.send(
            webhook_url, webhook_module.build_messages(notice, images), session
        )
        # 전송 성공 직후에 기록한다. 여기서 죽으면 다음 회차에 다시 보낸다.
        seen = [notice.notice_id] + seen
        save_seen(state_path, seen)
        sent_count += 1
        print(f"발송 완료: [{notice.notice_id}] {notice.title}")

    return sent_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="썬데이 메이플 공지 알림 봇")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="발송하지 않고 현재 썬데이 공지를 전부 '이미 봄'으로 기록한다 (최초 1회)",
    )
    parser.add_argument(
        "--state", default=str(DEFAULT_STATE_PATH), help="상태 파일 경로"
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("NEXON_API_KEY")
    if not api_key:
        print("NEXON_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url and not args.bootstrap:
        print("DISCORD_WEBHOOK_URL 환경변수가 없습니다.", file=sys.stderr)
        return 1

    try:
        run(
            NexonClient(api_key),
            webhook_url or "",
            Path(args.state),
            bootstrap=args.bootstrap,
        )
    except Exception as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import pytest

from maple_sunday_bot.notice import Notice, is_sunday


@pytest.mark.parametrize(
    "title",
    [
        "썬데이 메이플",
        "스페셜 썬데이 메이플",
        "썬데이메이플",
        "[안내] 8월 9일 썬데이 메이플 안내",
        "  스페셜  썬데이   메이플  ",
    ],
)
def test_썬데이_공지_제목을_통과시킨다(title):
    assert is_sunday(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "메이플 히어로즈 이벤트",
        "썬데이 이벤트",  # '메이플'이 안 붙으면 다른 이벤트다
        "몬스터파크 메이플 이벤트",
        "",
    ],
)
def test_썬데이_공지가_아닌_제목은_거른다(title):
    assert is_sunday(title) is False


def test_Notice는_이벤트_기간이_없어도_만들_수_있다():
    notice = Notice(
        notice_id=1356,
        title="스페셜 썬데이 메이플",
        url="https://maplestory.nexon.com/News/Event/1356",
        date="2026-08-07T10:00+09:00",
        date_event_start=None,
        date_event_end=None,
    )
    assert notice.notice_id == 1356

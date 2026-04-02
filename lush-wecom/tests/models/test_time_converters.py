from __future__ import annotations

import datetime

from lush_wecom.models.get_groupmsg_list_vo import GetGroupMsgListRequest
from lush_wecom.models.get_moment_list_vo import GetMomentListRequest


def test_groupmsg_list_request_converts_datetime_to_int_ts() -> None:
    dt = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    req = GetGroupMsgListRequest(
        chat_type="single",
        start_time=dt,
        end_time=dt,
        limit=1,
    )
    assert isinstance(req.start_time, int)
    assert isinstance(req.end_time, int)


def test_moment_list_request_accepts_int_or_datetime() -> None:
    dt = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    req1 = GetMomentListRequest(start_time=dt, end_time=dt)
    assert isinstance(req1.start_time, int)
    assert isinstance(req1.end_time, int)

    req2 = GetMomentListRequest(start_time=123, end_time=456)
    assert req2.start_time == 123
    assert req2.end_time == 456

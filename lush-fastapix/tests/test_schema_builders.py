from __future__ import annotations

from lush_stdx.enumx import MetaInfoIntEnum, XMetaInfo

from lush_fastapix.schema_builders import build_parameter


class _E(MetaInfoIntEnum):
    A = (1, XMetaInfo("a"))
    B = (2, XMetaInfo("b"))


def test_build_parameter_basic_and_description_default() -> None:
    p = build_parameter("x", _E, in_="header", required=False, description=None)
    assert p["name"] == "x"
    assert p["in"] == "header"
    assert p["required"] is False
    assert p["description"] == ""
    assert p["schema"]["enum"] == [1, 2]
    assert "x-enum-module" in p["schema"]
    assert "x-enum-class" in p["schema"]

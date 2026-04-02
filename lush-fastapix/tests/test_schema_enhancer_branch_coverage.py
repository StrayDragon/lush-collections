from __future__ import annotations

import enum
import sys

from lush_fastapix.schema_enhancer import (
    _get_enum_description_from_schema,
    _has_enum_in_schema,
    _is_metainfo_enum_class,
    enhance_enum_schema,
    enhance_parameter_description,
    enhance_parameter_schema,
    enhance_path_parameters,
    enhance_request_body_schema,
    enhance_schema_recursive,
    generate_enhanced_description,
    should_enhance_parameter_description,
)


def test_enhance_path_parameters_keeps_non_dict_operation() -> None:
    paths = {"/x": {"get": "noop"}}
    enhanced = enhance_path_parameters(paths)
    assert enhanced["/x"]["get"] == "noop"


def test_enhance_parameter_schema_returns_input_when_invalid() -> None:
    assert enhance_parameter_schema("x") == "x"
    assert enhance_parameter_schema({"name": "x"}) == {"name": "x"}


def test_enhance_parameter_schema_does_not_enhance_description_when_already_detailed() -> None:
    param = {
        "name": "x",
        "schema": {"enum": [1], "description": "d\n\n* `1`: one"},
        "description": "d\n\n* `1`: one",
    }
    enhanced = enhance_parameter_schema(param, "/p", "get")
    assert enhanced["description"] == param["description"]


def test_enhance_request_body_schema_returns_input_when_invalid() -> None:
    assert enhance_request_body_schema({"x": 1}) == {"x": 1}


def test_enhance_request_body_schema_keeps_non_schema_content_defs() -> None:
    body = {"content": {"text/plain": "raw", "application/json": {"example": 1}}}
    enhanced = enhance_request_body_schema(body)
    assert enhanced["content"]["text/plain"] == "raw"
    assert enhanced["content"]["application/json"] == {"example": 1}


def test_enhance_schema_recursive_handles_non_dict_and_list_items() -> None:
    assert enhance_schema_recursive("x") == "x"

    schema = {
        "type": "array",
        "items": [
            {"enum": [1], "description": "e"},
            "x",
        ],
        "allOf": {"type": "string"},
        "additionalProperties": True,
    }
    enhanced = enhance_schema_recursive(schema, context_hint="ctx")
    assert enhanced["items"][1] == "x"


def test_enhance_enum_schema_non_dict_passthrough() -> None:
    assert enhance_enum_schema("x") == "x"


def test_enhance_enum_schema_normalizes_string_enum_anyof() -> None:
    schema = {
        "type": "string",
        "enum": ["a", "b"],
        "anyOf": [{"type": "integer"}, {"type": "string"}],
        "description": "d",
    }
    enhanced = enhance_enum_schema(schema, context_hint="ctx")
    assert "anyOf" not in enhanced
    assert enhanced["type"] == "string"
    assert enhanced["enum"] == ["a", "b"]

    mixed = {"type": "string", "enum": [1, "a"], "anyOf": [{"type": "integer"}, {"type": "string"}], "description": "d"}
    enhanced_mixed = enhance_enum_schema(mixed, context_hint="ctx")
    assert "anyOf" not in enhanced_mixed
    assert enhanced_mixed["enum"] == [1, "a"]


def test_enhance_enum_schema_keeps_anyof_when_contains_null() -> None:
    schema = {"type": "integer", "enum": [1, 2], "anyOf": [{"type": "integer"}, {"type": "null"}], "description": "d"}
    enhanced = enhance_enum_schema(schema, context_hint="ctx")
    assert "anyOf" in enhanced
    assert enhanced["enum"] == [1, 2]


def test_enhance_enum_schema_anyof_empty_and_nested_anyof() -> None:
    assert enhance_enum_schema({"anyOf": []}, context_hint="ctx") == {"anyOf": []}

    schema = {"anyOf": [{"anyOf": [{"enum": [1]}]}, "x"]}
    enhanced = enhance_enum_schema(schema, context_hint="ctx")
    assert "anyOf" in enhanced


def test_direct_enum_schema_imports_module_and_handles_mismatch() -> None:
    # Ensure module is not loaded so code path imports it.
    sys.modules.pop("tests._tmp_enum_mod", None)

    schema = {
        "type": "integer",
        "enum": [1, 2],
        "description": "d",
        "x-enum-module": "tests._tmp_enum_mod",
        "x-enum-class": "TmpEnum",
    }
    enhanced = enhance_enum_schema(schema, context_hint="ctx")
    assert "* `1`:" in enhanced.get("description", "")

    # Value mismatch => do not accept candidate enum class.
    mismatch = {
        "type": "integer",
        "enum": [1],
        "description": "d",
        "x-enum-module": "tests._tmp_enum_mod",
        "x-enum-class": "TmpEnum",
    }
    enhanced_mismatch = enhance_enum_schema(mismatch, context_hint="ctx")
    assert enhanced_mismatch == mismatch


def test_direct_enum_schema_returns_original_when_already_enhanced() -> None:
    from tests._tmp_enum_mod import TmpEnum

    already = generate_enhanced_description(TmpEnum, "desc\n\n* `1`: already")
    schema = {
        "type": "integer",
        "enum": [1, 2],
        "description": already,
        "x-enum-module": "tests._tmp_enum_mod",
        "x-enum-class": "TmpEnum",
    }
    enhanced = enhance_enum_schema(schema, context_hint="ctx")
    assert enhanced is schema


def test_generate_enhanced_description_no_x_meta_returns_original() -> None:
    class PlainEnum(enum.Enum):
        A = 1

    assert generate_enhanced_description(PlainEnum, "orig") == "orig"


def test_enhance_parameter_description_noop_when_not_needed() -> None:
    param = {"schema": {"type": "string"}, "description": "x"}
    assert enhance_parameter_description(param) is param
    assert should_enhance_parameter_description("x") is False


def test_is_metainfo_enum_class_branches() -> None:
    assert _is_metainfo_enum_class(None) is False

    class NotEnum:
        pass

    assert _is_metainfo_enum_class(NotEnum) is False

    class EmptyEnum(enum.Enum):
        pass

    assert _is_metainfo_enum_class(EmptyEnum) is False

    class NoXMeta(enum.Enum):
        A = 1

    assert _is_metainfo_enum_class(NoXMeta) is False

    class XMetaNoDesc(enum.Enum):
        A = 1

    XMetaNoDesc.A.x_meta = object()
    assert _is_metainfo_enum_class(XMetaNoDesc) is False


def test_get_enum_description_from_schema_and_has_enum_in_schema() -> None:
    assert _get_enum_description_from_schema("x") == ""

    schema = {
        "anyOf": [
            {"enum": [1], "description": "no ticks"},
            "x",
            {"enum": [1], "description": "* `1`: ok"},
        ]
    }
    assert _get_enum_description_from_schema(schema) == "* `1`: ok"

    assert _get_enum_description_from_schema({"description": "top"}) == "top"

    schema2 = {"anyOf": [{"type": "string"}, {"description": "desc in anyof"}]}
    assert _get_enum_description_from_schema(schema2) == "desc in anyof"
    assert _get_enum_description_from_schema({"anyOf": [{"type": "string"}]}) == ""
    assert _get_enum_description_from_schema({"type": "string"}) == ""

    assert _has_enum_in_schema("x") is False
    assert _has_enum_in_schema({"anyOf": [{"enum": [1]}]}) is True
    assert _has_enum_in_schema({"anyOf": ["x", {"anyOf": [{"enum": [1]}]}]}) is True
    assert _has_enum_in_schema({"anyOf": ["x", {"type": "string"}, {"type": "integer"}]}) is False

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TextIO, cast

from lush_stdx.enumx.compact import StrEnum
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from lush_logx.cli.textual_prompts import (
    MultiSelectConfig,
    TextualPromptBackError,
    TextualPromptError,
    run_textual_confirm,
    run_textual_multi_select,
    run_textual_single_select,
    run_textual_text_input,
)

_DEFAULT_COLUMNS = ("timestamp", "level", "logger", "event", "message")
_AVAILABLE_COLUMNS = ("timestamp", "level", "logger", "event", "message", "payload", "kind", "raw", "source")
_JSON_STANDARD_KEYS = {
    "event",
    "message",
    "level",
    "severity",
    "logger",
    "logger_name",
    "timestamp",
    "ts",
    "time",
    "datetime",
}
_LEVEL_STYLES = {
    "DEBUG": "dim cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold red",
}
_REGEX_TARGET_CHOICES = {
    "raw": "原始日志(raw)",
    "message": "解析消息(message)",
    "event": "事件(event)",
    "logger": "记录器(logger)",
    "level": "级别(level)",
    "payload": "额外字段(payload)",
}
_COLUMN_CONFIG: dict[str, dict[str, Any]] = {
    "timestamp": {"max_width": 24},
    "level": {"max_width": 8},
    "logger": {"max_width": 40},
    "event": {"max_width": 50},
    "message": {"max_width": 60},
    "payload": {"max_width": 60},
    "kind": {"max_width": 8},
    "raw": {"max_width": 120},
    "source": {"max_width": 60},
}
_METADATA_SAMPLE_LIMIT = 5000
_LEVEL_CHOICES_DEFAULT = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_MAX_SUGGESTIONS = 20
ExportFormat = Literal["json", "csv"]


@dataclass(slots=True)
class ResolvedInput:
    paths: list[Path]
    from_stdin: bool
    base_dir: Path | None


@dataclass(slots=True)
class LogMetadata:
    levels: set[str] = field(default_factory=set)
    loggers: set[str] = field(default_factory=set)
    keywords: set[str] = field(default_factory=set)

    @classmethod
    def empty(cls) -> LogMetadata:
        return cls()


class StepControl(Enum):
    ADVANCE = "advance"
    BACK = "back"
    CANCEL = "cancel"


@dataclass(slots=True)
class InteractiveWizardState:
    keyword_selection: list[str] = field(default_factory=list)
    keyword_extras: list[str] = field(default_factory=list)
    levels_selection: list[str] = field(default_factory=list)
    levels_extras: list[str] = field(default_factory=list)
    loggers_selection: list[str] = field(default_factory=list)
    loggers_extras: list[str] = field(default_factory=list)
    regex_targets: list[str] = field(default_factory=list)
    regex_rules: dict[str, list[str]] = field(default_factory=dict)
    columns: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_COLUMNS)
    limit: int | None = None
    as_json: bool = False
    export_format: str | None = None
    export_path: str | None = None

    def snapshot(self) -> InteractiveWizardState:
        return InteractiveWizardState(
            keyword_selection=list(self.keyword_selection),
            keyword_extras=list(self.keyword_extras),
            levels_selection=list(self.levels_selection),
            levels_extras=list(self.levels_extras),
            loggers_selection=list(self.loggers_selection),
            loggers_extras=list(self.loggers_extras),
            regex_targets=list(self.regex_targets),
            regex_rules={key: list(values) for key, values in self.regex_rules.items()},
            columns=tuple(self.columns),
            limit=self.limit,
            as_json=self.as_json,
            export_format=self.export_format,
            export_path=self.export_path,
        )


@dataclass(slots=True)
class ExportWriter:
    format: ExportFormat
    handle: TextIO
    columns: Sequence[str]
    csv_writer: csv.DictWriter[str] | None = None

    def write(self, entry: LogEntry) -> None:
        if self.format == "json":
            line = entry.raw
            if not line.endswith("\n"):
                line = f"{line}\n"
            _ = self.handle.write(line)
            return

        if self.csv_writer is None:
            fieldnames = [column.upper() for column in self.columns]
            self.csv_writer = csv.DictWriter(self.handle, fieldnames=fieldnames, extrasaction="ignore")
            self.csv_writer.writeheader()
        row = {column.upper(): _get_column_text(entry, column) for column in self.columns}
        self.csv_writer.writerow(row)

    def close(self) -> None:
        self.handle.close()


class LogEntryKind(StrEnum):
    JSON = "json"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class LogEntry:
    raw: str
    kind: LogEntryKind
    timestamp: str | None = None
    level: str | None = None
    logger: str | None = None
    event: str | None = None
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind.value,
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "event": self.event,
            "message": self.message,
            "payload": self.payload or None,
            "raw": self.raw,
            "source": self.source,
        }
        return {key: value for key, value in data.items() if value is not None}


def parse_log_stream(lines: Iterable[str] | Iterable[tuple[str | None, str]]) -> Iterator[LogEntry]:
    for item in lines:
        if isinstance(item, tuple):
            source, raw_line = item
        else:
            source, raw_line = None, item
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        yield parse_log_line(line, source=source)


def parse_log_line(line: str, source: str | None = None) -> LogEntry:
    json_entry = _parse_json_line(line, source=source)
    if json_entry is not None:
        return json_entry

    bracket_entry = _parse_bracket_line(line, source=source)
    if bracket_entry is not None:
        return bracket_entry

    key_value_entry = _parse_key_value_line(line, source=source)
    if key_value_entry is not None:
        return key_value_entry

    return LogEntry(
        raw=line,
        kind=LogEntryKind.UNKNOWN,
        message=line.strip(),
        source=source,
    )


def _parse_json_line(line: str, *, source: str | None = None) -> LogEntry | None:
    try:
        data_raw = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(data_raw, dict):
        return None

    data = cast("dict[str, Any]", data_raw)
    timestamp = _pick_first(data, ("timestamp", "ts", "time", "datetime"))
    level = _pick_first(data, ("level", "severity"))
    logger = _pick_first(data, ("logger", "logger_name"))
    event = _pick_first(data, ("event", "message"))

    payload: dict[str, Any] = {key: value for key, value in data.items() if key not in _JSON_STANDARD_KEYS}

    return LogEntry(
        raw=line,
        kind=LogEntryKind.JSON,
        timestamp=_ensure_text(timestamp),
        level=_ensure_text(level),
        logger=_ensure_text(logger),
        event=_ensure_text(event),
        message=_build_json_message(event, payload),
        payload=payload,
        source=source,
    )


def _parse_bracket_line(line: str, *, source: str | None = None) -> LogEntry | None:
    if not line.startswith("[") or "]" not in line:
        return None

    closing_idx = line.find("]")
    timestamp = line[1:closing_idx].strip() or None
    rest = line[closing_idx + 1 :].strip()
    message = rest or None

    return LogEntry(
        raw=line,
        kind=LogEntryKind.TEXT,
        timestamp=timestamp,
        message=message,
        event=message,
        source=source,
    )


def _parse_key_value_line(line: str, *, source: str | None = None) -> LogEntry | None:
    if "=" not in line:
        return None

    key, _, value = line.partition("=")
    key = key.strip()
    if not key:
        return None

    value = value.strip()
    payload: dict[str, str] = {key: value}

    return LogEntry(
        raw=line,
        kind=LogEntryKind.TEXT,
        message=line.strip(),
        event=f"{key}={value}",
        payload=payload,
        source=source,
    )


def _pick_first(data: dict[str, Any], keys: Sequence[str]) -> Any | None:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _ensure_text(value: Any | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _build_json_message(event: str | None, payload: dict[str, Any]) -> str | None:
    if event and payload:
        return f"{event} {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    if event:
        return event
    if payload:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return None


def _resolve_input(path: str, glob_pattern: str) -> ResolvedInput:
    if path == "-" or not path:
        return ResolvedInput(paths=[], from_stdin=True, base_dir=None)

    input_path = Path(path).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(path)

    if input_path.is_file():
        return ResolvedInput(paths=[input_path], from_stdin=False, base_dir=input_path.parent)

    if input_path.is_dir():
        matched_paths = sorted(p for p in input_path.rglob(glob_pattern) if p.is_file())
        return ResolvedInput(paths=matched_paths, from_stdin=False, base_dir=input_path)

    raise OSError(f"{path} 不是文件或目录")


def _iter_sources(resolved: ResolvedInput) -> Iterator[tuple[str | None, str]]:
    if resolved.from_stdin:
        for line in sys.stdin:
            yield None, line
        return

    for path in resolved.paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                yield str(path), line


def _collect_metadata(paths: Sequence[Path], limit: int = _METADATA_SAMPLE_LIMIT) -> LogMetadata:
    metadata = LogMetadata.empty()
    if not paths:
        return metadata

    total = 0
    for path in paths:
        with suppress(OSError), path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.rstrip("\n")
                if not line.strip():
                    continue
                entry = parse_log_line(line, source=str(path))
                if entry.level:
                    metadata.levels.add(entry.level)
                if entry.logger:
                    metadata.loggers.add(entry.logger)
                if entry.event:
                    metadata.keywords.add(entry.event)
                elif entry.message:
                    metadata.keywords.add(entry.message)
                total += 1
                if total >= limit:
                    return metadata
    return metadata


def _apply_filters(
    entries: Iterable[LogEntry],
    *,
    levels: list[str] | None,
    loggers: list[str] | None,
    contains: list[str] | None,
) -> Iterator[LogEntry]:
    normalized_levels = {level.upper() for level in levels or []}
    normalized_loggers = set(loggers or [])
    substrings = contains or []

    for entry in entries:
        if normalized_levels and (entry.level or "").upper() not in normalized_levels:
            continue

        if normalized_loggers:
            logger_name = entry.logger or ""
            if not any(logger_name.startswith(candidate) for candidate in normalized_loggers):
                continue

        if substrings:
            raw_text = entry.raw
            if not all(substring in raw_text for substring in substrings):
                continue

        yield entry


def _run_multi_select_prompt(
    *,
    title: str,
    choices: Sequence[tuple[str, str]],
    preselected: Sequence[str],
    error_console: Console,
    instructions: str | None = None,
    allow_empty: bool = True,
    allow_back: bool = False,
    extra_prompt: str | None = None,
    extra_default: str = "",
    extra_placeholder: str | None = None,
) -> tuple[list[str] | None, str | None]:
    config = MultiSelectConfig(
        title=title,
        choices=choices,
        preselected=preselected,
        instructions=instructions,
        allow_empty=allow_empty,
        extra_prompt=extra_prompt,
        extra_default=extra_default,
        extra_placeholder=extra_placeholder,
    )
    try:
        outcome = run_textual_multi_select(config, allow_back=allow_back)
    except TextualPromptBackError:
        raise
    except TextualPromptError as exc:
        error_console.print(f"[red]{exc}[/red]")
        return None, None
    selections = outcome.selections
    extra_text = outcome.extra_text
    if selections is None:
        return None, extra_text
    return _deduplicate_list(selections), extra_text


def _run_text_input_prompt(
    *,
    title: str,
    prompt: str,
    default: str,
    error_console: Console,
    allow_empty: bool = True,
    placeholder: str | None = None,
    strip_result: bool = True,
    allow_back: bool = False,
) -> str | None:
    try:
        return run_textual_text_input(
            title,
            prompt,
            default,
            allow_empty=allow_empty,
            placeholder=placeholder,
            strip_result=strip_result,
            allow_back=allow_back,
        )
    except TextualPromptBackError:
        raise
    except TextualPromptError as exc:
        error_console.print(f"[red]{exc}[/red]")
        return None


def _run_confirm_prompt(
    *,
    title: str,
    prompt: str,
    default: bool,
    error_console: Console,
    allow_back: bool = False,
) -> bool | None:
    try:
        return run_textual_confirm(title, prompt, default, allow_back=allow_back)
    except TextualPromptBackError:
        raise
    except TextualPromptError as exc:
        error_console.print(f"[red]{exc}[/red]")
        return None


def _run_single_select_prompt(
    *,
    title: str,
    prompt: str,
    choices: Sequence[tuple[str, str]],
    default: str | None,
    error_console: Console,
    allow_back: bool = False,
) -> str | None:
    try:
        return run_textual_single_select(title, prompt, choices, default, allow_back=allow_back)
    except TextualPromptBackError:
        raise
    except TextualPromptError as exc:
        error_console.print(f"[red]{exc}[/red]")
        return None


def _apply_regex_filters(
    entries: Iterable[LogEntry],
    regex_rules: Mapping[str, Sequence[re.Pattern[str]]],
) -> Iterator[LogEntry]:
    if not regex_rules:
        yield from entries
        return

    for entry in entries:
        matched = True
        for target_field, patterns in regex_rules.items():
            if not patterns:
                continue
            candidate = _get_regex_target_value(entry, target_field)
            if not all(pattern.search(candidate) for pattern in patterns):
                matched = False
                break
        if matched:
            yield entry


def _parse_regex_arguments(
    patterns: Sequence[str],
    targets: Sequence[str] | None,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    default_targets = [target for target in (targets or []) if target in _REGEX_TARGET_CHOICES]

    for raw_pattern in patterns:
        if not raw_pattern:
            continue
        target_field: str | None = None
        expression = raw_pattern
        for separator in (":", "="):
            if separator in raw_pattern:
                prefix, _, suffix = raw_pattern.partition(separator)
                prefix = prefix.strip()
                suffix = suffix.strip()
                if prefix in _REGEX_TARGET_CHOICES and suffix:
                    target_field = prefix
                    expression = suffix
                    break
        expression = expression.strip()
        if not expression:
            continue
        target_candidates = [target_field] if target_field else (default_targets or ["raw"])
        for candidate in target_candidates:
            if candidate not in _REGEX_TARGET_CHOICES:
                continue
            result.setdefault(candidate, []).append(expression)
    return result


def _compile_regex_rules(
    direct_rules: Mapping[str, Sequence[str]] | None,
    raw_patterns: Sequence[str],
    raw_targets: Sequence[str] | None,
    error_console: Console,
) -> dict[str, list[re.Pattern[str]]]:
    merged: dict[str, list[str]] = {}
    if direct_rules:
        for target_field, patterns in direct_rules.items():
            if target_field in _REGEX_TARGET_CHOICES and patterns:
                merged.setdefault(target_field, []).extend(patterns)

    parsed_rules = _parse_regex_arguments(raw_patterns, raw_targets)
    for target_field, patterns in parsed_rules.items():
        merged.setdefault(target_field, []).extend(patterns)

    compiled: dict[str, list[re.Pattern[str]]] = {}
    for target_field, patterns in merged.items():
        compiled_patterns: list[re.Pattern[str]] = []
        for pattern in patterns:
            compiled_pattern = _safe_compile_pattern(pattern, error_console)
            if compiled_pattern is not None:
                compiled_patterns.append(compiled_pattern)
        if compiled_patterns:
            compiled[target_field] = compiled_patterns
    return compiled


def _safe_compile_pattern(pattern: str, error_console: Console) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern)
    except re.error as exc:
        error_console.print(f"[red]无效正则表达式 {pattern!r}: {exc}[/red]")
        return None


def _get_regex_target_value(entry: LogEntry, target: str) -> str:
    if target == "raw":
        return entry.raw
    if target == "message":
        return entry.message or ""
    if target == "event":
        return entry.event or ""
    if target == "logger":
        return entry.logger or ""
    if target == "level":
        return entry.level or ""
    if target == "payload":
        if not entry.payload:
            return ""
        return json.dumps(entry.payload, ensure_ascii=False, separators=(",", ":"))
    return entry.raw


def _format_column(entry: LogEntry, column: str) -> Text:
    if column == "timestamp":
        return Text(entry.timestamp or "-", style="cyan")
    if column == "level":
        level_value = entry.level or "-"
        style = _LEVEL_STYLES.get(level_value.upper(), "")
        return Text(level_value, style=style)
    if column == "logger":
        return Text(entry.logger or "-", style="bright_blue")
    if column == "event":
        return Text(entry.event or "-", style="bright_white")
    if column == "message":
        return Text(entry.message or "-", style="white")
    if column == "kind":
        return Text(entry.kind.value, style="magenta")
    if column == "payload":
        if not entry.payload:
            return Text("-")
        return Text(json.dumps(entry.payload, ensure_ascii=False, separators=(",", ":")), style="bright_black")
    if column == "raw":
        return Text(entry.raw, style="white")
    if column == "source":
        return Text(entry.source or "-", style="bright_black")
    return Text("-")


def _get_column_text(entry: LogEntry, column: str) -> str:
    if column == "timestamp":
        return entry.timestamp or ""
    if column == "level":
        return entry.level or ""
    if column == "logger":
        return entry.logger or ""
    if column == "event":
        return entry.event or ""
    if column == "message":
        return entry.message or ""
    if column == "kind":
        return entry.kind.value
    if column == "payload":
        if not entry.payload:
            return ""
        return json.dumps(entry.payload, ensure_ascii=False, separators=(",", ":"))
    if column == "raw":
        return entry.raw
    if column == "source":
        return entry.source or ""
    return ""


def _parse_columns(columns: str | Sequence[str] | None) -> tuple[str, ...]:
    if columns is None:
        return _DEFAULT_COLUMNS
    if isinstance(columns, str):
        raw = [item.strip() for item in columns.split(",") if item.strip()]
    else:
        raw = [str(item).strip() for item in columns if str(item).strip()]

    ordered: list[str] = []
    seen: set[str] = set()
    for column in raw:
        if column not in _AVAILABLE_COLUMNS:
            continue
        if column in seen:
            continue
        ordered.append(column)
        seen.add(column)

    return tuple(ordered or _DEFAULT_COLUMNS)


def _split_by_comma(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _deduplicate_list(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _ensure_str_list(values: Sequence[object] | None) -> list[str]:
    if values is None:
        return []

    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                result.append(stripped)
    return result


def _should_highlight_column(column: str, regex_target: str) -> bool:
    mapping = {
        "raw": {"raw"},
        "message": {"message"},
        "event": {"event"},
        "logger": {"logger"},
        "level": {"level"},
        "payload": {"payload"},
        "source": {"source"},
    }
    return column in mapping.get(regex_target, set())


def _resolve_export_path(export_format: str, export_path: str | None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = "json" if export_format == "json" else "csv"

    if not export_path:
        final_path = Path.cwd() / f"export_{timestamp}.{extension}"
    else:
        path_obj = Path(export_path).expanduser()
        if (path_obj.exists() and path_obj.is_dir()) or export_path.endswith(("/", "\\")):
            final_path = path_obj / f"export_{timestamp}.{extension}"
        elif path_obj.suffix:
            final_path = path_obj
        else:
            final_path = path_obj.with_suffix(f".{extension}")

    final_path.parent.mkdir(parents=True, exist_ok=True)
    return final_path


def _open_export_writer(export_format: ExportFormat, path: Path, columns: Sequence[str]) -> ExportWriter:
    if export_format == "json":
        handle = path.open("w", encoding="utf-8")
    else:
        handle = path.open("w", encoding="utf-8", newline="")
    return ExportWriter(format=export_format, handle=handle, columns=columns)


def _emit_json_entries(
    entries: Iterable[LogEntry],
    limit: int | None,
    stdout: TextIO,
    export_writer: ExportWriter | None,
) -> int:
    count = 0
    for entry in entries:
        json_line = json.dumps(entry.to_dict(), ensure_ascii=False)
        _ = stdout.write(json_line + "\n")
        if export_writer is not None:
            export_writer.write(entry)
        count += 1
        if limit is not None and count >= limit:
            break
    stdout.flush()
    return count


def _emit_table_entries(
    entries: Iterable[LogEntry],
    columns: Sequence[str],
    limit: int | None,
    console: Console,
    export_writer: ExportWriter | None,
    contains: list[str] | None,
    regex_rules: Mapping[str, Sequence[re.Pattern[str]]],
) -> int:
    table = Table(show_header=True, header_style="bold cyan", expand=False, highlight=True)
    for column in columns:
        config = _COLUMN_CONFIG.get(column, {})
        table.add_column(
            column.upper(),
            overflow="ellipsis",
            max_width=config.get("max_width"),
        )

    highlight_terms = contains or []
    count = 0
    for entry in entries:
        if export_writer is not None:
            export_writer.write(entry)

        row_cells: list[Text] = []
        for column in columns:
            cell = _format_column(entry, column)
            for term in filter(None, highlight_terms):
                _ = cell.highlight_regex(re.escape(term), style="reverse bold")
            for target_field, patterns in regex_rules.items():
                if not patterns or not _should_highlight_column(column, target_field):
                    continue
                for pattern in patterns:
                    _ = cell.highlight_regex(pattern.pattern, style="bold yellow")
            row_cells.append(cell)

        table.add_row(*row_cells)
        count += 1
        if limit is not None and count >= limit:
            break

    if count == 0:
        return 0

    caption = f"显示 {count} 条日志"
    if limit is not None:
        caption += f" (限制 {limit})"
    table.caption = caption
    console.print(table)
    return count


def _render_summary(console: Console, args: argparse.Namespace, count: int) -> None:
    lines: list[str] = []
    resolved_paths: list[Path] = getattr(args, "resolved_paths", [])
    from_stdin: bool = getattr(args, "from_stdin", args.path in ("-", None))
    if from_stdin:
        source_desc = "stdin"
    elif not resolved_paths:
        source_desc = args.path or "未指定"
    elif len(resolved_paths) == 1:
        source_desc = str(resolved_paths[0])
    else:
        sample = ", ".join(str(path) for path in resolved_paths[:3])
        suffix = "" if len(resolved_paths) <= 3 else f" 等 {len(resolved_paths)} 个文件"
        source_desc = f"{sample}{suffix}"
    lines.append(f"[bold]数据源[/bold]: {source_desc}")
    lines.append(f"[bold]匹配条数[/bold]: {count}" + (f" / 限制 {args.limit}" if args.limit is not None else ""))

    if args.levels:
        lines.append(f"[bold]级别过滤[/bold]: {', '.join(args.levels)}")
    if args.loggers:
        lines.append(f"[bold]Logger[/bold]: {', '.join(args.loggers)}")
    if args.contains:
        lines.append(f"[bold]关键字[/bold]: {', '.join(args.contains)}")
    regex_rules = cast("dict[str, list[str]]", getattr(args, "regex_rules", {}))
    if regex_rules:
        rule_segments: list[str] = []
        for target_field, pattern_list in regex_rules.items():
            normalized_patterns = [str(pattern) for pattern in pattern_list if pattern]
            if normalized_patterns:
                rule_segments.append(f"{target_field}={'|'.join(normalized_patterns)}")
        if rule_segments:
            lines.append(f"[bold]正则[/bold]: {', '.join(rule_segments)}")
    elif args.regex_patterns:
        targets = getattr(args, "regex_targets", None)
        target_desc = ", ".join(targets) if targets else "raw"
        lines.append(f"[bold]正则[/bold]: {', '.join(args.regex_patterns)} @ {target_desc}")
    parsed_columns = _parse_columns(getattr(args, "columns", None))
    args.columns = parsed_columns
    lines.append(f"[bold]列[/bold]: {', '.join(parsed_columns)}")
    export_format = getattr(args, "export_format", None)
    export_path = getattr(args, "export_path", None)
    if export_format and export_path:
        lines.append(f"[bold]导出[/bold]: {export_format.upper()} -> {export_path}")

    panel = Panel("\n".join(lines), title="过滤概要", expand=False, border_style="blue")
    console.print(panel)


def _run_interactive_wizard(
    args: argparse.Namespace,
    error_console: Console,
    metadata: LogMetadata,
) -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        error_console.print("[yellow]当前终端不支持交互式向导, 将继续使用已有参数[/yellow]")
        return True

    existing_regex_rules_input: dict[str, list[str]] = getattr(args, "regex_rules", {})
    existing_regex_rules = {key: list(dict.fromkeys(values)) for key, values in existing_regex_rules_input.items() if values}
    default_regex_targets = list(existing_regex_rules.keys() or (args.regex_targets or []))
    default_columns = list(_parse_columns(getattr(args, "columns", None)))
    level_choices = sorted({*(args.levels or []), *metadata.levels, *_LEVEL_CHOICES_DEFAULT})
    logger_choices = sorted(metadata.loggers)
    if len(logger_choices) > _MAX_SUGGESTIONS:
        logger_choices = logger_choices[:_MAX_SUGGESTIONS]
    keyword_choices = sorted(metadata.keywords)
    if len(keyword_choices) > _MAX_SUGGESTIONS:
        keyword_choices = keyword_choices[:_MAX_SUGGESTIONS]

    preselected_keywords = _deduplicate_list(args.contains)
    keyword_selection = [keyword for keyword in preselected_keywords if keyword in keyword_choices]
    keyword_extras = [keyword for keyword in preselected_keywords if keyword not in keyword_choices]

    original_levels = _deduplicate_list(args.levels)
    levels_selection = [level for level in original_levels if level in level_choices]
    levels_extras = [level for level in original_levels if level not in level_choices]

    original_loggers = _deduplicate_list(args.loggers)
    loggers_selection = [logger for logger in original_loggers if logger in logger_choices]
    loggers_extras = [logger for logger in original_loggers if logger not in logger_choices]

    state = InteractiveWizardState(
        keyword_selection=keyword_selection,
        keyword_extras=keyword_extras,
        levels_selection=levels_selection,
        levels_extras=levels_extras,
        loggers_selection=loggers_selection,
        loggers_extras=loggers_extras,
        regex_targets=list(default_regex_targets),
        regex_rules={key: list(value) for key, value in existing_regex_rules.items()},
        columns=tuple(default_columns or _DEFAULT_COLUMNS),
        limit=args.limit,
        as_json=bool(args.as_json),
        export_format=getattr(args, "export_format", None),
        export_path=getattr(args, "export_path", None),
    )

    def step_keywords(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        available = sorted({choice for choice in keyword_choices if choice})
        combined = _deduplicate_list([*available, *current_state.keyword_selection])
        pairs = [(choice, choice) for choice in combined]
        try:
            selections, extra_text = _run_multi_select_prompt(
                title="关键字筛选",
                choices=pairs,
                preselected=_deduplicate_list(current_state.keyword_selection),
                instructions=(
                    "Ctrl+K 聚焦搜索, H/L 聚焦切换, J/K 移动, 空格切换选中, Ctrl+A 全选, Ctrl+D 清除, Ctrl+I 反选, Ctrl+O 聚焦额外输入, Enter 确认, Esc 取消"
                ),
                error_console=error_console,
                allow_empty=True,
                allow_back=can_go_back,
                extra_prompt="额外关键字 (逗号分隔, 留空跳过)",
                extra_default=",".join(current_state.keyword_extras),
                extra_placeholder="例如: 关键字A,关键字B",
            )
        except TextualPromptBackError:
            if can_go_back:
                return StepControl.BACK
            return StepControl.CANCEL
        if selections is None:
            return StepControl.CANCEL
        current_state.keyword_selection = selections
        current_state.keyword_extras = _split_by_comma(extra_text or "")
        return StepControl.ADVANCE

    def step_levels(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        if not level_choices:
            current_state.levels_selection = _deduplicate_list(current_state.levels_selection)
            current_state.levels_extras = _deduplicate_list(current_state.levels_extras)
            return StepControl.ADVANCE
        combined = _deduplicate_list([*(str(choice) for choice in level_choices), *current_state.levels_selection])
        pairs = [(choice, choice) for choice in combined]
        try:
            selections, extra_text = _run_multi_select_prompt(
                title="选择日志级别",
                choices=pairs,
                preselected=_deduplicate_list(current_state.levels_selection),
                instructions="Ctrl+K 搜索, H/L 聚焦切换, J/K 移动, 空格切换选中, Ctrl+O 聚焦额外输入, Enter 确认, Esc 取消",
                error_console=error_console,
                allow_empty=True,
                allow_back=can_go_back,
                extra_prompt="额外日志级别 (逗号分隔, 留空跳过)",
                extra_default=",".join(current_state.levels_extras),
                extra_placeholder="例如: INFO_VERBOSE",
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if selections is None:
            return StepControl.CANCEL
        current_state.levels_selection = selections
        current_state.levels_extras = _split_by_comma(extra_text or "")
        return StepControl.ADVANCE

    def step_loggers(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        if not logger_choices:
            current_state.loggers_selection = _deduplicate_list(current_state.loggers_selection)
            current_state.loggers_extras = _deduplicate_list(current_state.loggers_extras)
            return StepControl.ADVANCE
        combined = _deduplicate_list([*(str(choice) for choice in logger_choices), *current_state.loggers_selection])
        pairs = [(choice, choice) for choice in combined]
        try:
            selections, extra_text = _run_multi_select_prompt(
                title="选择常见 Logger",
                choices=pairs,
                preselected=_deduplicate_list(current_state.loggers_selection),
                instructions="Ctrl+K 搜索, H/L 聚焦切换, J/K 移动, 空格切换选中, Ctrl+O 聚焦额外输入, Enter 确认, Esc 取消",
                error_console=error_console,
                allow_empty=True,
                allow_back=can_go_back,
                extra_prompt="额外 Logger (逗号分隔, 留空跳过)",
                extra_default=",".join(current_state.loggers_extras),
                extra_placeholder="例如: project.module",
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if selections is None:
            return StepControl.CANCEL
        current_state.loggers_selection = selections
        current_state.loggers_extras = _split_by_comma(extra_text or "")
        return StepControl.ADVANCE

    def step_regex_targets(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        try:
            selection, _ = _run_multi_select_prompt(
                title="选择需要应用正则的字段",
                choices=[(label, value) for value, label in _REGEX_TARGET_CHOICES.items()],
                preselected=[target for target in current_state.regex_targets if target in _REGEX_TARGET_CHOICES],
                instructions="Ctrl+K 搜索, H/L 聚焦切换, J/K 移动, 空格切换选中, Enter 确认, Esc 取消",
                error_console=error_console,
                allow_empty=True,
                allow_back=can_go_back,
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if selection is None:
            return StepControl.CANCEL
        normalized = [target for target in selection if target in _REGEX_TARGET_CHOICES]
        current_state.regex_targets = normalized
        current_state.regex_rules = {
            target: list(dict.fromkeys(current_state.regex_rules.get(target, [])))
            for target in normalized
            if current_state.regex_rules.get(target)
        }
        return StepControl.ADVANCE

    def step_columns(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        try:
            selection, _ = _run_multi_select_prompt(
                title="选择输出列",
                choices=[(column, column) for column in _AVAILABLE_COLUMNS],
                preselected=list(current_state.columns),
                instructions="Ctrl+K 搜索, H/L 聚焦切换, J/K 移动, 空格切换选中, Enter 确认, Esc 取消",
                error_console=error_console,
                allow_empty=False,
                allow_back=can_go_back,
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if selection is None:
            return StepControl.CANCEL
        current_state.columns = tuple(selection or _DEFAULT_COLUMNS)
        return StepControl.ADVANCE

    def step_limit(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        while True:
            try:
                limit_raw = _run_text_input_prompt(
                    title="输出条数限制",
                    prompt="限制输出条数 (输入整数, 留空表示全部)",
                    default="" if current_state.limit is None else str(current_state.limit),
                    error_console=error_console,
                    placeholder="例如 200",
                    allow_back=can_go_back,
                )
            except TextualPromptBackError:
                return StepControl.BACK
            if limit_raw is None:
                return StepControl.CANCEL
            limit_text = limit_raw.strip()
            if not limit_text:
                current_state.limit = None
                return StepControl.ADVANCE
            try:
                current_state.limit = int(limit_text)
            except ValueError:
                error_console.print("[red]请输入有效的整数[/red]")
                continue
            return StepControl.ADVANCE

    def step_json_toggle(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        try:
            decision = _run_confirm_prompt(
                title="输出格式",
                prompt="是否以 JSON 行形式输出解析结果?",
                default=bool(current_state.as_json),
                error_console=error_console,
                allow_back=can_go_back,
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if decision is None:
            return StepControl.CANCEL
        current_state.as_json = bool(decision)
        return StepControl.ADVANCE

    def step_export_format(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        default_choice = current_state.export_format or ("json" if current_state.export_path else "none")
        try:
            selection = _run_single_select_prompt(
                title="导出格式",
                prompt="选择导出格式 (Esc 取消)",
                choices=[
                    ("不导出", "none"),
                    ("JSON (逐行)", "json"),
                    ("CSV", "csv"),
                ],
                default=default_choice,
                error_console=error_console,
                allow_back=can_go_back,
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if selection is None:
            return StepControl.CANCEL
        current_state.export_format = None if selection == "none" else selection
        if current_state.export_format is None:
            current_state.export_path = None
        return StepControl.ADVANCE

    def step_export_path(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        if current_state.export_format is None:
            current_state.export_path = None
            return StepControl.ADVANCE
        try:
            path_raw = _run_text_input_prompt(
                title="导出路径",
                prompt="输入导出的文件路径或目录 (留空自动生成)",
                default=current_state.export_path or "",
                error_console=error_console,
                allow_back=can_go_back,
            )
        except TextualPromptBackError:
            return StepControl.BACK
        if path_raw is None:
            return StepControl.CANCEL
        current_state.export_path = path_raw.strip() or None
        return StepControl.ADVANCE

    def step_regex_rules(current_state: InteractiveWizardState, can_go_back: bool) -> StepControl:
        if not current_state.regex_targets:
            current_state.regex_rules = {}
            return StepControl.ADVANCE
        updated_rules: dict[str, list[str]] = {}
        for target_field in current_state.regex_targets:
            label = _REGEX_TARGET_CHOICES.get(target_field, target_field)
            default_patterns = ",".join(current_state.regex_rules.get(target_field, []))
            try:
                pattern_raw = _run_text_input_prompt(
                    title=f"{label} 正则配置",
                    prompt=f"为 {label} 输入正则表达式 (逗号分隔, 留空跳过)",
                    default=default_patterns,
                    error_console=error_console,
                    allow_back=can_go_back,
                )
            except TextualPromptBackError:
                return StepControl.BACK
            if pattern_raw is None:
                return StepControl.CANCEL
            patterns = _split_by_comma(pattern_raw)
            if patterns:
                updated_rules[target_field] = patterns
        current_state.regex_rules = updated_rules
        return StepControl.ADVANCE

    steps: list[Callable[[InteractiveWizardState, bool], StepControl]] = [
        step_keywords,
        step_levels,
        step_loggers,
        step_regex_targets,
        step_columns,
        step_limit,
        step_json_toggle,
        step_export_format,
        step_export_path,
        step_regex_rules,
    ]

    history: list[InteractiveWizardState] = [state.snapshot()]
    step_index = 0

    while step_index < len(steps):
        can_go_back = step_index > 0
        control = steps[step_index](state, can_go_back)
        if control is StepControl.ADVANCE:
            history.append(state.snapshot())
            step_index += 1
            continue
        if control is StepControl.BACK:
            if step_index == 0 or len(history) <= 1:
                continue
            last_snapshot = history.pop()
            state = last_snapshot
            step_index -= 1
            continue
        return False

    args.contains = _deduplicate_list([*state.keyword_selection, *state.keyword_extras])
    args.levels = _deduplicate_list([*state.levels_selection, *state.levels_extras])
    args.loggers = _deduplicate_list([*state.loggers_selection, *state.loggers_extras])
    args.columns = tuple(state.columns or _DEFAULT_COLUMNS)
    args.limit = state.limit
    args.as_json = bool(state.as_json)
    args.export_format = state.export_format
    args.export_path = state.export_path
    args.regex_targets = list(state.regex_targets)
    args.regex_rules = {target: list(dict.fromkeys(patterns)) for target, patterns in state.regex_rules.items() if patterns}
    args.regex_patterns = []
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lush-logx-cli-log-parser",
        description="解析并展示混合 JSON/Text 的日志文件, 支持筛选与多种输出形式",
    )
    _ = parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="日志文件路径, 默认为标准输入",
    )
    _ = parser.add_argument(
        "--path-glob",
        dest="path_glob",
        default="*.log",
        help="当路径为目录时用于匹配日志文件的 glob 模式 (默认: *.log)",
    )
    _ = parser.add_argument(
        "--level",
        dest="levels",
        action="append",
        help="按日志级别筛选(可多次使用, 匹配 JSON 中的 level 字段)",
    )
    _ = parser.add_argument(
        "--logger",
        dest="loggers",
        action="append",
        help="按 logger 前缀筛选(可多次使用)",
    )
    _ = parser.add_argument(
        "--contains",
        dest="contains",
        action="append",
        help="要求原始日志同时包含的关键字(可多次使用)",
    )
    _ = parser.add_argument(
        "--regex",
        dest="regex_patterns",
        action="append",
        help="正则表达式过滤(可多次使用)",
    )
    _ = parser.add_argument(
        "--regex-target",
        dest="regex_targets",
        action="append",
        choices=list(_REGEX_TARGET_CHOICES.keys()),
        help="正则匹配的目标字段(可多次使用, 默认 raw)",
    )
    _ = parser.add_argument(
        "--export-format",
        dest="export_format",
        choices=["json", "csv"],
        help="将匹配日志导出为文件时使用的格式 (json/csv)",
    )
    _ = parser.add_argument(
        "--export-path",
        dest="export_path",
        help="导出的文件路径或目录, 与 --export-format 搭配使用",
    )
    _ = parser.add_argument(
        "--columns",
        dest="columns",
        default=None,
        help="逗号分隔的列名, 可选: timestamp,level,logger,event,message,kind,payload,raw,source",
    )
    _ = parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="最多输出的日志条数",
    )
    _ = parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="以 JSON 行形式输出解析结果",
    )
    _ = parser.add_argument(
        "-i",
        "--interactive",
        dest="interactive",
        action="store_true",
        help="启动交互式向导配置筛选条件",
    )
    _ = parser.add_argument(
        "--output-json-file",
        dest="output_json_file",
        help="将匹配日志另存为 JSONL 文件路径",
    )

    args = parser.parse_args(argv)

    console = Console()
    error_console = Console(stderr=True)

    args.levels = _ensure_str_list(args.levels)
    args.loggers = _ensure_str_list(args.loggers)
    args.contains = _ensure_str_list(args.contains)
    args.regex_patterns = _ensure_str_list(args.regex_patterns)
    args.regex_targets = _ensure_str_list(getattr(args, "regex_targets", None))

    try:
        resolved_input = _resolve_input(args.path, args.path_glob)
    except FileNotFoundError:
        error_console.print(f"[red]文件不存在: {args.path}[/red]")
        return 1
    except OSError as exc:
        error_console.print(f"[red]{exc}[/red]")
        return 1

    resolved_paths = resolved_input.paths
    if not resolved_input.from_stdin and not resolved_paths:
        error_console.print(f"[red]目录 {args.path} 内未找到匹配 {args.path_glob!r} 的日志文件[/red]")
        return 1

    if args.interactive and not resolved_input.from_stdin and resolved_paths:
        if len(resolved_paths) > 1:
            base_dir = resolved_input.base_dir or resolved_paths[0].parent
            choices = [(str(path.relative_to(base_dir)), str(path)) for path in resolved_paths]
            selection, _ = _run_multi_select_prompt(
                title="选择需要解析的日志文件",
                choices=choices,
                preselected=[value for _, value in choices],
                instructions="Ctrl+K 搜索, H/L 聚焦切换, J/K 移动, 空格切换选中, Ctrl+D 清空, Enter 确认, Esc 取消",
                error_console=error_console,
                allow_empty=False,
            )
            if selection is None:
                error_console.print("[red]已取消交互式配置[/red]")
                return 1
            if not selection:
                error_console.print("[red]未选择任何日志文件[/red]")
                return 1
            resolved_paths = [Path(value) for value in selection]

    metadata = LogMetadata.empty()
    if not resolved_input.from_stdin and resolved_paths:
        metadata = _collect_metadata(resolved_paths)

    args.resolved_paths = resolved_paths
    args.from_stdin = resolved_input.from_stdin

    if args.interactive:
        if not _run_interactive_wizard(args, error_console, metadata):
            return 1

    args.levels = _ensure_str_list(args.levels)
    args.loggers = _ensure_str_list(args.loggers)
    args.contains = _ensure_str_list(args.contains)
    args.regex_patterns = _ensure_str_list(args.regex_patterns)
    args.regex_targets = _ensure_str_list(args.regex_targets)
    if getattr(args, "export_format", None) == "none":
        args.export_format = None
    args.export_path = args.export_path or None
    if getattr(args, "output_json_file", None):
        args.export_format = args.export_format or "json"
        args.export_path = args.output_json_file

    regex_rules_input: dict[str, list[str]] = dict(getattr(args, "regex_rules", {}))
    parsed_rules = _parse_regex_arguments(args.regex_patterns, args.regex_targets)
    for target_field, patterns in parsed_rules.items():
        regex_rules_input.setdefault(target_field, []).extend(patterns)
    args.regex_rules = {target_field: list(dict.fromkeys(patterns)) for target_field, patterns in regex_rules_input.items() if patterns}
    args.regex_patterns = []

    try:
        compiled_regex = _compile_regex_rules(args.regex_rules, [], None, error_console)
    except FileNotFoundError:
        error_console.print(f"[red]文件不存在: {args.path}[/red]")
        return 1
    except OSError as exc:
        error_console.print(f"[red]无法读取日志文件: {args.path} ({exc})[/red]")
        return 1

    resolved_input.paths = resolved_paths
    log_iter = _iter_sources(resolved_input)
    entries = parse_log_stream(log_iter)
    entries = _apply_filters(entries, levels=args.levels, loggers=args.loggers, contains=args.contains)
    entries = _apply_regex_filters(entries, compiled_regex)

    limit = args.limit if args.limit is None or args.limit >= 0 else None
    columns = _parse_columns(getattr(args, "columns", None))
    args.columns = columns

    export_writer: ExportWriter | None = None
    export_format = getattr(args, "export_format", None)
    export_path_option = getattr(args, "export_path", None)
    if export_format:
        export_format_literal = cast("ExportFormat", export_format)
        resolved_export_path = _resolve_export_path(export_format_literal, export_path_option)
        try:
            export_writer = _open_export_writer(export_format_literal, resolved_export_path, columns)
        except OSError as exc:
            error_console.print(f"[red]无法写入导出文件: {resolved_export_path} ({exc})[/red]")
            return 1
        args.export_format = export_format_literal
        args.export_path = str(resolved_export_path)
    else:
        args.export_format = None
        args.export_path = None

    try:
        if args.as_json:
            count = _emit_json_entries(entries, limit, sys.stdout, export_writer)
            if count == 0:
                error_console.print("[yellow]未匹配到任何日志[/yellow]")
            return 0

        count = _emit_table_entries(entries, columns, limit, console, export_writer, args.contains, compiled_regex)
        if count == 0:
            console.print("[yellow]未匹配到任何日志[/yellow]")
            return 0

        _render_summary(console, args, count)
    finally:
        if export_writer is not None:
            export_writer.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

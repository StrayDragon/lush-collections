from __future__ import annotations

import csv
import json
from pathlib import Path
from textwrap import dedent

from _pytest.capture import CaptureFixture

from lush_logx.cli.log_parser import LogEntryKind, main, parse_log_line, parse_log_stream


def test_parse_json_line_extracts_known_fields() -> None:
    line = '{"event": "运行开始", "level": "info", "logger": "service.test", "timestamp": "2025-11-12 15:20:05", "extra": {"foo": "bar"}}'

    entry = parse_log_line(line)

    assert entry.kind is LogEntryKind.JSON
    assert entry.event == "运行开始"
    assert entry.level == "info"
    assert entry.logger == "service.test"
    assert entry.timestamp == "2025-11-12 15:20:05"
    assert entry.payload == {"extra": {"foo": "bar"}}
    assert entry.source is None


def test_parse_text_lines_supports_bracket_and_key_value() -> None:
    lines = [
        "[2025-11-12T15:18:01+08:00] job start",
        "COMMAND=uv run python cron/process.py",
        "",
    ]

    entries = list(parse_log_stream(lines))

    assert len(entries) == 2
    assert entries[0].kind is LogEntryKind.TEXT
    assert entries[0].timestamp == "2025-11-12T15:18:01+08:00"
    assert entries[0].message == "job start"

    assert entries[1].kind is LogEntryKind.TEXT
    assert entries[1].payload == {"COMMAND": "uv run python cron/process.py"}


def test_cli_json_mode_outputs_filtered_entries(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    content = dedent(
        """
        {"event": "Sentry 初始化成功, 环境: dev", "level": "info", "logger": "lush_sentryx.manager", "timestamp": "2025-11-12 15:20:05"}
        [2025-11-12T15:18:01+08:00] job start
        """,
    ).strip()

    log_file: Path = tmp_path / "sample.log"
    _ = log_file.write_text(content)

    exit_code = main([str(log_file), "--json", "--level", "info"])
    captured = capsys.readouterr()

    assert exit_code == 0
    output_lines = [line for line in captured.out.strip().splitlines() if line]
    assert len(output_lines) == 1

    parsed = json.loads(output_lines[0])
    assert parsed["event"] == "Sentry 初始化成功, 环境: dev"
    assert parsed["level"] == "info"
    assert parsed["source"] == str(log_file)


def test_regex_filter_and_file_output(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    content = dedent(
        """
        {"event": "员工任务统计处理完成", "level": "info", "logger": "service.stats", "timestamp": "2025-11-12 15:20:05"}
        {"event": "其他任务已跳过", "level": "warning", "logger": "service.other", "timestamp": "2025-11-12 15:21:05"}
        """,
    ).strip()

    log_file: Path = tmp_path / "sample.log"
    _ = log_file.write_text(content)

    output_path: Path = tmp_path / "filtered.jsonl"
    exit_code = main(
        [
            str(log_file),
            "--json",
            "--regex",
            "统计",
            "--regex-target",
            "event",
            "--output-json-file",
            str(output_path),
        ],
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    stdout_lines = [line for line in captured.out.strip().splitlines() if line]
    assert len(stdout_lines) == 1
    parsed_stdout = json.loads(stdout_lines[0])
    assert "统计" in parsed_stdout["event"]
    assert parsed_stdout["source"] == str(log_file)

    file_lines = [line for line in output_path.read_text().splitlines() if line]
    assert len(file_lines) == 1
    assert file_lines[0] == content.splitlines()[0]


def test_cli_table_mode_outputs_summary(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    content = dedent(
        """
        {"event": "Sentry 初始化成功, 环境: dev", "level": "info", "logger": "lush_sentryx.manager", "timestamp": "2025-11-12 15:20:05"}
        {"event": "======= 开始处理待发送的定时派发任务 =======", "level": "info", "logger": "demo_service.cron", "timestamp": "2025-11-12 15:20:05"}
        """,
    ).strip()

    log_file: Path = tmp_path / "sample.log"
    _ = log_file.write_text(content)

    exit_code = main([str(log_file), "--limit", "1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "过滤概要" in captured.out
    assert "Sentry" in captured.out


def test_directory_input_resolves_multiple_files(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    content_a = '{"event": "A", "level": "info", "logger": "demo.a"}\n'
    content_b = '{"event": "B", "level": "error", "logger": "demo.b"}\n'

    file_a = tmp_path / "a.log"
    file_b = tmp_path / "b.log"
    _ = file_a.write_text(content_a)
    _ = file_b.write_text(content_b)

    exit_code = main([str(tmp_path), "--json", "--limit", "2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    output_lines = [json.loads(line) for line in captured.out.strip().splitlines() if line]
    sources = {parsed["source"] for parsed in output_lines}
    assert sources == {str(file_a), str(file_b)}


def test_regex_field_prefix_syntax(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    content = dedent(
        """
        {"event": "需要统计", "level": "info", "logger": "demo", "timestamp": "2025-01-01 00:00:00"}
        {"event": "无需匹配", "level": "info", "logger": "demo", "timestamp": "2025-01-01 00:00:01"}
        """,
    ).strip()

    log_file: Path = tmp_path / "sample.log"
    _ = log_file.write_text(content)

    exit_code = main([str(log_file), "--json", "--regex", "event:统计"])
    captured = capsys.readouterr()

    assert exit_code == 0
    output_lines = [json.loads(line) for line in captured.out.strip().splitlines() if line]
    assert len(output_lines) == 1
    assert "统计" in output_lines[0]["event"]


def test_export_csv_produces_file(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    content = dedent(
        """
        {"event": "Sentry 初始化成功, 环境: dev", "level": "info", "logger": "lush_sentryx.manager", "timestamp": "2025-11-12 15:20:05"}
        {"event": "======= 开始处理...", "level": "warning", "logger": "service", "timestamp": "2025-11-12 15:21:05"}
        """,
    ).strip()

    log_file: Path = tmp_path / "sample.log"
    _ = log_file.write_text(content)
    export_path = tmp_path / "result.csv"

    exit_code = main([str(log_file), "--export-format", "csv", "--export-path", str(export_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert export_path.exists()
    with export_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert rows[0]["EVENT"] == "Sentry 初始化成功, 环境: dev"
    assert rows[0]["LEVEL"] == "info"
    assert export_path.name in captured.out


def test_export_json_preserves_raw_lines(tmp_path: Path) -> None:
    content = dedent(
        """
        [2025-11-12T15:18:01+08:00] job start
        {"event": "Sentry 初始化成功, 环境: dev", "logger": "lush_sentryx.manager", "level": "info", "timestamp": "2025-11-12 15:20:05"}
        """,
    ).strip()

    log_file: Path = tmp_path / "sample.log"
    _ = log_file.write_text(content)
    export_path = tmp_path / "result.jsonl"

    exit_code = main([str(log_file), "--export-format", "json", "--export-path", str(export_path)])

    assert exit_code == 0
    exported_lines = export_path.read_text(encoding="utf-8").splitlines()
    assert exported_lines == content.splitlines()

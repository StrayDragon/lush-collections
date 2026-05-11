from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, OptionList, SelectionList, Static
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection
from typing_extensions import override


class TextualPromptError(RuntimeError):
    """当 Textual 交互提示运行失败时抛出。"""


class TextualPromptBackError(RuntimeError):
    """当 Textual 交互提示请求返回上一步时抛出。"""


@dataclass(slots=True)
class MultiSelectConfig:
    title: str
    choices: Sequence[tuple[str, str]]
    preselected: Sequence[str]
    instructions: str | None = None
    allow_empty: bool = True
    extra_prompt: str | None = None
    extra_default: str = ""
    extra_placeholder: str | None = None


@dataclass(slots=True)
class MultiSelectResult:
    selections: list[str] | None
    extra_text: str | None


class _MultiSelectApp(App[list[str] | None]):
    CSS: ClassVar[str] = """
    Screen {
        layout: vertical;
    }

    #body {
        layout: vertical;
        padding: 1 2;
    }

    #title {
        text-style: bold;
    }

    #instructions {
        color: $text-muted;
    }

    #filter {
        border: solid $accent;
    }

    SelectionList {
        border: solid $accent;
        height: 1fr;
        padding: 1;
    }

    #status {
        color: $success-lighten-2;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+b", "go_back", "上一步"),
        Binding("enter", "confirm", "确认"),
        Binding("escape", "cancel", "取消"),
        Binding("ctrl+k", "focus_filter", "聚焦搜索"),
        Binding("ctrl+l", "focus_list", "聚焦列表"),
        Binding("ctrl+a", "select_all", "全选当前"),
        Binding("ctrl+d", "clear_selection", "清除当前"),
        Binding("ctrl+i", "invert_selection", "反选当前"),
        Binding("h", "focus_filter", "聚焦搜索(h)"),
        Binding("l", "focus_list", "聚焦列表(l)"),
        Binding("j", "cursor_down", "下移(j)"),
        Binding("k", "cursor_up", "上移(k)"),
        Binding("ctrl+o", "focus_extra", "聚焦额外输入(Ctrl+O)"),
    ]

    def __init__(self, config: MultiSelectConfig, *, allow_back: bool) -> None:
        super().__init__()
        self._config = config
        self._allow_back = allow_back
        self._all_options = list(config.choices)
        self._selected_values = set(config.preselected)
        self._filtered_options: list[tuple[str, str]] = list(self._all_options)
        self._status: Static | None = None
        self._filter_input: Input | None = None
        self._list: SelectionList[str] | None = None
        self._back_requested = False
        self._extra_input: Input | None = None
        self._extra_value: str | None = None

    @override
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="body"):
            yield Static(self._config.title, id="title")
            if self._config.instructions:
                yield Static(self._config.instructions, id="instructions")
            self._filter_input = Input(placeholder="输入以过滤 (支持模糊匹配, 大小写不敏感)", id="filter")
            yield self._filter_input
            self._list = SelectionList[str](id="options")
            yield self._list
            if self._config.extra_prompt is not None:
                yield Static(self._config.extra_prompt, id="extra_prompt")
                self._extra_input = Input(
                    value=self._config.extra_default,
                    placeholder=self._config.extra_placeholder or "",
                    id="extra_input",
                )
                yield self._extra_input
            self._status = Static("", id="status")
            yield self._status
        yield Footer()

    def on_ready(self) -> None:
        if self._filter_input is None or self._list is None:
            raise TextualPromptError("无法创建交互式组件")
        self._apply_filter("")
        self._filter_input.focus()

    def action_focus_filter(self) -> None:
        if self._filter_input is not None:
            self._filter_input.focus()

    def action_focus_list(self) -> None:
        if self._list is not None:
            self._list.focus()

    def action_focus_extra(self) -> None:
        if self._extra_input is not None:
            self._extra_input.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter" or self._list is None:
            return
        self._sync_selected_from_widget()
        self._apply_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is self._filter_input:
            event.stop()
            self.action_confirm()

    def on_selection_list_selected_changed(self, message: SelectionList.SelectedChanged[str]) -> None:
        self._sync_selected_from_widget(message.selection_list)

    def on_paste(self, event: events.Paste) -> None:
        if self._filter_input is not None and self._filter_input.has_focus:
            event.stop()
            self._filter_input.insert_text_at_cursor(event.text)

    def action_select_all(self) -> None:
        if self._list is None:
            return
        self._list.select_all()
        self._sync_selected_from_widget()

    def action_clear_selection(self) -> None:
        if self._list is None:
            return
        self._list.deselect_all()
        self._sync_selected_from_widget()

    def action_invert_selection(self) -> None:
        if self._list is None:
            return
        self._list.toggle_all()
        self._sync_selected_from_widget()

    def action_cursor_down(self) -> None:
        if self._list is None:
            return
        cast("Any", self._list).action_cursor_down()

    def action_cursor_up(self) -> None:
        if self._list is None:
            return
        cast("Any", self._list).action_cursor_up()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self.action_confirm()
            return

    def action_go_back(self) -> None:
        if self._allow_back:
            self._back_requested = True
            self.exit(None)

    def action_confirm(self) -> None:
        if self._list is None:
            return
        self._sync_selected_from_widget()
        if not self._config.allow_empty and not self._selected_values:
            self._update_status("请至少选择一项", error=True)
            return
        ordered = [value for _, value in self._all_options if value in self._selected_values]
        if self._extra_input is not None:
            self._extra_value = self._extra_input.value
        self._back_requested = False
        self.exit(ordered)

    def action_cancel(self) -> None:
        self._back_requested = False
        self.exit(None)

    def _apply_filter(self, text: str) -> None:
        if self._list is None:
            return
        normalized = text.strip().lower()
        if normalized:
            filtered = [option for option in self._all_options if normalized in option[0].lower() or normalized in option[1].lower()]
        else:
            filtered = list(self._all_options)
        self._filtered_options = filtered
        self._list.clear_options()
        for label, value in filtered:
            self._list.add_option(Selection(label, value, value in self._selected_values))
        if filtered and self._list is not None:
            cast("Any", self._list).index = 0
        self._update_status()

    def _sync_selected_from_widget(self, widget: SelectionList[str] | None = None) -> None:
        selection_list = widget or self._list
        if selection_list is None:
            return
        visible_values = {value for _, value in self._filtered_options}
        current_visible_selected = set(selection_list.selected)
        self._selected_values.difference_update(visible_values)
        self._selected_values.update(current_visible_selected)
        self._update_status()

    def _update_status(self, message: str | None = None, *, error: bool = False) -> None:
        if self._status is None:
            return
        summary = f"已选 {len(self._selected_values)} / {len(self._all_options)}"
        if message:
            summary = f"{message} · {summary}" if summary else message
        if not self._filtered_options:
            summary = "无匹配结果, 调整过滤条件" if not message else f"{message} · 无匹配结果"
        style = "$error" if error else "$success-lighten-2"
        self._status.update(f"[{style}]{summary}[/{style}]")

    @property
    def back_requested(self) -> bool:
        return self._back_requested

    @property
    def extra_value(self) -> str | None:
        if self._extra_input is None:
            return None
        return self._extra_value if self._extra_value is not None else self._extra_input.value


def run_textual_multi_select(
    config: MultiSelectConfig,
    *,
    allow_back: bool = False,
) -> MultiSelectResult:
    app = _MultiSelectApp(config, allow_back=allow_back)
    try:
        selections = app.run()
    except Exception as exc:  # pragma: no cover - Textual handles Ctrl+C / runtime issues
        raise TextualPromptError(f"启动 Textual 多选界面失败: {exc}") from exc
    if allow_back and app.back_requested:
        raise TextualPromptBackError
    return MultiSelectResult(selections, app.extra_value)


class _TextInputApp(App[str | None]):
    CSS: ClassVar[str] = """
    Screen {
        layout: vertical;
    }

    #body {
        layout: vertical;
        padding: 1 2;
    }

    #title {
        text-style: bold;
    }

    Input {
        border: solid $accent;
    }

    #status {
        color: $text-muted;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+b", "go_back", "上一步"),
        Binding("enter", "confirm", "确认"),
        Binding("escape", "cancel", "取消"),
        Binding("ctrl+u", "clear", "清空"),
    ]

    def __init__(
        self,
        title: str,
        prompt: str,
        default: str,
        *,
        allow_empty: bool,
        placeholder: str | None,
        strip_result: bool,
        allow_back: bool,
    ) -> None:
        super().__init__()
        self._title = title
        self._prompt = prompt
        self._default = default
        self._allow_empty = allow_empty
        self._placeholder = placeholder
        self._strip_result = strip_result
        self._allow_back = allow_back
        self._input: Input | None = None
        self._status: Static | None = None
        self._back_requested = False

    @override
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="body"):
            yield Static(self._title, id="title")
            yield Static(self._prompt, id="prompt")
            self._input = Input(value=self._default, placeholder=self._placeholder or "")
            yield self._input
            self._status = Static("", id="status")
            yield self._status
        yield Footer()

    def on_ready(self) -> None:
        if self._input is None:
            raise TextualPromptError("无法创建输入组件")
        self._input.focus()
        self._update_status()

    def action_clear(self) -> None:
        if self._input is not None:
            self._input.value = ""
            self._update_status()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self._input:
            self._update_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is self._input:
            event.stop()
            self.action_confirm()

    def action_confirm(self) -> None:
        if self._input is None:
            return
        value = self._input.value
        processed = value.strip() if self._strip_result else value
        if not self._allow_empty and not processed:
            if self._status is not None:
                self._status.update("[red]请输入非空内容[/red]")
            return
        self._back_requested = False
        self.exit(processed)

    def action_cancel(self) -> None:
        self._back_requested = False
        self.exit(None)

    def action_go_back(self) -> None:
        if self._allow_back:
            self._back_requested = True
            self.exit(None)

    def _update_status(self) -> None:
        if self._input is None or self._status is None:
            return
        length = len(self._input.value)
        self._status.update(f"[dim]当前长度: {length}[/dim]")

    @property
    def back_requested(self) -> bool:
        return self._back_requested


def run_textual_text_input(
    title: str,
    prompt: str,
    default: str = "",
    *,
    allow_empty: bool = True,
    placeholder: str | None = None,
    strip_result: bool = True,
    allow_back: bool = False,
) -> str | None:
    app = _TextInputApp(
        title,
        prompt,
        default,
        allow_empty=allow_empty,
        placeholder=placeholder,
        strip_result=strip_result,
        allow_back=allow_back,
    )
    try:
        result = app.run()
    except Exception as exc:  # pragma: no cover
        raise TextualPromptError(f"启动 Textual 输入界面失败: {exc}") from exc
    if allow_back and app.back_requested:
        raise TextualPromptBackError
    return result


class _ConfirmApp(App[bool | None]):
    CSS: ClassVar[str] = """
    Screen {
        layout: vertical;
    }

    #body {
        layout: vertical;
        padding: 1 2;
    }

    #title {
        text-style: bold;
    }

    #status {
        color: $success-lighten-2;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+b", "go_back", "上一步"),
        Binding("enter", "confirm", "确认"),
        Binding("escape", "cancel", "取消"),
        Binding("space", "toggle", "切换"),
        Binding("y", "set_true", "选是"),
        Binding("n", "set_false", "选否"),
    ]

    def __init__(self, title: str, prompt: str, default: bool, *, allow_back: bool) -> None:
        super().__init__()
        self._title = title
        self._prompt = prompt
        self._value = default
        self._allow_back = allow_back
        self._status: Static | None = None
        self._back_requested = False

    @override
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="body"):
            yield Static(self._title, id="title")
            yield Static(self._prompt, id="prompt")
            self._status = Static("", id="status")
            yield self._status
        yield Footer()

    def on_ready(self) -> None:
        self._update_status()

    @override
    def action_toggle(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._value = not self._value
        self._update_status()

    def action_set_true(self) -> None:
        self._value = True
        self._update_status()

    def action_set_false(self) -> None:
        self._value = False
        self._update_status()

    def action_confirm(self) -> None:
        self._back_requested = False
        self.exit(self._value)

    def action_cancel(self) -> None:
        self._back_requested = False
        self.exit(None)

    def action_go_back(self) -> None:
        if self._allow_back:
            self._back_requested = True
            self.exit(None)

    def _update_status(self) -> None:
        if self._status is None:
            return
        value_text = "是" if self._value else "否"
        self._status.update(f"[bold]{value_text}[/bold] (空格切换, Y/N 快捷选择)")

    @property
    def back_requested(self) -> bool:
        return self._back_requested


def run_textual_confirm(
    title: str,
    prompt: str,
    default: bool = True,
    *,
    allow_back: bool = False,
) -> bool | None:
    app = _ConfirmApp(title, prompt, default, allow_back=allow_back)
    try:
        result = app.run()
    except Exception as exc:  # pragma: no cover
        raise TextualPromptError(f"启动 Textual 确认界面失败: {exc}") from exc
    if allow_back and app.back_requested:
        raise TextualPromptBackError
    return result


class _SingleSelectApp(App[str | None]):
    CSS: ClassVar[str] = """
    Screen {
        layout: vertical;
    }

    #body {
        layout: vertical;
        padding: 1 2;
    }

    #title {
        text-style: bold;
    }

    OptionList {
        border: solid $accent;
        height: 1fr;
        padding: 1;
    }

    #status {
        color: $text-muted;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+b", "go_back", "上一步"),
        Binding("enter", "confirm", "确认"),
        Binding("escape", "cancel", "取消"),
        Binding("j", "cursor_down", "下移(j)"),
        Binding("k", "cursor_up", "上移(k)"),
        Binding("ctrl+o", "focus_extra", "聚焦额外输入(Ctrl+O)"),
    ]

    def __init__(
        self,
        title: str,
        prompt: str,
        choices: Sequence[tuple[str, str]],
        default: str | None,
        allow_back: bool,
    ) -> None:
        super().__init__()
        self._title = title
        self._prompt = prompt
        self._choices = list(choices)
        self._default = default
        self._allow_back = allow_back
        self._option_list: OptionList | None = None
        self._values: list[str] = [value for _, value in self._choices]
        self._back_requested = False

    @override
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="body"):
            yield Static(self._title, id="title")
            yield Static(self._prompt, id="prompt")
            options = [Option(label) for label, _ in self._choices]
            self._option_list = OptionList(*options, id="options")
            yield self._option_list
            yield Static("上下方向键选择, Enter 确认, Esc 取消", id="status")
        yield Footer()

    def on_ready(self) -> None:
        if self._option_list is None:
            raise TextualPromptError("无法创建列表组件")
        default_index = 0
        if self._default is not None and self._default in self._values:
            default_index = self._values.index(self._default)
        cast("Any", self._option_list).index = default_index

    def action_confirm(self) -> None:
        if self._option_list is None:
            return
        highlighted = self._option_list.highlighted
        if highlighted is None:
            return
        try:
            value = self._values[highlighted]
        except IndexError:
            self.exit(None)
            return
        self._back_requested = False
        self.exit(value)

    def action_cancel(self) -> None:
        self._back_requested = False
        self.exit(None)

    def action_go_back(self) -> None:
        if self._allow_back:
            self._back_requested = True
            self.exit(None)

    def action_cursor_down(self) -> None:
        if self._option_list is None:
            return
        cast("Any", self._option_list).action_cursor_down()

    def action_cursor_up(self) -> None:
        if self._option_list is None:
            return
        cast("Any", self._option_list).action_cursor_up()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self.action_confirm()
            return

    def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        index = message.option_index
        if index is None:
            return
        if 0 <= index < len(self._values):
            message.stop()
            self.exit(self._values[index])

    @property
    def back_requested(self) -> bool:
        return self._back_requested


def run_textual_single_select(
    title: str,
    prompt: str,
    choices: Sequence[tuple[str, str]],
    default: str | None = None,
    *,
    allow_back: bool = False,
) -> str | None:
    app = _SingleSelectApp(title, prompt, choices, default, allow_back=allow_back)
    try:
        result = app.run()
    except Exception as exc:  # pragma: no cover
        raise TextualPromptError(f"启动 Textual 单选界面失败: {exc}") from exc
    if allow_back and app.back_requested:
        raise TextualPromptBackError
    return result


__all__ = [
    "MultiSelectConfig",
    "MultiSelectResult",
    "TextualPromptBackError",
    "TextualPromptError",
    "run_textual_confirm",
    "run_textual_multi_select",
    "run_textual_single_select",
    "run_textual_text_input",
]

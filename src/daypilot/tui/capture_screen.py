import asyncio
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, RichLog, Static
from textual.worker import Worker, WorkerState

from daypilot.capture.agent import create_capture_agent
from daypilot.capture.state import CaptureState


class CaptureScreen(Screen):
    CSS = """
    Screen {
        background: #0f1418;
    }

    #body {
        layout: horizontal;
        height: 1fr;
        padding: 1 2;
    }

    .pane {
        border: round #3b4a58;
        padding: 1 2;
    }

    .pane-title {
        text-style: bold;
        color: #d9e2ec;
        margin-bottom: 1;
    }

    #tasks-pane {
        width: 38%;
        min-width: 28;
        layout: vertical;
        margin-right: 1;
    }

    #task-list {
        height: 1fr;
    }

    #chat-pane {
        width: 1fr;
        min-width: 40;
        layout: vertical;
    }

    #chat-log {
        height: 1fr;
    }

    #chat-input {
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "app.quit", "Quit"),
        ("escape", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._agent = create_capture_agent()
        self._state: CaptureState = {
            "messages": [],
            "tasks": [],
            "now": datetime.now().astimezone(),
        }
        self._stream_buffer: str | None = None
        self._agent_worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        with Container(id="body"):
            yield Container(
                Static("Captured tasks", classes="pane-title"),
                self._build_task_list(),
                id="tasks-pane",
                classes="pane",
            )
            yield Container(
                Static("Capture chat", classes="pane-title"),
                RichLog(id="chat-log", highlight=True, markup=True, wrap=True),
                Input(placeholder="Describe tasks, ask questions, or clarify...", id="chat-input"),
                id="chat-pane",
                classes="pane",
            )

    def on_mount(self) -> None:
        self.query_one("#chat-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return

        message = event.value.strip()
        if not message:
            return

        self._state["messages"] = [
            *self._state.get("messages", []),
            HumanMessage(content=message),
        ]
        event.input.value = ""
        event.input.disabled = True
        self._stream_buffer = None
        self._render_chat_log()
        self._agent_worker = self.run_worker(
            self._run_agent_stream,
            name="capture_agent",
            group="capture_agent",
            exclusive=True,
            thread=True,
        )
        event.input.focus()

    def _build_task_list(self) -> ListView:
        items = [ListItem(Label(self._format_task(task))) for task in self._state.get("tasks", [])]
        return ListView(*items, id="task-list")

    def _run_agent_stream(self) -> None:
        asyncio.run(self._run_agent_stream_async())

    async def _run_agent_stream_async(self) -> None:
        final_state: CaptureState | None = None
        async for event in self._agent.astream_events(self._state, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                text = self._message_text(chunk)
                if text:
                    self.app.call_from_thread(self._append_stream_text, text)
            elif event.get("event") == "on_chain_end":
                output = event.get("data", {}).get("output")
                if isinstance(output, dict) and "messages" in output:
                    final_state = output
        self.app.call_from_thread(self._apply_final_state, final_state)

    def _append_stream_text(self, text: str) -> None:
        if self._stream_buffer is None:
            self._stream_buffer = ""
        self._stream_buffer += text
        self._render_chat_log()

    def _apply_final_state(self, output_state: CaptureState | None) -> None:
        if output_state is not None:
            self._state = output_state
        self._stream_buffer = None
        self._render_chat_log()
        self._refresh_task_list()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "capture_agent":
            return
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED):
            return
        chat_input = self.query_one("#chat-input", Input)
        chat_input.disabled = False
        chat_input.focus()
        if event.state == WorkerState.ERROR:
            chat_log = self.query_one("#chat-log", RichLog)
            chat_log.write(f"[bold red]Error:[/bold red] {event.worker.error}")

    def _render_chat_log(self) -> None:
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.clear()
        for message in self._state.get("messages", []):
            self._write_message(chat_log, message)
        if self._stream_buffer:
            chat_log.write(f"[bold magenta]Agent:[/bold magenta] {self._stream_buffer}")

    def _write_message(self, chat_log: RichLog, message) -> None:
        text = self._message_text(message)
        if not text:
            return
        if isinstance(message, ToolMessage):
            chat_log.write(f"[bold yellow]Tool:[/bold yellow] {text}")
        elif isinstance(message, AIMessage):
            chat_log.write(f"[bold magenta]Agent:[/bold magenta] {text}")
        elif isinstance(message, HumanMessage):
            chat_log.write(f"[bold cyan]You:[/bold cyan] {text}")
        else:
            chat_log.write(text)

    def _refresh_task_list(self) -> None:
        task_list = self.query_one("#task-list", ListView)
        task_list.clear()
        for task in self._state.get("tasks", []):
            task_list.append(ListItem(Label(self._format_task(task))))

    def _format_task(self, task) -> str:
        return f"{task.id}. {task.title}"

    def _message_text(self, message) -> str:
        if message is None:
            return ""
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "".join(parts).strip()
        return str(content).strip()

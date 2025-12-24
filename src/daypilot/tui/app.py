from textual.app import App

from daypilot.tui.capture_screen import CaptureScreen


class CaptureApp(App):
    TITLE = "DayPilot Capture"
    SUB_TITLE = "Task capture workspace"

    def on_mount(self) -> None:
        self.push_screen(CaptureScreen())


def main() -> None:
    CaptureApp().run()


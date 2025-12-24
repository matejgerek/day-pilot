from datetime import datetime

from langgraph.graph import MessagesState

from daypilot.capture.schema import CandidateTask


class CaptureState(MessagesState):
    tasks: list[CandidateTask]
    now: datetime

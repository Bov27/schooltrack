"""Attendance state machine (ADR-004). Pure: no I/O.

    OUTSIDE --CHECK_IN--> PRESENT --TEMPORARY_CHECK_OUT--> TEMPORARY_EXIT
       ^                   |   ^                                |
       +----CHECK_OUT------+   +------------RETURN--------------+

Attendance state answers "where is this person now?". Validation status (is this
event trustworthy?) is a separate dimension and lives on the event.
"""

import enum


class AttendanceState(enum.StrEnum):
    OUTSIDE = "OUTSIDE"
    PRESENT = "PRESENT"
    TEMPORARY_EXIT = "TEMPORARY_EXIT"


class EventType(enum.StrEnum):
    CHECK_IN = "CHECK_IN"
    TEMPORARY_CHECK_OUT = "TEMPORARY_CHECK_OUT"
    RETURN = "RETURN"
    CHECK_OUT = "CHECK_OUT"


TRANSITIONS: dict[tuple[AttendanceState, EventType], AttendanceState] = {
    (AttendanceState.OUTSIDE, EventType.CHECK_IN): AttendanceState.PRESENT,
    (AttendanceState.PRESENT, EventType.TEMPORARY_CHECK_OUT): AttendanceState.TEMPORARY_EXIT,
    (AttendanceState.TEMPORARY_EXIT, EventType.RETURN): AttendanceState.PRESENT,
    (AttendanceState.PRESENT, EventType.CHECK_OUT): AttendanceState.OUTSIDE,
}


class InvalidTransitionError(Exception):
    def __init__(self, state: AttendanceState, event: EventType) -> None:
        allowed = sorted(e.value for (s, e) in TRANSITIONS if s is state)
        super().__init__(
            f"Cannot {event.value} while {state.value}; allowed now: {', '.join(allowed)}"
        )
        self.state = state
        self.event = event
        self.allowed = allowed


def next_state(state: AttendanceState, event: EventType) -> AttendanceState:
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise InvalidTransitionError(state, event) from None


def allowed_events(state: AttendanceState) -> list[EventType]:
    return [e for (s, e) in TRANSITIONS if s is state]

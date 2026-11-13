import itertools

import pytest

from app.modules.attendance.state_machine import (
    TRANSITIONS,
    AttendanceState,
    EventType,
    InvalidTransitionError,
    allowed_events,
    next_state,
)

S, E = AttendanceState, EventType


@pytest.mark.parametrize(
    ("state", "event", "expected"),
    [
        (S.OUTSIDE, E.CHECK_IN, S.PRESENT),
        (S.PRESENT, E.TEMPORARY_CHECK_OUT, S.TEMPORARY_EXIT),
        (S.TEMPORARY_EXIT, E.RETURN, S.PRESENT),
        (S.PRESENT, E.CHECK_OUT, S.OUTSIDE),
    ],
)
def test_allowed_transitions(state: S, event: E, expected: S) -> None:
    assert next_state(state, event) is expected


INVALID = [(s, e) for s, e in itertools.product(S, E) if (s, e) not in TRANSITIONS]


def test_exactly_four_transitions_exist() -> None:
    assert len(TRANSITIONS) == 4
    assert len(INVALID) == len(S) * len(E) - 4


@pytest.mark.parametrize(("state", "event"), INVALID)
def test_every_other_combination_is_rejected(state: S, event: E) -> None:
    with pytest.raises(InvalidTransitionError) as info:
        next_state(state, event)
    assert info.value.state is state
    assert info.value.event is event


def test_duplicate_check_in_is_rejected_with_a_helpful_message() -> None:
    with pytest.raises(InvalidTransitionError, match="Cannot CHECK_IN while PRESENT") as info:
        next_state(S.PRESENT, E.CHECK_IN)
    assert info.value.allowed == ["CHECK_OUT", "TEMPORARY_CHECK_OUT"]


def test_cannot_check_out_during_a_temporary_exit() -> None:
    with pytest.raises(InvalidTransitionError):
        next_state(S.TEMPORARY_EXIT, E.CHECK_OUT)


def test_full_school_day() -> None:
    state = S.OUTSIDE
    for event in (E.CHECK_IN, E.TEMPORARY_CHECK_OUT, E.RETURN, E.CHECK_OUT):
        state = next_state(state, event)
    assert state is S.OUTSIDE


def test_allowed_events() -> None:
    assert allowed_events(S.OUTSIDE) == [E.CHECK_IN]
    assert allowed_events(S.TEMPORARY_EXIT) == [E.RETURN]

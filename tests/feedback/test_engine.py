import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.feedback.engine import FeedbackEngine
from coding_agent_harness.feedback.models import FailureCategory, VerificationRun


def failed_run(message: str, *, count: int = 1) -> VerificationRun:
    return VerificationRun(
        name="test",
        ok=False,
        output=f"tests/test_add.py::test_add FAILED\nAssertionError: {message}",
        failure_count=count,
    )


@pytest.mark.parametrize("second_count", [2, 3])
def test_second_same_or_worse_failure_round_waits_for_user(second_count: int) -> None:
    engine = FeedbackEngine()

    first = engine.evaluate([], failed_run("same", count=2))
    second = engine.evaluate(
        [first.observation], failed_run("same-second", count=second_count)
    )

    assert second.next_state is TaskState.WAITING_USER
    assert second.reason_code == "NO_PROGRESS"


def test_lower_failure_count_resets_no_progress() -> None:
    engine = FeedbackEngine()
    first = engine.evaluate([], failed_run("first", count=3))

    second = engine.evaluate([first.observation], failed_run("second", count=2))

    assert second.next_state is TaskState.CORRECTING
    assert second.reason_code == "CORRECTION_REQUIRED"


def test_changed_failure_category_resets_no_progress() -> None:
    engine = FeedbackEngine()
    first = engine.evaluate([], failed_run("first", count=2))

    second = engine.evaluate(
        [first.observation],
        VerificationRun(
            name="lint", ok=False, output="ruff: lint failure", failure_count=2
        ),
    )

    assert second.next_state is TaskState.CORRECTING
    assert second.reason_code == "CORRECTION_REQUIRED"


def test_unknown_failure_counts_do_not_claim_no_progress() -> None:
    engine = FeedbackEngine()
    first = engine.evaluate(
        [],
        VerificationRun(name="test", ok=False, output="AssertionError: first", failure_count=None),
    )
    second = engine.evaluate(
        [first.observation],
        VerificationRun(name="test", ok=False, output="AssertionError: second", failure_count=None),
    )

    assert second.next_state is TaskState.CORRECTING
    assert second.reason_code == "CORRECTION_REQUIRED"


def test_same_fingerprint_is_limited_to_three_verification_attempts() -> None:
    engine = FeedbackEngine()
    first = engine.evaluate([], failed_run("same"))
    second = engine.evaluate([first.observation], failed_run("same"))
    third = engine.evaluate([first.observation, second.observation], failed_run("same"))

    assert second.reason_code == "NO_PROGRESS"
    assert third.next_state is TaskState.WAITING_USER
    assert third.reason_code == "FINGERPRINT_BUDGET"


def test_total_verification_budget_is_eight_attempts() -> None:
    engine = FeedbackEngine()
    history = [
        engine.evaluate([], failed_run(f"failure-{index}")).observation
        for index in range(7)
    ]

    decision = engine.evaluate(history, failed_run("failure-8"))

    assert decision.next_state is TaskState.WAITING_USER
    assert decision.reason_code == "VERIFICATION_BUDGET"


def test_classifier_and_fingerprint_ignore_transient_locations_and_timings() -> None:
    engine = FeedbackEngine()
    first = engine.evaluate(
        [],
        VerificationRun(
            name="test",
            ok=False,
            output="C:\\Temp\\run-1\\test_add.py:14: AssertionError: expected 3 in 0.12s",
        ),
    )
    second = engine.evaluate(
        [],
        VerificationRun(
            name="test",
            ok=False,
            output="D:\\work\\run-2\\test_add.py:999: AssertionError: expected 3 in 9.99s",
        ),
    )

    assert first.observation.category is FailureCategory.TEST
    assert first.observation.fingerprint == second.observation.fingerprint

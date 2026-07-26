from collections.abc import Sequence

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.feedback.classifier import classify
from coding_agent_harness.feedback.fingerprint import fingerprint
from coding_agent_harness.feedback.models import FeedbackDecision, FeedbackObservation, VerificationRun


class FeedbackEngine:
    """仅依据已落盘观察值作出可重放的下一步反馈决定。"""

    max_same_fingerprint = 3
    max_verification_runs = 8

    def evaluate(
        self,
        history: Sequence[FeedbackObservation],
        run: VerificationRun,
    ) -> FeedbackDecision:
        category = classify(run)
        observation = FeedbackObservation(
            category=category,
            fingerprint=fingerprint(run, category),
            failure_count=run.failure_count,
        )
        if len(history) + 1 >= self.max_verification_runs:
            return FeedbackDecision(
                observation=observation,
                next_state=TaskState.WAITING_USER,
                reason_code="VERIFICATION_BUDGET",
            )
        if sum(item.fingerprint == observation.fingerprint for item in history) + 1 >= self.max_same_fingerprint:
            return FeedbackDecision(
                observation=observation,
                next_state=TaskState.WAITING_USER,
                reason_code="FINGERPRINT_BUDGET",
            )
        if len(history) >= 2:
            baseline, previous = history[-2:]
            if (
                baseline.category is previous.category is observation.category
                and baseline.failure_count is not None
                and previous.failure_count is not None
                and observation.failure_count is not None
                and previous.failure_count >= baseline.failure_count
                and observation.failure_count >= previous.failure_count
            ):
                return FeedbackDecision(
                    observation=observation,
                    next_state=TaskState.WAITING_USER,
                    reason_code="NO_PROGRESS",
                )
        return FeedbackDecision(
            observation=observation,
            next_state=TaskState.CORRECTING,
            reason_code="CORRECTION_REQUIRED",
        )

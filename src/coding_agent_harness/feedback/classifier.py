from coding_agent_harness.feedback.models import FailureCategory, VerificationRun


def classify(run: VerificationRun) -> FailureCategory:
    text = f"{run.name}\n{run.output}".casefold()
    if "timeout" in text or "timed out" in text:
        return FailureCategory.TIMEOUT
    if "output limit" in text or "output_limit" in text:
        return FailureCategory.OUTPUT_LIMIT
    if "policy" in text or "approval_required" in text or "denied" in text:
        return FailureCategory.POLICY
    if "ruff" in text or "flake8" in text or "lint" in text:
        return FailureCategory.LINT
    if "mypy" in text or "pyright" in text or "typecheck" in text:
        return FailureCategory.TYPECHECK
    if "build" in text or "compile" in text:
        return FailureCategory.BUILD
    if "pytest" in text or "assertionerror" in text or " failed" in text:
        return FailureCategory.TEST
    if "tool" in text or "unsupported" in text:
        return FailureCategory.TOOL
    return FailureCategory.UNKNOWN

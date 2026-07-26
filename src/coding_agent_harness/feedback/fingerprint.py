import hashlib
import re

from coding_agent_harness.feedback.models import FailureCategory, VerificationRun


_ABSOLUTE_DIRECTORY = re.compile(r"(?:[A-Za-z]:)?[\\/](?:[^\s:\\/]+[\\/])+")
_LINE_COLUMN = re.compile(r":\d+(?::\d+)?")
_DURATION = re.compile(r"\b(?:in\s+)?\d+(?:\.\d+)?s\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def fingerprint(run: VerificationRun, category: FailureCategory) -> str:
    normalized = _ABSOLUTE_DIRECTORY.sub("", run.output)
    normalized = _LINE_COLUMN.sub(":<line>", normalized)
    normalized = _DURATION.sub("<duration>", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip().casefold()
    digest = hashlib.sha256(
        f"{category.value}\n{run.name.casefold()}\n{normalized}".encode("utf-8")
    ).hexdigest()
    return digest

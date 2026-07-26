"""跨传输与持久化边界共享的确定性数据上限。"""

MAX_REQUIREMENT_BYTES = 64 * 1024


class RequirementTooLargeError(ValueError):
    """任务需求在规范化前后超过共享 UTF-8 字节上限。"""


def validate_requirement_size(requirement: str) -> str:
    """按 UTF-8 字节数验证任务需求，避免不同边界采用不同单位。"""

    if len(requirement.encode("utf-8")) > MAX_REQUIREMENT_BYTES:
        raise RequirementTooLargeError("任务需求超过 UTF-8 字节上限")
    return requirement

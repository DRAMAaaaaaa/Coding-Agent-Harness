import os
import re
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, JsonValue


_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
    {"api_key", "token", "secret", "password", "client_secret"}
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_ASSIGNMENT = re.compile(
    r"(?i)[\"']?\b(?:api_key|token|secret|password|client_secret)\b[\"']?\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.DOTALL,
)


class RedactionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    value: JsonValue
    rule_names: tuple[str, ...]


class Redactor:
    def __init__(self, sensitive_env: Mapping[str, str] | None = None) -> None:
        environment = sensitive_env or {}
        self._environment = {
            name: value
            for name, value in environment.items()
            if isinstance(name, str) and isinstance(value, str) and name
        }
        self._environment_values = tuple(
            sorted({value for value in self._environment.values() if value}, key=len, reverse=True)
        )
        self._environment_case_insensitive = os.name == "nt"
        flags = re.IGNORECASE if self._environment_case_insensitive else 0
        self._environment_name_patterns = tuple(
            re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", flags)
            for name in sorted(self._environment, key=len, reverse=True)
        )
        self._environment_key_names = frozenset(
            self._normalize_environment_name(name) for name in self._environment
        )

    def sanitize(self, value: object) -> RedactionResult:
        rules: set[str] = set()
        sanitized = self._sanitize_value(value, rules)
        return RedactionResult(value=sanitized, rule_names=tuple(sorted(rules)))

    def _sanitize_value(self, value: object, rules: set[str]) -> JsonValue:
        if isinstance(value, BaseException):
            try:
                message = str(value)
            except Exception:
                message = _REDACTED
            return {
                "exception_type": type(value).__name__,
                "message": self._sanitize_text(message, rules),
            }
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._sanitize_text(value, rules)
        if isinstance(value, (list, tuple)):
            return [self._sanitize_value(item, rules) for item in value]
        if isinstance(value, dict):
            sanitized: dict[str, JsonValue] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError("不支持的脱敏值类型")
                sanitized_key = self._sanitize_text(key, rules)
                if self._is_sensitive_key(key):
                    rules.add(self._key_rule(key))
                    sanitized[sanitized_key] = _REDACTED
                else:
                    sanitized[sanitized_key] = self._sanitize_value(item, rules)
            return sanitized
        raise TypeError("不支持的脱敏值类型")

    def _sanitize_text(self, text: str, rules: set[str]) -> str:
        sanitized, count = _PRIVATE_KEY.subn(_REDACTED, text)
        if count:
            rules.add("PRIVATE_KEY")
        sanitized, count = _BEARER.subn(_REDACTED, sanitized)
        if count:
            rules.add("BEARER_TOKEN")
        sanitized, count = _ASSIGNMENT.subn(_REDACTED, sanitized)
        if count:
            rules.add("SECRET_ASSIGNMENT")
        for pattern in self._environment_name_patterns:
            sanitized, count = pattern.subn(_REDACTED, sanitized)
            if count:
                rules.add("SENSITIVE_ENV_NAME")
        for secret in self._environment_values:
            if secret in sanitized:
                sanitized = sanitized.replace(secret, _REDACTED)
                rules.add("SENSITIVE_ENV_VALUE")
        return sanitized

    def _is_sensitive_key(self, key: str) -> bool:
        return (
            key.casefold() in _SENSITIVE_KEYS
            or self._normalize_environment_name(key) in self._environment_key_names
        )

    def _key_rule(self, key: str) -> str:
        if self._normalize_environment_name(key) in self._environment_key_names:
            return "SENSITIVE_ENV_NAME"
        return "SECRET_ASSIGNMENT"

    def _normalize_environment_name(self, name: str) -> str:
        return name.casefold() if self._environment_case_insensitive else name

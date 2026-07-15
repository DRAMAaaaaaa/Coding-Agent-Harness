import json
import os

import pytest

from coding_agent_harness.governance.redaction import RedactionResult, Redactor


def test_sanitize_recurses_without_mutating_input_and_sorts_rule_names() -> None:
    original = {
        "标题": "保留 Unicode：你好",
        "nested": [
            "Authorization: Bearer abc.def-123",
            ("api_key = 'top-secret'",),
        ],
    }

    result = Redactor().sanitize(original)

    assert isinstance(result, RedactionResult)
    assert result.value == {
        "标题": "保留 Unicode：你好",
        "nested": ["Authorization: [REDACTED]", ["[REDACTED]"],],
    }
    assert result.rule_names == ("BEARER_TOKEN", "SECRET_ASSIGNMENT")
    assert original["nested"][0] == "Authorization: Bearer abc.def-123"


def test_sanitize_redacts_private_key_environment_name_and_value() -> None:
    private_key = (
        "-----BEGIN PRIVATE KEY-----\n"
        "c3VwZXItc2VjcmV0\n"
        "-----END PRIVATE KEY-----"
    )
    secret_value = "env-value-绝密"
    redactor = Redactor(
        sensitive_env={"DEPLOY_TOKEN": secret_value},
    )

    result = redactor.sanitize(
        {
            "text": f"DEPLOY_TOKEN={secret_value}\nkey={private_key}",
            "DEPLOY_TOKEN": "a value that must be replaced as a whole",
        }
    )

    serialized = json.dumps(result.value, ensure_ascii=False, sort_keys=True)
    assert result.value["[REDACTED]"] == "[REDACTED]"
    assert private_key not in serialized
    assert secret_value not in serialized
    assert "DEPLOY_TOKEN" not in serialized
    assert result.rule_names == (
        "PRIVATE_KEY",
        "SENSITIVE_ENV_NAME",
        "SENSITIVE_ENV_VALUE",
    )


def test_empty_environment_name_or_value_does_not_match_all_text() -> None:
    result = Redactor(sensitive_env={"": "", "EMPTY": ""}).sanitize("ordinary text")

    assert result.value == "ordinary text"
    assert result.rule_names == ()


def test_sensitive_dict_key_replaces_entire_nested_value() -> None:
    result = Redactor().sanitize(
        {"password": {"nested": ["must", "not", "survive"]}, "safe": 7}
    )

    assert result.value == {"password": "[REDACTED]", "safe": 7}
    assert result.rule_names == ("SECRET_ASSIGNMENT",)


def test_quoted_json_secret_assignment_is_redacted() -> None:
    result = Redactor().sanitize('{"client_secret": "quoted-secret"}')

    assert result.value == "{[REDACTED]}"
    assert result.rule_names == ("SECRET_ASSIGNMENT",)


def test_exception_is_copied_as_type_and_sanitized_message_only() -> None:
    secret = "exception-token-123"
    error = RuntimeError(f"request failed: Bearer {secret}")

    result = Redactor().sanitize(error)

    assert result.value == {
        "exception_type": "RuntimeError",
        "message": "request failed: [REDACTED]",
    }
    assert result.rule_names == ("BEARER_TOKEN",)
    rendered = " ".join(
        [str(result), repr(result), json.dumps(result.value, ensure_ascii=False)]
    )
    assert secret not in rendered
    assert error not in result.value.values()


class _SecretRepr:
    def __repr__(self) -> str:
        raise AssertionError("不得调用不支持对象的 repr")


def test_unsupported_object_is_rejected_without_calling_repr() -> None:
    with pytest.raises(TypeError, match="^不支持的脱敏值类型$"):
        Redactor().sanitize(_SecretRepr())


class _ExplodingMessageError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("Bearer nested-exception-secret")

    def __repr__(self) -> str:
        raise AssertionError("不得调用恶意异常的 repr")


def test_exception_with_failing_str_becomes_fixed_safe_message() -> None:
    result = Redactor().sanitize(_ExplodingMessageError())

    assert result.value == {
        "exception_type": "_ExplodingMessageError",
        "message": "[REDACTED]",
    }
    assert result.rule_names == ()
    rendered = json.dumps(result.value, ensure_ascii=False)
    assert "nested-exception-secret" not in rendered


def test_environment_name_uses_identifier_boundaries_and_platform_case() -> None:
    result = Redactor(sensitive_env={"TOKEN": "exact-secret"}).sanitize(
        "TOKENIZER TOKEN token"
    )

    expected = (
        "TOKENIZER [REDACTED] [REDACTED]"
        if os.name == "nt"
        else "TOKENIZER [REDACTED] token"
    )
    assert result.value == expected
    assert result.rule_names == ("SENSITIVE_ENV_NAME",)


def test_environment_dict_key_uses_same_platform_case_semantics() -> None:
    redactor = Redactor(sensitive_env={"DEPLOY_KEY": "exact-secret"})
    boundary = redactor.sanitize({"DEPLOY_KEYSTONE": "visible"})
    differently_cased = redactor.sanitize({"deploy_key": {"nested": "visible"}})

    assert boundary.value == {"DEPLOY_KEYSTONE": "visible"}
    if os.name == "nt":
        assert differently_cased.value == {"[REDACTED]": "[REDACTED]"}
        assert differently_cased.rule_names == ("SENSITIVE_ENV_NAME",)
    else:
        assert differently_cased.value == {"deploy_key": {"nested": "visible"}}
        assert differently_cased.rule_names == ()

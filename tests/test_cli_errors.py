"""Tests for the CLI JSON/exit-code error contract (ticket 30 Scope 3)."""

import json

import pytest
import typer

from ghstars.cli import errors as errors_module
from ghstars.cli.errors import EXIT_PARTIAL, EXIT_RETRYABLE, EXIT_TERMINAL, fail


def test_fail_prints_plain_prose_without_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(typer.Exit):
        fail("boom", code=errors_module.CODE_INVALID_INPUT, json_output=False)
    captured = capsys.readouterr()
    assert captured.err == "error: boom\n"


def test_fail_under_json_emits_stable_error_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(typer.Exit):
        fail(
            "no local record for 'a/b'",
            code=errors_module.CODE_NO_LOCAL_RECORD,
            json_output=True,
            target="a/b",
        )
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload == {
        "error": {
            "code": "no_local_record",
            "message": "no local record for 'a/b'",
            "target": "a/b",
        }
    }


def test_fail_under_json_omits_target_when_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(typer.Exit):
        fail("boom", code=errors_module.CODE_INVALID_INPUT, json_output=True)
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert "target" not in payload["error"]


@pytest.mark.parametrize(
    "code",
    [
        errors_module.CODE_RATE_LIMIT_EXCEEDED,
        errors_module.CODE_STATE_LOCK_HELD,
        errors_module.CODE_NETWORK_FAILURE,
    ],
)
def test_fail_exits_retryable_for_retryable_codes(code: str) -> None:
    with pytest.raises(typer.Exit) as exc_info:
        fail("boom", code=code, json_output=False)
    assert exc_info.value.exit_code == EXIT_RETRYABLE


@pytest.mark.parametrize(
    "code",
    [
        errors_module.CODE_NO_LOCAL_RECORD,
        errors_module.CODE_STAR_ARCHIVED,
        errors_module.CODE_LIST_MEMBERSHIP_DRIFT,
        errors_module.CODE_TAG_PUSH_FAILED,
        errors_module.CODE_INVALID_INPUT,
        errors_module.CODE_UNKNOWN_FIELD,
        errors_module.CODE_TOOL_UNAVAILABLE,
    ],
)
def test_fail_exits_terminal_for_non_retryable_codes(code: str) -> None:
    with pytest.raises(typer.Exit) as exc_info:
        fail("boom", code=code, json_output=False)
    assert exc_info.value.exit_code == EXIT_TERMINAL


def test_exit_codes_are_the_three_documented_flat_values() -> None:
    assert EXIT_TERMINAL == 1
    assert EXIT_RETRYABLE == 3
    assert EXIT_PARTIAL == 4

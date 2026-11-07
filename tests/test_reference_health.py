"""Offline transport checks: no external DNS or HTTP requests."""

from subprocess import CompletedProcess

import pytest

from mri_rag.reference_health import check_reference
from mri_rag.reference_policy import ReferencePolicyError, ReferenceState

FDA = "https://www.fda.gov/media/116492/download"


def response(headers, code=0):
    return CompletedProcess([], code, stdout=headers, stderr="")


def test_valid_response_is_pending_document_review():
    commands = []

    def runner(argv, **kwargs):
        commands.append((argv, kwargs))
        return response("HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n\r\n")

    result = check_reference(
        FDA,
        resolver=lambda host: ["8.8.8.8"],
        runner=runner,
    )

    assert result.http_status == 200
    assert result.state == ReferenceState.PENDING_REVIEW
    assert "--resolve" in commands[0][0]
    assert "www.fda.gov:443:8.8.8.8" in commands[0][0]
    assert "--location" not in commands[0][0]
    assert commands[0][1]["env"].get("HTTPS_PROXY") is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, ReferenceState.BROKEN),
        (410, ReferenceState.BROKEN),
        (403, ReferenceState.INACCESSIBLE),
        (429, ReferenceState.INACCESSIBLE),
        (503, ReferenceState.INACCESSIBLE),
    ],
)
def test_status_classification(status, expected):
    result = check_reference(
        FDA,
        resolver=lambda host: ["8.8.8.8"],
        runner=lambda argv, **kwargs: response(f"HTTP/1.1 {status} Result\r\n\r\n"),
    )
    assert result.state == expected


def test_private_dns_never_invokes_transport():
    def forbidden_runner(argv, **kwargs):
        pytest.fail("Transport must not be invoked")

    result = check_reference(
        FDA,
        resolver=lambda host: ["8.8.8.8", "127.0.0.1"],
        runner=forbidden_runner,
    )
    assert result.reason == "dns_unavailable_or_blocked"


def test_redirect_outside_allowlist_blocked():
    def runner(argv, **kwargs):
        return response("HTTP/1.1 302 Found\r\nLocation: https://evil.example/\r\n\r\n")

    with pytest.raises(ReferencePolicyError):
        check_reference(
            FDA,
            resolver=lambda host: ["8.8.8.8"],
            runner=runner,
        )


def test_transport_failure_is_not_broken():
    result = check_reference(
        FDA,
        resolver=lambda host: ["8.8.8.8"],
        runner=lambda argv, **kwargs: response("", code=60),
    )
    assert result.state == ReferenceState.INACCESSIBLE
    assert result.reason == "curl_failure"


def test_no_proxy_or_curl_config_inheritance():
    captured = {}

    def runner(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return response("HTTP/1.1 200 OK\r\n\r\n")

    check_reference(
        FDA,
        resolver=lambda host: ["8.8.8.8"],
        runner=runner,
    )

    assert captured["argv"][1] == "-q"
    assert "--noproxy" in captured["argv"]
    assert "--max-time" in captured["argv"]
    assert "--max-filesize" in captured["argv"]
    assert "HOME" in captured["env"]
    assert "ALL_PROXY" not in captured["env"]


def test_ipv6_pinning():
    captured = {}

    def runner(argv, **kwargs):
        captured["argv"] = argv
        return response("HTTP/1.1 200 OK\\r\\n\\r\\n")

    result = check_reference(
        FDA,
        resolver=lambda host: ["2606:4700:4700::1111"],
        runner=runner,
    )

    assert result.state == ReferenceState.PENDING_REVIEW

    assert "www.fda.gov:443:[2606:4700:4700::1111]" in captured["argv"]


def test_partial_http_response_is_not_verified():
    result = check_reference(
        FDA,
        resolver=lambda host: ["8.8.8.8"],
        runner=lambda argv, **kwargs: response("HTTP/1.1 206 Partial Content\\r\\n\\r\\n"),
    )

    assert result.http_status == 206
    assert result.state == ReferenceState.PENDING_REVIEW


def test_real_subprocess_output_limit():
    import sys
    from pathlib import Path

    from mri_rag.reference_health import (
        HeaderOutputLimit,
        _run_bounded,
    )

    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('X' * 70000)",
    ]

    with pytest.raises(HeaderOutputLimit):
        _run_bounded(
            command,
            env={"PATH": "/usr/bin:/bin"},
            cwd=str(Path.cwd()),
        )


def test_real_subprocess_timeout():
    import subprocess
    import sys
    from pathlib import Path

    from mri_rag.reference_health import _run_bounded

    command = [
        sys.executable,
        "-c",
        "import time; time.sleep(2)",
    ]

    with pytest.raises(subprocess.TimeoutExpired):
        _run_bounded(
            command,
            env={"PATH": "/usr/bin:/bin"},
            cwd=str(Path.cwd()),
            timeout=0.1,
        )

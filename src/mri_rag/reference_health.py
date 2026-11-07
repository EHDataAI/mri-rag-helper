"""Bounded, pinned HTTPS reference checker.

HTTP availability is not proof of document identity or clinical validity.
"""

from __future__ import annotations

import os
import selectors
import socket

# Security review: subprocess is needed for the fixed curl executable.
# Execution uses controlled argv, environment, timeout and output limits.
import subprocess  # nosec B404
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from .reference_policy import (
    ReferencePolicyError,
    ReferenceState,
    classify_http_status,
    validate_public_addresses,
    validate_reference_url,
)

MAX_REDIRECTS = 3
MAX_HEADER_OUTPUT = 65536
CURL = "/usr/bin/curl"


class HeaderOutputLimit(RuntimeError):
    """HTTP header output exceeded the configured byte limit."""


def _run_bounded(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: str,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with bounded stdout and a hard deadline."""
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    received = 0

    # S603: argv is supplied as an argument list, without shell execution.
    # The production caller constructs the command with a fixed curl binary.
    process = subprocess.Popen(  # noqa: S603  # nosec B603
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=env,
        cwd=cwd,
    )

    selector = selectors.DefaultSelector()

    try:
        if process.stdout is None:
            raise OSError("Missing subprocess stdout")

        selector.register(process.stdout, selectors.EVENT_READ)

        while True:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)

            events = selector.select(remaining)

            if not events:
                continue

            data = os.read(process.stdout.fileno(), 8192)

            if not data:
                break

            received += len(data)

            if received > MAX_HEADER_OUTPUT:
                raise HeaderOutputLimit("HTTP header output exceeded limit")

            chunks.append(data)

        remaining = max(0.001, deadline - time.monotonic())

        return_code = process.wait(timeout=remaining)

        return subprocess.CompletedProcess(
            argv,
            return_code,
            stdout=b"".join(chunks).decode("latin-1"),
            stderr="",
        )

    finally:
        selector.close()

        if process.poll() is None:
            process.kill()

        process.wait()

        if process.stdout is not None:
            process.stdout.close()


@dataclass(frozen=True)
class ReferenceCheck:
    requested_url: str
    final_url: str
    state: ReferenceState
    http_status: int | None
    redirects: int
    reason: str


def resolve_public_ips(hostname: str) -> list[str]:
    """Resolve all addresses; caller rejects the entire set if unsafe."""
    answers = socket.getaddrinfo(
        hostname,
        443,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return list(dict.fromkeys(item[4][0] for item in answers))


def parse_headers(raw: str) -> tuple[int, str | None]:
    """Extract the final HTTP response block from curl headers."""
    blocks = raw.replace("\r\n", "\n").split("\n\n")

    for block in reversed(blocks):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith("HTTP/"):
            continue

        parts = lines[0].split()
        if len(parts) < 2 or not parts[1].isdigit():
            continue

        status = int(parts[1])
        location = None

        for line in lines[1:]:
            if line.lower().startswith("location:"):
                location = line.split(":", 1)[1].strip()
                break

        return status, location

    raise ReferencePolicyError("No valid HTTP response headers")


def check_reference(
    url: str,
    *,
    resolver=resolve_public_ips,
    runner=subprocess.run,
) -> ReferenceCheck:
    """Check an approved URL, validating each redirect independently.

    A single validated public IP is pinned for each HTTPS request.
    No external network call occurs when resolver and runner are mocked.
    """
    requested = url
    current = url
    visited: set[str] = set()

    for redirects in range(MAX_REDIRECTS + 1):
        target = validate_reference_url(current)

        if current in visited:
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "redirect_loop",
            )

        visited.add(current)

        try:
            addresses = validate_public_addresses(list(resolver(target.hostname)))
        except (OSError, ReferencePolicyError):
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "dns_unavailable_or_blocked",
            )

        # Fail closed: there is no retry to another, unvalidated destination.
        chosen_ip = addresses[0]
        pinned_ip = f"[{chosen_ip}]" if ":" in chosen_ip else chosen_ip
        resolve_arg = f"{target.hostname}:443:{pinned_ip}"

        argv = [
            CURL,
            "-q",
            "--silent",
            "--show-error",
            "--http1.1",
            "--noproxy",
            "*",
            "--proto",
            "=https",
            "--proto-redir",
            "=https",
            "--max-redirs",
            "0",
            "--connect-timeout",
            "3",
            "--max-time",
            "8",
            "--max-filesize",
            "65536",
            "--range",
            "0-0",
            "--output",
            "/dev/null",
            "--dump-header",
            "-",
            "--resolve",
            resolve_arg,
            "--",
            current,
        ]

        # Do not inherit proxy, curl home/configuration or certificate overrides.
        environment = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "HOME": "/nonexistent",
        }

        try:
            if runner is subprocess.run:
                result = _run_bounded(
                    argv,
                    env=environment,
                    cwd=str(Path(__file__).resolve().parents[2]),
                    timeout=10.0,
                )
            else:
                # Preserve dependency injection for offline unit tests.
                result = runner(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                    env=environment,
                    cwd=str(Path(__file__).resolve().parents[2]),
                )

        except HeaderOutputLimit:
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "header_limit",
            )

        except (OSError, subprocess.TimeoutExpired):
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "transport_failure",
            )

        if result.returncode != 0:
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "curl_failure",
            )

        if len(result.stdout) > MAX_HEADER_OUTPUT:
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "header_limit",
            )

        try:
            status, location = parse_headers(result.stdout)
        except ReferencePolicyError:
            return ReferenceCheck(
                requested,
                current,
                ReferenceState.INACCESSIBLE,
                None,
                redirects,
                "invalid_http_headers",
            )

        if status in (301, 302, 303, 307, 308):
            if not location:
                return ReferenceCheck(
                    requested,
                    current,
                    ReferenceState.INACCESSIBLE,
                    status,
                    redirects,
                    "missing_redirect_location",
                )

            if redirects == MAX_REDIRECTS:
                return ReferenceCheck(
                    requested,
                    current,
                    ReferenceState.INACCESSIBLE,
                    status,
                    redirects,
                    "redirect_limit",
                )

            candidate = urljoin(current, location)

            # Validate before continuing to DNS or transport.
            validate_reference_url(candidate)
            current = candidate
            continue

        return ReferenceCheck(
            requested,
            current,
            classify_http_status(status),
            status,
            redirects,
            "http_response",
        )

    raise AssertionError("Unreachable redirect state")

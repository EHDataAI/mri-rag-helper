"""Pure, offline security policy for external academic references."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from .corpus import ALLOWED_HOSTS


class ReferenceState(StrEnum):
    VERIFIED = "VERIFIED"
    BROKEN = "BROKEN"
    INACCESSIBLE = "INACCESSIBLE"
    PENDING_REVIEW = "PENDING_REVIEW"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    STALE = "STALE"


class ReferencePolicyError(ValueError):
    """An external reference violates the approved URL/network policy."""


@dataclass(frozen=True)
class ReferenceTarget:
    url: str
    hostname: str
    port: int


def validate_reference_url(
    url: str,
    allowed_hosts: frozenset[str] | None = None,
) -> ReferenceTarget:
    """Validate an approved HTTPS URL without opening a connection."""
    if not isinstance(url, str):
        raise ReferencePolicyError("URL must be a string")

    if not url or len(url) > 2048:
        raise ReferencePolicyError("Invalid URL length")

    if any(ord(ch) < 33 or ord(ch) == 127 for ch in url):
        raise ReferencePolicyError("Control or whitespace in URL")

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ReferencePolicyError("Malformed URL") from exc

    if (
        parts.scheme != "https"
        or not parts.hostname
        or not parts.netloc
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or "\\" in url
    ):
        raise ReferencePolicyError("Disallowed URL structure")

    if port not in (None, 443):
        raise ReferencePolicyError("Disallowed port")

    hostname = parts.hostname

    if hostname is None:
        raise ReferencePolicyError("Missing hostname")

    approved = frozenset(ALLOWED_HOSTS) if allowed_hosts is None else allowed_hosts

    if hostname not in approved:
        raise ReferencePolicyError("Host not approved")

    if parts.netloc.lower() not in (
        hostname,
        f"{hostname}:443",
    ):
        raise ReferencePolicyError("Unexpected authority")

    # Reject ambiguous encodings while preserving valid UTF-8.
    component = parts.path + "?" + parts.query

    if re.search(r"%(?![0-9A-Fa-f]{2})", component):
        raise ReferencePolicyError("Malformed percent encoding")

    octets = [
        int(match.group(1), 16)
        for match in re.finditer(
            r"%([0-9A-Fa-f]{2})",
            component,
        )
    ]

    if any(value < 32 or value == 127 or value in (47, 92) for value in octets):
        raise ReferencePolicyError("Unsafe encoded character")

    if re.search(r"%2[eE]", parts.path):
        raise ReferencePolicyError("Ambiguous encoded path")

    if "//" in parts.path:
        raise ReferencePolicyError("Repeated path separator")

    if any(segment in (".", "..") for segment in parts.path.split("/")):
        raise ReferencePolicyError("Path traversal")

    return ReferenceTarget(url, hostname, 443)


def validate_public_addresses(addresses: list[str]) -> tuple[str, ...]:
    """Fail closed if any DNS answer is not globally routable."""
    if not addresses:
        raise ReferencePolicyError("Empty DNS response")

    approved: list[str] = []

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ReferencePolicyError("Invalid IP address") from exc

        if not ip.is_global:
            raise ReferencePolicyError("Non-public IP address")

        approved.append(str(ip))

    return tuple(approved)


def classify_http_status(status: int) -> ReferenceState:
    """Classification only; it does not establish clinical validity."""
    if not isinstance(status, int) or isinstance(status, bool):
        raise ValueError("HTTP status must be an integer")

    if 200 <= status < 300:
        return ReferenceState.PENDING_REVIEW

    if status in (404, 410):
        return ReferenceState.BROKEN

    if status in (401, 403, 408, 425, 429):
        return ReferenceState.INACCESSIBLE

    if 500 <= status < 600:
        return ReferenceState.INACCESSIBLE

    return ReferenceState.PENDING_REVIEW

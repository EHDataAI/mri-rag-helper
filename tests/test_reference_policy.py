"""Offline adversarial checks for ERIG reference policy."""

import pytest

from mri_rag.reference_policy import (
    ReferencePolicyError,
    ReferenceState,
    classify_http_status,
    validate_public_addresses,
    validate_reference_url,
)


def test_approved_fda_reference():
    target = validate_reference_url("https://www.fda.gov/media/116492/download")
    assert target.hostname == "www.fda.gov"
    assert target.port == 443


@pytest.mark.parametrize(
    "url",
    [
        "http://www.fda.gov/media/116492/download",
        "https://evil.example/document",
        "https://www.fda.gov.evil.example/document",
        "https://evil.example@www.fda.gov/document",
        "https://www.fda.gov@evil.example/document",
        "https://www.fda.gov:8443/document",
        "https://www.fda.gov/document#fragment",
        "https://www.fda.gov\\@evil.example/document",
        "https://127.0.0.1/document",
        "https://www.fda.gov/white space",
        "",
    ],
)
def test_reject_unsafe_urls(url):
    with pytest.raises(ReferencePolicyError):
        validate_reference_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.10",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "not-an-ip",
    ],
)
def test_reject_nonpublic_dns_results(address):
    with pytest.raises(ReferencePolicyError):
        validate_public_addresses([address])


def test_public_addresses():
    assert validate_public_addresses(["8.8.8.8"]) == ("8.8.8.8",)


def test_mixed_dns_response_is_blocked():
    with pytest.raises(ReferencePolicyError):
        validate_public_addresses(["8.8.8.8", "127.0.0.1"])


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, ReferenceState.PENDING_REVIEW),
        (204, ReferenceState.PENDING_REVIEW),
        (404, ReferenceState.BROKEN),
        (410, ReferenceState.BROKEN),
        (403, ReferenceState.INACCESSIBLE),
        (429, ReferenceState.INACCESSIBLE),
        (500, ReferenceState.INACCESSIBLE),
        (503, ReferenceState.INACCESSIBLE),
    ],
)
def test_http_classification(status, expected):
    assert classify_http_status(status) == expected


def test_http_200_is_not_automatically_verified():
    assert classify_http_status(200) != ReferenceState.VERIFIED


def test_empty_dns_response_rejected():
    with pytest.raises(ReferencePolicyError):
        validate_public_addresses([])


@pytest.mark.parametrize(
    "url",
    [
        "https://www.fda.gov/%2e%2e/admin",
        "https://www.fda.gov/%2f%2fevil.example/",
        "https://www.fda.gov//evil.example/path",
        "https://www.fda.gov/media/116492/download?x=%0d%0a",
        "https://www.fda.gov/%5cadmin",
        "https://www.fda.gov/../admin",
        "https://www.fda.gov/%GG",
    ],
)
def test_reject_ambiguous_urls(url):
    with pytest.raises(ReferencePolicyError):
        validate_reference_url(url)


def test_utf8_encoded_reference_is_accepted():
    url = (
        "https://www.nibib.nih.gov/espanol/temas-cientificos/"
        "imagen-por-resonancia-magn%C3%A9tica-irm"
    )

    target = validate_reference_url(url)

    assert target.hostname == "www.nibib.nih.gov"


def test_explicit_https_port():
    target = validate_reference_url("https://www.fda.gov:443/media/116492/download")

    assert target.port == 443

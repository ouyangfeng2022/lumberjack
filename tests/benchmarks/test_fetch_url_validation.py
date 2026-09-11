from __future__ import annotations

import socket

import pytest

from benchmarks.fetch_parser_corpora import _validated_download_url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/corpus.json",
        "file:///etc/passwd",
        "gopher://example.com/x",
    ],
)
def test_validated_download_url_rejects_non_http_schemes(url: str) -> None:
    with pytest.raises(ValueError, match="unsupported URL scheme"):
        _validated_download_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/corpus.json",
        "http://127.0.0.1/corpus.json",
        "http://10.0.0.1/corpus.json",
        "http://192.168.1.1/corpus.json",
        "http://169.254.1.1/corpus.json",
        "http://[::1]/corpus.json",
    ],
)
def test_validated_download_url_rejects_local_and_private_targets(url: str) -> None:
    with pytest.raises(ValueError):
        _validated_download_url(url)


def _resolve_to(address: str) -> object:
    """getaddrinfo stub pinning every lookup to *address*."""

    def _getaddrinfo(*_args: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    return _getaddrinfo


def test_validated_download_url_returns_public_target_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolve_to("93.184.216.34"))

    url = "https://example.com/corpus.json"
    assert _validated_download_url(url) == url


def test_validated_download_url_rejects_host_resolving_to_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolve_to("10.1.2.3"))

    with pytest.raises(ValueError, match="non-public"):
        _validated_download_url("https://example.com/corpus.json")

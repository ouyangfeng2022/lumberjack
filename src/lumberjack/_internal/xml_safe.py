"""Hardening helpers for parsing untrusted XML payloads."""

from __future__ import annotations

from xml.etree import ElementTree

# Entity expansion requires a DTD; none of the formats lumberjack parses
# (OOXML parts, record XML) legitimately declares either marker.
_REJECTED_TEXT_MARKERS = ("<!DOCTYPE", "<!ENTITY")
_REJECTED_BYTES_MARKERS = tuple(
    marker.encode(encoding)
    for marker in _REJECTED_TEXT_MARKERS
    for encoding in ("utf-8", "utf-16-le", "utf-16-be")
)
_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024


def parse_untrusted_xml(payload: bytes | str) -> ElementTree.Element:
    """Parse an untrusted XML part with DTD/entity declarations rejected.

    The standard-library ElementTree expands internal DTD entities, so a
    crafted payload could exhaust memory (billion laughs). Reject DTD and
    entity declarations up front (covering str plus UTF-8/UTF-16 bytes) and
    bound the payload size. The marker scan is the sole enforcement layer:
    ``<!DOCTYPE``/``<!ENTITY`` are unsplittable, case-sensitive literals in
    every encoding expat supports, so a declaration cannot sneak past it
    (pyexpat exposes no portable ForbidDTD hook to double-check with).
    """
    if isinstance(payload, bytes) and len(payload) > _MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"XML payload is {len(payload)} bytes; limit is {_MAX_PAYLOAD_BYTES}"
        )
    if isinstance(payload, str):
        if any(marker in payload for marker in _REJECTED_TEXT_MARKERS):
            raise ValueError("XML payload declares a DTD or entity; rejected")
    elif any(marker in payload for marker in _REJECTED_BYTES_MARKERS):
        raise ValueError("XML payload declares a DTD or entity; rejected")
    return ElementTree.fromstring(payload)

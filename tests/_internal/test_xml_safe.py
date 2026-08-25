from __future__ import annotations

import pytest

from lumberjack._internal.xml_safe import parse_untrusted_xml


@pytest.mark.parametrize(
    "payload",
    [
        "<root><child>text</child></root>",
        b"<root><child>text</child></root>",
        "<root><child>text</child></root>".encode("utf-16-le"),
    ],
    ids=["str", "utf-8-bytes", "utf-16-bytes"],
)
def test_parse_untrusted_xml_accepts_well_formed_payloads(payload) -> None:
    root = parse_untrusted_xml(payload)

    assert root.tag == "root"
    child = root.find("child")
    assert child is not None
    assert child.text == "text"


@pytest.mark.parametrize(
    "payload",
    [
        '<!DOCTYPE root [<!ENTITY x "y">]><root>&x;</root>',
        b'<!DOCTYPE root [<!ENTITY x "y">]><root>&x;</root>',
        '<!DOCTYPE root [<!ENTITY x "y">]><root>&x;</root>'.encode("utf-16-le"),
        '<!DOCTYPE root [<!ENTITY x "y">]><root>&x;</root>'.encode("utf-16-be"),
        "<root><!-- <!ENTITY x 'y'> --></root>",
    ],
    ids=["str", "utf-8-bytes", "utf-16-le-bytes", "utf-16-be-bytes", "inside-comment"],
)
def test_parse_untrusted_xml_rejects_dtd_and_entity_markers(payload) -> None:
    with pytest.raises(ValueError, match="DTD or entity"):
        parse_untrusted_xml(payload)


def test_parse_untrusted_xml_rejects_oversized_bytes_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lumberjack._internal.xml_safe as xml_safe

    monkeypatch.setattr(xml_safe, "_MAX_PAYLOAD_BYTES", 16)
    with pytest.raises(ValueError, match="bytes"):
        parse_untrusted_xml(b"<root>pad-pad-pad-pad</root>")


def test_parse_untrusted_xml_raises_parse_error_for_malformed_xml() -> None:
    from xml.etree import ElementTree

    with pytest.raises(ElementTree.ParseError):
        parse_untrusted_xml("<root><unclosed></root>")

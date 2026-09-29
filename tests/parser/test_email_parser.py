from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from lumberjack import Lumberjack
from lumberjack.parser import AutoParser, EmlParser, MboxParser, MsgParser


def _message(subject: str, message_id: str, *, reply_to: str = "") -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Ada <ada@example.org>"
    message["To"] = "Bob <bob@example.org>"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    if reply_to:
        message["In-Reply-To"] = reply_to
        message["References"] = reply_to
    message.set_content(f"Body for {subject}")
    message.add_attachment(
        b"example", maintype="text", subtype="plain", filename="note.txt"
    )
    return message


def test_eml_preserves_headers_body_attachment_and_thread() -> None:
    data = _message("Hello", "<one@example.org>").as_bytes()
    tree = EmlParser().parse(data, source_path="one.eml")
    result = Lumberjack().saw(data, format="eml", source_path="one.eml")

    assert tree.root.children[0].title == "Hello"
    blocks = tree.root.children[0].blocks
    assert any(block.text == "From: Ada <ada@example.org>" for block in blocks)
    assert any(block.text == "Body for Hello" for block in blocks)
    assert any(block.attrs.get("filename") == "note.txt" for block in blocks)
    assert tree.metadata["threads"][0]["message_id"] == "<one@example.org>"
    assert any(
        location.element_id == "message:1:body"
        for chunk in result.chunks
        for location in chunk.source_locations
    )
    assert AutoParser().parse(data, source_path="one.eml").title == "Hello"


def test_mbox_preserves_message_order_and_reply_links() -> None:
    first = _message("First", "<one@example.org>")
    second = _message("Reply", "<two@example.org>", reply_to="<one@example.org>")
    data = (
        b"From ada@example.org Mon Jan  1 00:00:00 2024\n"
        + first.as_bytes()
        + b"\nFrom bob@example.org Tue Jan  2 00:00:00 2024\n"
        + second.as_bytes()
    )
    tree = MboxParser().parse(data, source_path="thread.mbox")

    assert [section.title for section in tree.root.children] == ["First", "Reply"]
    assert tree.metadata["threads"][1]["in_reply_to"] == "<one@example.org>"
    assert (
        tree.root.children[1].blocks[0].source_locations[0].element_id
        == "message:2:header:From"
    )


def test_msg_uses_same_email_contract(tmp_path: Path) -> None:
    msg = pytest.importorskip("aspose.email_foss.msg")
    message = msg.MapiMessage.from_email_message(
        _message("Outlook", "<msg@example.org>")
    )
    path = tmp_path / "sample.msg"
    message.save(path)

    tree = MsgParser().parse(path.read_bytes(), source_path="sample.msg")

    assert tree.root.children[0].title == "Outlook"
    assert any(
        block.attrs.get("filename") == "note.txt"
        for block in tree.root.children[0].blocks
    )
    assert tree.root.children[0].blocks[0].source_locations[0].source == "sample.msg"


def test_invalid_email_inputs_fail_clearly() -> None:
    with pytest.raises(ValueError, match="Invalid EML"):
        EmlParser().parse(b"body without headers")
    with pytest.raises(ValueError, match="Invalid MBOX"):
        MboxParser().parse(b"body without separator")
    with pytest.raises(ValueError, match="Invalid or unreadable MSG"):
        MsgParser().parse(b"not a msg")

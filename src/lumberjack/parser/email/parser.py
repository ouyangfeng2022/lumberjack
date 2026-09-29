"""EML, MBOX, and MSG input through the standard email message model."""

from __future__ import annotations

from dataclasses import replace
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from ...models import DocTree, Document, InputFormat, SectionNode, SourceLocation
from ..builder import DocTreeBuilder
from ..html import HTMLParser

_HEADERS = ("From", "To", "Cc", "Date", "Message-ID", "In-Reply-To", "References")


def _document(
    source: Document | bytes,
    format: InputFormat,
    title: str | None,
    metadata: dict[str, object] | None,
    path: str | Path | None,
) -> Document:
    if isinstance(source, Document):
        return source
    return Document(
        source,
        format=format,
        document_title=title,
        metadata_overrides=dict(metadata or {}),
        source_path=path,
    )


def _body(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if not isinstance(content, str):
        return ""
    if part.get_content_type() == "text/html":
        tree = HTMLParser().parse(content)

        def text(section: SectionNode) -> list[str]:
            return (
                ([section.title] if section.level else [])
                + [block.text for block in section.blocks]
                + [piece for child in section.children for piece in text(child)]
            )

        return "\n\n".join(text(tree.root)).strip()
    return content.strip()


def _build(messages: list[EmailMessage], document: Document) -> DocTree:
    if not messages:
        raise ValueError("Mailbox contains no messages")
    first_title = str(messages[0].get("Subject") or "Message 1")
    builder = DocTreeBuilder(
        title=document.document_title or first_title,
        source_path=document.source_path,
        metadata=document.metadata_overrides,
        block_kinds={"paragraph", "field_value"},
    )
    source_parts: list[str] = []
    threads: list[dict[str, object]] = []
    for index, message in enumerate(messages, 1):
        subject = str(message.get("Subject") or f"Message {index}")
        thread: dict[str, object] = {
            "index": index,
            "message_id": str(message.get("Message-ID") or ""),
            "in_reply_to": str(message.get("In-Reply-To") or ""),
            "references": str(message.get("References") or ""),
        }
        threads.append(thread)
        prefix = f"message:{index}"
        source = str(document.source_path) if document.source_path is not None else None
        builder.add_section(
            1,
            subject,
            location=SourceLocation(source=source, element_id=prefix),
        )
        for header in _HEADERS:
            if value := message.get(header):
                builder.add_block(
                    "field_value",
                    f"{header}: {value}",
                    locations=(
                        SourceLocation(
                            source=source, element_id=f"{prefix}:header:{header}"
                        ),
                    ),
                    attrs={"role": "header", "name": header},
                )
        if body := _body(message):
            builder.add_block(
                "paragraph",
                body,
                locations=(SourceLocation(source=source, element_id=f"{prefix}:body"),),
                attrs={"role": "body", "message_index": index},
            )
            source_parts.append(body)
        for part_index, part in enumerate(message.walk(), 1):
            if part.is_multipart() or not (
                part.get_filename() or part.get_content_disposition() == "attachment"
            ):
                continue
            name = part.get_filename() or f"attachment-{part_index}"
            content_type = part.get_content_type()
            size = len(part.get_payload(decode=True) or b"")
            builder.add_block(
                "field_value",
                f"Attachment: {name} ({content_type}, {size} bytes)",
                locations=(
                    SourceLocation(
                        source=source, element_id=f"{prefix}:attachment:{part_index}"
                    ),
                ),
                attrs={
                    "role": "attachment",
                    "filename": name,
                    "content_type": content_type,
                    "size": size,
                },
            )
    tree = builder.build()
    return replace(
        tree,
        source="\n\n".join(source_parts),
        metadata={**tree.metadata, "threads": threads},
    )


class EmlParser:
    """Read one RFC 5322 message, including MIME attachment metadata."""

    block_kinds = frozenset({"paragraph", "field_value"})

    def parse(
        self,
        document: Document | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        document = _document(
            document, "eml", document_title, metadata_overrides, source_path
        )
        if not isinstance(document.source, bytes | bytearray):
            raise TypeError("EmlParser.parse expects Document[bytes]")
        message = BytesParser(policy=policy.default).parsebytes(bytes(document.source))
        if not any(
            message.get(header) for header in ("From", "To", "Subject", "Message-ID")
        ):
            raise ValueError("Invalid EML: no message headers")
        return _build([message], document)


class MboxParser:
    """Read mboxrd messages in archive order without writing uploaded data."""

    block_kinds = EmlParser.block_kinds

    def parse(
        self,
        document: Document | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        document = _document(
            document, "mbox", document_title, metadata_overrides, source_path
        )
        if not isinstance(document.source, bytes | bytearray):
            raise TypeError("MboxParser.parse expects Document[bytes]")
        parts: list[bytes] = []
        current: list[bytes] = []
        for line in bytes(document.source).splitlines(keepends=True):
            if line.startswith(b"From "):
                if current:
                    parts.append(b"".join(current))
                    current = []
            elif line.lstrip(b">").startswith(b"From ") and line.startswith(b">"):
                current.append(line[1:])
            else:
                current.append(line)
        if current:
            parts.append(b"".join(current))
        if not bytes(document.source).startswith(b"From "):
            raise ValueError("Invalid MBOX: missing From separator")
        messages = [
            BytesParser(policy=policy.default).parsebytes(part) for part in parts
        ]
        return _build(messages, document)


class MsgParser:
    """Convert Outlook MSG locally, then use the shared email parser."""

    block_kinds = EmlParser.block_kinds

    def parse(
        self,
        document: Document | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        document = _document(
            document, "msg", document_title, metadata_overrides, source_path
        )
        if not isinstance(document.source, bytes | bytearray):
            raise TypeError("MsgParser.parse expects Document[bytes]")
        try:
            from aspose.email_foss import cfb, msg
        except ImportError as exc:
            raise RuntimeError(
                "MSG parsing requires the 'msg' extra: pip install 'lumberjack-py[msg]'"
            ) from exc
        try:
            with msg.MsgReader(cfb.CFBReader(bytes(document.source))) as reader:
                message = msg.MapiMessage.from_msg_document(
                    msg.MsgDocument.from_reader(reader)
                )
                email = message.to_email_message()
        except Exception as exc:
            raise ValueError(f"Invalid or unreadable MSG: {exc}") from exc
        return _build([email], document)

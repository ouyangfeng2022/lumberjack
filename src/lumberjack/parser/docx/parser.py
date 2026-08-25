from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import unquote
from xml.etree import ElementTree

from lumberjack.block import BlockKind

from ..._internal.xml_safe import parse_untrusted_xml
from ...models import (
    DocTree,
    DocumentBlock,
    DocumentInline,
    SectionNode,
    SourceLocation,
)
from ...models import (
    Document as SourceDocument,
)
from ...protocols import ParserProtocol

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument


_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_MAX_PACKAGE_ENTRIES = 100_000
_MAX_EXPANDED_PACKAGE_BYTES = 512 * 1024 * 1024
_OPTIONAL_RELATIONSHIP_TYPE_SUFFIXES = ("/image", "/metadata/thumbnail")
_STRICT_NAMESPACE_REPLACEMENTS = {
    b"http://purl.oclc.org/ooxml/officeDocument/relationships": (
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ),
    b"http://purl.oclc.org/ooxml/wordprocessingml/main": (
        b"http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ),
    b"http://purl.oclc.org/ooxml/officeDocument/math": (
        b"http://schemas.openxmlformats.org/officeDocument/2006/math"
    ),
    b"http://purl.oclc.org/ooxml/drawingml/main": (
        b"http://schemas.openxmlformats.org/drawingml/2006/main"
    ),
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": (
        b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    ),
    b"http://purl.oclc.org/ooxml/drawingml/picture": (
        b"http://schemas.openxmlformats.org/drawingml/2006/picture"
    ),
    b"http://purl.oclc.org/ooxml/drawingml/chart": (
        b"http://schemas.openxmlformats.org/drawingml/2006/chart"
    ),
    b"http://purl.oclc.org/ooxml/drawingml/diagram": (
        b"http://schemas.openxmlformats.org/drawingml/2006/diagram"
    ),
}
_CONTENT_TYPES_BY_EXTENSION = {
    "bmp": "image/bmp",
    "emf": "image/x-emf",
    "gif": "image/gif",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "svg": "image/svg+xml",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "wmf": "image/x-wmf",
}
_TEMPLATE_MAIN_CONTENT_TYPE = (
    b"application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
)
_DOCUMENT_MAIN_CONTENT_TYPE = (
    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)


@dataclass(frozen=True, slots=True)
class _ListInfo:
    """Numbering identity resolved from explicit OOXML numbering properties."""

    ordered: bool | None
    num_id: int
    level: int
    num_format: str


def _validate_package_infos(package: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Validate bounded, unambiguous OPC metadata without expanding every part."""
    infos = package.infolist()
    if len(infos) > _MAX_PACKAGE_ENTRIES:
        raise ValueError(
            f"DOCX package has {len(infos)} entries; limit is {_MAX_PACKAGE_ENTRIES}"
        )
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise ValueError("DOCX package contains duplicate part names")
    expanded_size = sum(info.file_size for info in infos)
    if expanded_size > _MAX_EXPANDED_PACKAGE_BYTES:
        raise ValueError(
            f"DOCX expanded size is {expanded_size} bytes; "
            f"limit is {_MAX_EXPANDED_PACKAGE_BYTES}"
        )
    for name in names:
        normalized = posixpath.normpath(name)
        decoded = unquote(name)
        decoded_normalized = posixpath.normpath(decoded)
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or normalized != name.rstrip("/")
            or normalized == ".."
            or normalized.startswith("../")
            or decoded.startswith("/")
            or decoded_normalized == ".."
            or decoded_normalized.startswith("../")
        ):
            raise ValueError(f"unsafe DOCX package part name: {name!r}")
    return infos


def _relationship_source_directory(name: str) -> str:
    """Resolve the owning part directory for an OPC relationships part."""
    parent = posixpath.dirname(name)
    if parent == "_rels":
        return ""
    return posixpath.dirname(parent)


def _normalize_strict_namespaces(
    payload: bytes, *, relationships_part: bool
) -> tuple[bytes, bool]:
    """Normalize namespace and relationship-Type attributes, not text content."""
    updated = payload
    for strict, transitional in _STRICT_NAMESPACE_REPLACEMENTS.items():
        namespace_declaration = re.compile(
            rb"(\bxmlns(?::[A-Za-z_][\w.-]*)?\s*=\s*[\"'])"
            + re.escape(strict)
            + rb"([\"'])"
        )
        updated = namespace_declaration.sub(
            lambda match, replacement=transitional: (
                match.group(1) + replacement + match.group(2)
            ),
            updated,
        )
        if relationships_part:
            relationship_type = re.compile(
                rb"(\bType\s*=\s*[\"'])" + re.escape(strict) + rb"(?=/)"
            )
            updated = relationship_type.sub(
                lambda match, replacement=transitional: match.group(1) + replacement,
                updated,
            )
    return updated, updated != payload


def _repair_docx_package(data: bytes | bytearray) -> tuple[bytes, tuple[str, ...]]:
    """Repair narrowly defined OPC/Strict OOXML interoperability defects in memory."""
    with zipfile.ZipFile(BytesIO(data)) as source:
        infos = _validate_package_infos(source)
        entry_names = {info.filename for info in infos}
        if "[Content_Types].xml" not in entry_names:
            raise KeyError("DOCX package has no [Content_Types].xml part")

        editable = {
            name: source.read(name)
            for name in entry_names
            if name.endswith((".xml", ".rels"))
        }
        repairs: list[str] = []
        strict_replacements = 0
        for name, payload in editable.items():
            updated, changed = _normalize_strict_namespaces(
                payload, relationships_part=name.endswith(".rels")
            )
            if changed:
                editable[name] = updated
                strict_replacements += 1
        if strict_replacements:
            repairs.append(
                f"normalized Strict OOXML namespaces in {strict_replacements} parts"
            )

        removed_relationships = 0
        for name, payload in tuple(editable.items()):
            if not name.endswith(".rels"):
                continue
            root = parse_untrusted_xml(payload)
            changed = False
            source_directory = _relationship_source_directory(name)
            for relationship in list(root):
                if relationship.get("TargetMode", "").casefold() == "external":
                    continue
                relationship_type = str(relationship.get("Type", ""))
                if not relationship_type.endswith(_OPTIONAL_RELATIONSHIP_TYPE_SUFFIXES):
                    continue
                target = unquote(relationship.get("Target", ""))
                resolved = posixpath.normpath(
                    posixpath.join(source_directory, target.lstrip("/"))
                )
                if resolved not in entry_names:
                    root.remove(relationship)
                    removed_relationships += 1
                    changed = True
            if changed:
                editable[name] = ElementTree.tostring(
                    root, encoding="utf-8", xml_declaration=True
                )
        if removed_relationships:
            repairs.append(
                f"removed {removed_relationships} relationships to missing parts"
            )

        content_types = parse_untrusted_xml(editable["[Content_Types].xml"])
        default_tag = f"{{{_CONTENT_TYPES_NS}}}Default"
        declared_extensions = {
            str(element.get("Extension", "")).casefold()
            for element in content_types.findall(default_tag)
        }
        override_tag = f"{{{_CONTENT_TYPES_NS}}}Override"
        overridden_parts = {
            str(element.get("PartName", "")).lstrip("/")
            for element in content_types.findall(override_tag)
        }
        added_extensions: list[str] = []
        uncovered_extensions = {
            name.rsplit(".", 1)[-1].casefold()
            for name in entry_names
            if "." in posixpath.basename(name) and name not in overridden_parts
        }
        for extension in sorted(
            uncovered_extensions & _CONTENT_TYPES_BY_EXTENSION.keys()
        ):
            if extension in declared_extensions:
                continue
            ElementTree.SubElement(
                content_types,
                default_tag,
                Extension=extension,
                ContentType=_CONTENT_TYPES_BY_EXTENSION[extension],
            )
            added_extensions.append(extension)
        if added_extensions:
            repairs.append(
                "added missing content types for " + ", ".join(added_extensions)
            )
        for override in content_types.findall(override_tag):
            if (
                override.get("PartName") == "/word/document.xml"
                and str(override.get("ContentType", "")).encode()
                == _TEMPLATE_MAIN_CONTENT_TYPE
            ):
                override.set("ContentType", _DOCUMENT_MAIN_CONTENT_TYPE.decode())
                repairs.append(
                    "normalized template main content type for document parsing"
                )
        editable["[Content_Types].xml"] = ElementTree.tostring(
            content_types, encoding="utf-8", xml_declaration=True
        )

        if not repairs:
            return bytes(data), ()
        output = BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            for info in infos:
                payload = (
                    editable[info.filename]
                    if info.filename in editable
                    else source.read(info)
                )
                target.writestr(info, payload)
        return output.getvalue(), tuple(repairs)


def _local_name(element: Any) -> str:
    """Return an OOXML local name, ignoring comments and processing nodes."""
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _visible_descendants(element: Any):
    """Yield descendants from the visible revision and compatibility branches."""
    for child in element:
        tag = _local_name(child)
        if tag in {"del", "moveFrom"}:
            continue
        if tag == "AlternateContent":
            fallback = next(
                (item for item in child if _local_name(item) == "Fallback"),
                None,
            )
            if fallback is not None:
                yield from _visible_descendants(fallback)
            continue
        yield child
        yield from _visible_descendants(child)


def _paragraph_property_chain(para: Any):
    """Yield direct and inherited paragraph properties in precedence order."""
    yield getattr(para._p, "pPr", None)
    style = para.style
    visited: set[str] = set()
    while style is not None:
        style_id = str(style.style_id)
        if style_id in visited:
            raise ValueError(f"cyclic DOCX paragraph style inheritance at {style_id!r}")
        visited.add(style_id)
        yield getattr(style.element, "pPr", None)
        style = style.base_style


def _heading_level(para: Any) -> int | None:
    """Resolve a heading only from the OOXML outline level, never its style name."""
    for properties in _paragraph_property_chain(para):
        outline = getattr(properties, "outlineLvl", None)
        if outline is None:
            continue
        try:
            value = int(outline.val)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid DOCX outlineLvl value") from error
        return value + 1 if 0 <= value <= 8 else None
    return None


def _attribute(element: Any, local_name: str) -> str | None:
    """Return one namespace-agnostic XML attribute by exact local name."""
    matches = [
        value
        for name, value in element.attrib.items()
        if name.rsplit("}", 1)[-1] == local_name
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple XML attributes named {local_name!r}")
    return str(matches[0]) if matches else None


def _resolve_number_format(
    para: Any,
    numbering: Any,
    num_id: int,
    level: int,
    visited: frozenset[int] = frozenset(),
) -> str:
    """Resolve numFmt, including the OOXML numStyleLink indirection."""
    if num_id in visited:
        raise ValueError(f"cyclic DOCX numbering style link at numId {num_id}")
    try:
        instances = [num for num in numbering.num_lst if int(num.numId) == num_id]
    except (TypeError, ValueError) as error:
        raise ValueError("invalid DOCX numbering instance identifier") from error
    if len(instances) != 1:
        raise ValueError(
            f"DOCX numId {num_id} resolves to {len(instances)} numbering instances"
        )
    instance = instances[0]
    try:
        abstract_id = int(instance.abstractNumId.val)
    except (TypeError, ValueError) as error:
        raise ValueError(f"DOCX numId {num_id} has an invalid abstractNumId") from error

    override_formats = numbering.xpath(
        f"./w:num[@w:numId='{num_id}']/w:lvlOverride[@w:ilvl='{level}']"
        "/w:lvl/w:numFmt/@w:val"
    )
    abstract_formats = numbering.xpath(
        "./w:abstractNum"
        f"[@w:abstractNumId='{abstract_id}']"
        f"/w:lvl[@w:ilvl='{level}']/w:numFmt/@w:val"
    )
    formats = override_formats or abstract_formats
    if len(formats) == 1:
        return str(formats[0]).casefold()
    if len(formats) > 1:
        raise ValueError(
            f"DOCX numId {num_id} level {level} resolves to "
            f"{len(formats)} number formats"
        )

    abstracts = [
        element
        for element in numbering
        if _local_name(element) == "abstractNum"
        and _attribute(element, "abstractNumId") == str(abstract_id)
    ]
    if len(abstracts) != 1:
        raise ValueError(
            f"DOCX abstractNumId {abstract_id} resolves to {len(abstracts)} definitions"
        )
    style_links = [
        _attribute(child, "val")
        for child in abstracts[0]
        if _local_name(child) == "numStyleLink"
    ]
    if len(style_links) != 1 or style_links[0] is None:
        raise ValueError(
            f"DOCX numId {num_id} level {level} has no number format or "
            "numbering-style link"
        )
    style_id = style_links[0]
    styles = para.part._styles_part.element
    linked_styles = [
        style
        for style in styles
        if _local_name(style) == "style"
        and _attribute(style, "styleId") == style_id
        and _attribute(style, "type") == "numbering"
    ]
    if len(linked_styles) != 1:
        raise ValueError(
            f"DOCX numbering style {style_id!r} resolves to "
            f"{len(linked_styles)} definitions"
        )
    linked_num_ids = [
        _attribute(element, "val")
        for element in linked_styles[0].iter()
        if _local_name(element) == "numId"
    ]
    if len(linked_num_ids) != 1 or linked_num_ids[0] is None:
        raise ValueError(
            f"DOCX numbering style {style_id!r} does not declare exactly one numId"
        )
    try:
        linked_num_id = int(linked_num_ids[0])
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"DOCX numbering style {style_id!r} has an invalid numId"
        ) from error
    return _resolve_number_format(
        para,
        numbering,
        linked_num_id,
        level,
        visited | {num_id},
    )


def _list_info(para: Any) -> _ListInfo | None:
    """Resolve list identity and format from effective OOXML numbering data."""
    num_id: int | None = None
    level: int | None = None
    for properties in _paragraph_property_chain(para):
        numbering_properties = getattr(properties, "numPr", None)
        if numbering_properties is None:
            continue
        if num_id is None and numbering_properties.numId is not None:
            try:
                num_id = int(numbering_properties.numId.val)
            except (TypeError, ValueError) as error:
                raise ValueError("invalid DOCX numId value") from error
        if level is None and numbering_properties.ilvl is not None:
            try:
                level = int(numbering_properties.ilvl.val)
            except (TypeError, ValueError) as error:
                raise ValueError("invalid DOCX ilvl value") from error
        if num_id is not None and level is not None:
            break
    if num_id is None or num_id == 0:
        return None
    if level is None:
        level = 0

    try:
        numbering = para.part.numbering_part.element
    except (AttributeError, KeyError) as error:
        raise ValueError(f"DOCX numId {num_id} has no numbering part") from error
    num_format = _resolve_number_format(para, numbering, num_id, level)
    return _ListInfo(
        ordered=None if num_format == "none" else num_format != "bullet",
        num_id=num_id,
        level=level,
        num_format=num_format,
    )


def _run_to_inlines(run: Any) -> tuple[DocumentInline, ...]:
    """Convert one DOCX run, including drawings, to inline nodes."""
    inlines: list[DocumentInline] = []
    text = run.text
    if text:
        font = run.font
        if font.bold and font.italic:
            inlines.append(
                DocumentInline(
                    kind="strong",
                    children=(DocumentInline(kind="emphasis", text=text),),
                )
            )
        elif font.bold:
            inlines.append(
                DocumentInline(
                    kind="strong", children=(DocumentInline(kind="text", text=text),)
                )
            )
        elif font.italic:
            inlines.append(DocumentInline(kind="emphasis", text=text))
        elif run.font.underline:
            inlines.append(
                DocumentInline(kind="text", text=text, attrs={"underline": True})
            )
        else:
            inlines.append(DocumentInline(kind="text", text=text))

    text_box_parts: list[str] = []

    def collect_text_box_text(element: Any, inside_text_box: bool = False) -> None:
        if _local_name(element) == "AlternateContent":
            fallback = next(
                (child for child in element if _local_name(child) == "Fallback"),
                None,
            )
            if fallback is not None:
                collect_text_box_text(fallback, inside_text_box)
            return
        inside_text_box = inside_text_box or _local_name(element) == "txbxContent"
        if inside_text_box and _local_name(element) == "t" and element.text:
            text_box_parts.append(str(element.text))
        for child in element:
            collect_text_box_text(child, inside_text_box)

    collect_text_box_text(run._element)
    text_box_text = "".join(text_box_parts)
    if text_box_text:
        inlines.append(
            DocumentInline(
                kind="text",
                text=text_box_text,
                attrs={"source": "text_box"},
            )
        )

    drawings = [
        element
        for element in _visible_descendants(run._element)
        if _local_name(element) == "blip"
    ]
    for drawing in drawings:
        relationship_id = next(
            (
                value
                for attribute, value in drawing.attrib.items()
                if attribute.rsplit("}", 1)[-1] == "embed"
            ),
            "",
        )
        if not relationship_id:
            continue
        related_part = run.part.related_parts.get(relationship_id)
        destination = (
            str(related_part.partname).lstrip("/") if related_part is not None else ""
        )
        drawing_container = drawing
        while drawing_container.getparent() is not None and _local_name(
            drawing_container
        ) not in {"anchor", "inline", "pict", "r"}:
            drawing_container = drawing_container.getparent()
        drawing_properties = [
            element
            for element in _visible_descendants(drawing_container)
            if _local_name(element) == "docPr"
        ]
        descriptions = [
            element.get("descr")
            for element in drawing_properties
            if element.get("descr")
        ]
        titles = [
            element.get("title")
            for element in drawing_properties
            if element.get("title")
        ]
        names = [
            element.get("name") for element in drawing_properties if element.get("name")
        ]
        alt_text = str(
            (descriptions or titles or names or ["embedded image"])[0]
        ).strip()
        inlines.append(
            DocumentInline(
                kind="image",
                children=(DocumentInline(kind="text", text=alt_text),),
                attrs={
                    "destination": destination,
                    "title": str(titles[0]) if titles else "",
                    "relationship_id": str(relationship_id),
                },
            )
        )
    return tuple(inlines)


def _omml_literal(element: Any) -> str:
    """Return the linear visible text of an Office Math element."""
    return "".join(
        str(descendant.text)
        for descendant in element.iter()
        if _local_name(descendant) == "t" and descendant.text
    )


def _runs_to_inlines(para: Any) -> tuple[DocumentInline, ...]:
    """Convert paragraph content through transparent OOXML inline wrappers."""
    from docx.text.hyperlink import Hyperlink
    from docx.text.run import Run

    inlines: list[DocumentInline] = []
    hidden_wrappers = {"del", "moveFrom"}

    def collect(element: Any) -> None:
        for child in element:
            tag = _local_name(child)
            if tag in hidden_wrappers:
                continue
            if tag == "AlternateContent":
                fallback = next(
                    (item for item in child if _local_name(item) == "Fallback"),
                    None,
                )
                if fallback is not None:
                    collect(fallback)
                continue
            if tag in {"oMath", "oMathPara"}:
                literal = _omml_literal(child)
                if literal:
                    inlines.append(
                        DocumentInline(
                            kind="math_inline",
                            text=literal,
                            attrs={"literal": literal, "syntax": "omml"},
                        )
                    )
                continue
            if tag == "r":
                inlines.extend(_run_to_inlines(Run(child, para)))
                continue
            if tag == "hyperlink":
                item = Hyperlink(child, para)
                children = tuple(
                    inline for run in item.runs for inline in _run_to_inlines(run)
                )
                destination = str(item.url or "")
                fragment = str(getattr(item, "fragment", "") or "")
                if not destination and fragment:
                    destination = f"#{fragment}"
                inlines.append(
                    DocumentInline(
                        kind="link",
                        children=children,
                        attrs={
                            "destination": destination,
                            "title": "",
                        },
                    )
                )
                continue
            collect(child)

    collect(para._p)
    return tuple(inlines)


def _render_inlines(inlines: tuple[DocumentInline, ...]) -> str:
    """Render DOCX inlines into the canonical Markdown-like representation."""
    parts: list[str] = []
    for inline in inlines:
        children = _render_inlines(inline.children)
        if inline.kind == "strong":
            parts.append(f"**{children or inline.text}**")
        elif inline.kind == "emphasis":
            parts.append(f"*{children or inline.text}*")
        elif inline.kind == "code_span":
            parts.append(f"`{inline.text}`")
        elif inline.kind == "math_inline":
            parts.append(f"${inline.attrs.get('literal', inline.text)}$")
        elif inline.kind == "link":
            destination = str(inline.attrs.get("destination") or "")
            parts.append(f"[{children}]({destination})" if destination else children)
        elif inline.kind == "image":
            destination = str(inline.attrs.get("destination") or "")
            parts.append(f"![{children}]({destination})")
        else:
            parts.append(inline.text or children)
    return "".join(parts)


def _escape_table_cell(text: str) -> str:
    """Escape content that would otherwise corrupt a Markdown pipe table."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>").strip()


def _render_table_cell(cell: Any) -> str:
    """Render paragraphs and nested tables in one DOCX table cell."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parts: list[str] = []
    for element in _iter_body_elements(cell._tc):
        tag = _local_name(element)
        if tag == "p":
            paragraph = Paragraph(element, cell)
            inlines = _runs_to_inlines(paragraph)
            rendered = _render_inlines(inlines).strip() or paragraph.text.strip()
            if rendered:
                parts.append(rendered)
        elif tag == "tbl":
            parts.append(_render_table(Table(element, cell)))
        elif tag == "oMathPara":
            literal = _omml_literal(element).strip()
            if literal:
                parts.append(f"$${literal}$$")
    return _escape_table_cell("<br>".join(part for part in parts if part))


def _render_table(table: Any) -> str:
    """Render a DOCX table as Markdown pipe table text."""
    from docx.table import _Cell, _Row

    def descendants(container: Any, target: str) -> list[Any]:
        found: list[Any] = []
        for child in container:
            tag = _local_name(child)
            if tag in {"del", "moveFrom"}:
                continue
            if tag == target:
                found.append(child)
            elif tag not in {"p", "tbl", "tc", "tr"}:
                found.extend(descendants(child, target))
        return found

    rows_data: list[list[str]] = []
    wrapped_rows = descendants(table._tbl, "tr")
    rows = [_Row(element, table) for element in wrapped_rows]
    for row in rows:
        wrapped_cells = descendants(row._tr, "tc")
        row_cells = [_Cell(element, table) for element in wrapped_cells]
        cells = [_render_table_cell(cell) for cell in row_cells]
        rows_data.append(cells)

    if not rows_data:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows_data)
    for row in rows_data:
        while len(row) < max_cols:
            row.append("")

    lines: list[str] = []
    for i, row in enumerate(rows_data):
        line = "| " + " | ".join(row) + " |"
        lines.append(line)
        if i == 0:
            sep = "| " + " | ".join("---" for _ in row) + " |"
            lines.append(sep)

    return "\n".join(lines)


def _iter_body_elements(container: Any):
    """Yield visible blocks through producer-specific OOXML wrappers."""
    hidden_wrappers = {"del", "moveFrom"}
    for element in container:
        tag = _local_name(element)
        if tag in hidden_wrappers:
            continue
        if tag in {"p", "tbl", "oMathPara"}:
            yield element
        elif tag == "AlternateContent":
            fallback = next(
                (child for child in element if _local_name(child) == "Fallback"),
                None,
            )
            if fallback is not None:
                yield from _iter_body_elements(fallback)
        else:
            yield from _iter_body_elements(element)


class DocxParser(ParserProtocol):
    """Parse DOCX documents into DocTree.

    Maps DOCX structural elements to the same DocTree model used by
    the Markdown parser, enabling reuse of all existing splitters.

    Block kind mapping:
        - OOXML outline levels → SectionNode hierarchy
        - Normal paragraphs → ``paragraph``
        - Tables            → ``table``
        - OOXML numbering   → ``list`` with ``list_item`` children
    """

    default_block_kinds: ClassVar[frozenset[str]] = frozenset(
        {
            "paragraph",
            "table",
            "list",
            "list_item",
            "math_block",
        }
    )

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser can produce."""
        return self.default_block_kinds

    def parse(
        self,
        document: SourceDocument | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        """Parse DOCX binary data into a DocTree.

        Args:
            document: A ``Document`` or raw DOCX file content.
            document_title: Optional override for the document title.
            metadata_overrides: Semantic metadata that overrides DOCX core properties.
            source_path: Optional source provenance stored separately from metadata.
        """
        from docx import Document as create_docx_document

        if not isinstance(document, SourceDocument):
            document = SourceDocument(
                document,
                format="docx",
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        data = document.source
        if not isinstance(data, bytes | bytearray):
            msg = f"DocxParser.parse expects Document[bytes], got {type(data).__name__}"
            raise TypeError(msg)

        metadata = dict(document.metadata_overrides)

        # Apply only package defects established directly from OPC metadata.
        repaired_data, repairs = _repair_docx_package(data)
        doc = create_docx_document(BytesIO(repaired_data if repairs else data))
        if repairs:
            metadata["docx_repairs"] = list(repairs)

        # Extract core properties as metadata
        core_props = doc.core_properties
        if core_props.title and "title" not in metadata:
            metadata.setdefault("title", core_props.title)
        if core_props.author:
            metadata.setdefault("author", core_props.author)

        root = SectionNode(level=0, title="")
        section_stack: list[SectionNode] = [root]
        pending_list_children: list[DocumentBlock] = []
        pending_list_text: list[str] = []
        pending_list_locations: list[SourceLocation] = []
        pending_list_info: _ListInfo | None = None
        pending_list_section: SectionNode | None = None

        def element_location(element: Any) -> SourceLocation:
            return SourceLocation(
                source=(
                    str(document.source_path)
                    if document.source_path is not None
                    else None
                ),
                element_id=str(element.getroottree().getpath(element)),
            )

        def flush_pending_list() -> None:
            nonlocal pending_list_info, pending_list_section
            if pending_list_info is None or pending_list_section is None:
                return
            if pending_list_children:
                pending_list_section.add_block(
                    DocumentBlock(
                        kind=BlockKind.LIST,
                        text="\n".join(pending_list_text),
                        source_locations=tuple(pending_list_locations),
                        children=tuple(pending_list_children),
                        attrs={
                            "ordered": pending_list_info.ordered,
                            "num_id": pending_list_info.num_id,
                            "level": pending_list_info.level,
                            "num_format": pending_list_info.num_format,
                        },
                    )
                )
            pending_list_children.clear()
            pending_list_text.clear()
            pending_list_locations.clear()
            pending_list_info = None
            pending_list_section = None

        # Iterate document body elements in order
        for element in _iter_body_elements(doc.element.body):
            tag = _local_name(element)

            if tag == "p":
                para = self._paragraph_from_element(doc, element)
                level = _heading_level(para)

                if level is not None:
                    flush_pending_list()
                    title_inlines = _runs_to_inlines(para)
                    title_text = (
                        _render_inlines(title_inlines).strip() or para.text.strip()
                    )
                    if not title_text:
                        continue

                    while section_stack and section_stack[-1].level >= level:
                        section_stack.pop()
                    parent = section_stack[-1]
                    section = SectionNode(
                        level=level,
                        title=title_text,
                        path=(*parent.path, (level, title_text)),
                        index=len(parent.children),
                        source_locations=(element_location(element),),
                        title_inlines=title_inlines,
                    )
                    parent.add_child(section)
                    section_stack.append(section)
                    continue

                list_info = _list_info(para)
                if list_info is not None:
                    if pending_list_info is not None and pending_list_info != list_info:
                        flush_pending_list()
                    if pending_list_info is None:
                        pending_list_info = list_info
                        pending_list_section = section_stack[-1]

                    item_inlines = _runs_to_inlines(para)
                    item_text = _render_inlines(item_inlines).strip()
                    if not item_text:
                        item_text = para.text.strip()
                    if not item_text:
                        continue
                    pending_list_children.append(
                        DocumentBlock(
                            kind=BlockKind.LIST_ITEM,
                            text=item_text,
                            source_locations=(element_location(element),),
                            inlines=item_inlines,
                        )
                    )
                    marker = "1." if list_info.ordered else "-"
                    pending_list_text.append(
                        item_text
                        if list_info.ordered is None
                        else f"{marker} {item_text}"
                    )
                    pending_list_locations.append(element_location(element))
                    continue

                flush_pending_list()
                inlines = _runs_to_inlines(para)
                text = _render_inlines(inlines).strip()
                if not text:
                    continue
                section_stack[-1].add_block(
                    DocumentBlock(
                        kind=BlockKind.PARAGRAPH,
                        text=text,
                        source_locations=(element_location(element),),
                        inlines=inlines,
                    )
                )

            elif tag == "tbl":
                flush_pending_list()
                table = self._table_from_element(doc, element)
                rendered = _render_table(table)
                if rendered:
                    section_stack[-1].add_block(
                        DocumentBlock(
                            kind=BlockKind.TABLE,
                            text=rendered,
                            source_locations=(element_location(element),),
                        )
                    )

            elif tag == "oMathPara":
                flush_pending_list()
                literal = _omml_literal(element).strip()
                if literal:
                    section_stack[-1].add_block(
                        DocumentBlock(
                            kind=BlockKind.MATH_BLOCK,
                            text=f"$${literal}$$",
                            source_locations=(element_location(element),),
                            attrs={"literal": literal, "syntax": "omml"},
                        )
                    )

        flush_pending_list()

        final_title = self._resolve_document_title(document.document_title, doc, root)
        root.title = final_title

        return DocTree(
            title=final_title,
            source="",
            root=root,
            source_path=(
                str(document.source_path) if document.source_path is not None else None
            ),
            metadata=metadata,
        )

    def _paragraph_from_element(self, doc: DocxDocument, element: Any) -> Any:
        """Get a paragraph object from its XML element."""
        from docx.text.paragraph import Paragraph

        return Paragraph(element, doc)

    def _table_from_element(self, doc: DocxDocument, element: Any) -> Any:
        """Get a table object from its XML element."""
        from docx.table import Table

        return Table(element, doc)

    def _resolve_document_title(
        self,
        document_title: str | None,
        doc: DocxDocument,
        root: SectionNode,
    ) -> str:
        """Resolve document title: user-provided > core properties > first H1 > Anonymous."""
        if document_title is not None:
            return document_title

        core_props = doc.core_properties
        if core_props.title and core_props.title.strip():
            return core_props.title.strip()

        h1_title = self._first_h1_title(root)
        if h1_title is not None:
            return h1_title

        return "Anonymous"

    @staticmethod
    def _first_h1_title(root: SectionNode) -> str | None:
        """Return the title of the first level-1 heading section, or None."""
        for child in root.children:
            if child.level == 1:
                return child.title
        return None

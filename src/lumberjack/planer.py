from __future__ import annotations

import re
from html.parser import HTMLParser


class Planer:
    """Normalize line endings and block spacing while retaining markup."""

    def plane(self, text: str) -> str:
        normalized: list[str] = []
        blank = False
        for line in text.split("\n"):
            if line:
                normalized.append(line)
                blank = False
            elif normalized and not blank:
                normalized.append("")
                blank = True
        return "\n".join(normalized).strip("\n")


class _HTMLTextPlaner(HTMLParser):
    _BLOCK_TAGS = frozenset(
        {
            "address",
            "article",
            "aside",
            "blockquote",
            "br",
            "div",
            "figcaption",
            "figure",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "ol",
            "p",
            "pre",
            "section",
            "table",
            "td",
            "th",
            "tr",
            "ul",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class PlainTextPlaner(Planer):
    """Remove common Markdown and HTML surface syntax while retaining readable text."""

    _IMAGE_RE = re.compile(r"!\[([^]]*)\]\([^)]*\)")
    _LINK_RE = re.compile(r"\[([^]]+)\]\([^)]*\)")
    _FENCE_RE = re.compile(r"(?ms)^```[^\n]*\n(.*?)\n```$")
    _HTML_RE = re.compile(r"<[/!A-Za-z][^>]*>")
    _HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
    _QUOTE_RE = re.compile(r"(?m)^\s*>\s?")
    _LIST_RE = re.compile(r"(?m)^\s*(?:[-+*]|\d+[.)])\s+")
    _STRONG_RE = re.compile(r"(?<!\\)(\*\*|__|~~)(?=\S)(.+?)(?<=\S)\1")
    _EMPHASIS_RE = re.compile(r"(?<![\\\w])([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)")

    def plane(self, text: str) -> str:
        text = self._FENCE_RE.sub(lambda match: match.group(1), text)
        text = self._IMAGE_RE.sub(lambda match: match.group(1), text)
        text = self._LINK_RE.sub(lambda match: match.group(1), text)
        if self._HTML_RE.search(text):
            html_planer = _HTMLTextPlaner()
            html_planer.feed(text)
            html_planer.close()
            text = "".join(html_planer.parts)
        text = self._HEADING_RE.sub("", text)
        text = self._QUOTE_RE.sub("", text)
        text = self._LIST_RE.sub("", text)
        text = self._STRONG_RE.sub(lambda match: match.group(2), text)
        text = self._EMPHASIS_RE.sub(lambda match: match.group(2), text)
        text = text.replace("`", "")
        return super().plane(text)


__all__ = ["PlainTextPlaner", "Planer"]

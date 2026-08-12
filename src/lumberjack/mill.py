from __future__ import annotations

from collections.abc import Iterable

from ._internal.rendering import RENDER_SEPARATOR, join_rendered_blocks
from .models import (
    Bundle,
    Chunk,
    Entry,
    HeadingPath,
    Log,
    common_heading_path,
    render_heading_path,
)
from .planer import Planer
from .protocols import PlanerProtocol, ScalerProtocol, SeasonerProtocol
from .seasoner import Seasoner


def render_bundle_body(entries: list[Entry], external_headings: HeadingPath) -> str:
    """Render a bundle body while keeping its external headings as metadata."""
    parts: list[str] = []
    previous_headings = external_headings
    for entry in entries:
        shared = common_heading_path((previous_headings, entry.headings))
        if len(shared) < len(external_headings):
            shared = external_headings
        relative_headings = entry.headings[len(shared) :]
        entry_parts: list[str] = []
        if relative_headings:
            entry_parts.append(render_heading_path(relative_headings))
        if entry.body:
            entry_parts.append(entry.body)
        rendered = join_rendered_blocks(entry_parts)
        if rendered:
            parts.append(rendered)
        previous_headings = entry.headings
    return join_rendered_blocks(parts)


class Mill:
    """Season, plane, measure, and finish bundles into chunks."""

    def __init__(
        self,
        scaler: ScalerProtocol,
        *,
        seasoner: SeasonerProtocol | None = None,
        planer: PlanerProtocol | None = None,
        skip_empty_sections: bool = True,
    ) -> None:
        self.scaler = scaler
        self.seasoner = seasoner or Seasoner()
        self.planer = planer or Planer()
        self.skip_empty_sections = skip_empty_sections

    def mill(self, log: Log, bundles: Iterable[Bundle]) -> list[Chunk]:
        finished: list[Chunk] = []
        for bundle in bundles:
            body = render_bundle_body(bundle.entries, bundle.headings)
            body = self.planer.plane(self.seasoner.season(body))
            if self.skip_empty_sections and not body.strip():
                continue

            heading_text = render_heading_path(bundle.headings)
            headings_token_count = self.scaler.scale(heading_text, cache=True)
            body_token_count = self.scaler.scale(body, cache=True)
            token_count = (
                headings_token_count
                + self.scaler.scale(RENDER_SEPARATOR, cache=True)
                + body_token_count
            )
            ancestor_headings = (
                bundle.headings[:-1]
                if bundle.own_heading is not None
                else bundle.headings
            )
            finished.append(
                Chunk(
                    chunk_id=f"chunk-{len(finished) + 1:04d}",
                    chunk_type=bundle.chunk_type,
                    body=body,
                    token_count=token_count,
                    estimated_token_count=(
                        token_count
                        if bundle.counting_mode == "exact"
                        else bundle.token_count
                    ),
                    headings_token_count=headings_token_count,
                    body_token_count=body_token_count,
                    ancestor_headings=ancestor_headings,
                    own_heading=bundle.own_heading,
                    section_level=max(
                        (
                            level
                            for entry in bundle.entries
                            for level, _ in entry.headings
                        ),
                        default=0,
                    ),
                    document_title=log.title,
                    document_path=log.source_path,
                    start_line=min(
                        (
                            entry.start_line
                            for entry in bundle.entries
                            if entry.start_line is not None
                        ),
                        default=None,
                    ),
                    end_line=max(
                        (
                            entry.end_line
                            for entry in bundle.entries
                            if entry.end_line is not None
                        ),
                        default=None,
                    ),
                )
            )
        return finished


__all__ = ["Mill", "render_bundle_body"]

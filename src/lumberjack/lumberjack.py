from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .feller import AutoFeller
from .mill import Mill
from .models import Chunk, InputFormat, Tree
from .planer import Planer
from .protocols import (
    FellerProtocol,
    PlanerProtocol,
    SawyerProtocol,
    ScalerProtocol,
    SeasonerProtocol,
)
from .sawyer import SiblingSawyer
from .scaler import ApproxByteScaler
from .seasoner import Seasoner


class Lumberjack:
    """Orchestrate the complete tree-to-chunks lumber pipeline."""

    def __init__(
        self,
        *,
        scaler: ScalerProtocol | None = None,
        feller: FellerProtocol | None = None,
        sawyer: SawyerProtocol | None = None,
        seasoner: SeasonerProtocol | None = None,
        planer: PlanerProtocol | None = None,
        max_tokens: int = 1200,
        skip_empty_sections: bool = True,
    ) -> None:
        if scaler is None and sawyer is not None:
            scaler = sawyer.scaler
        self.scaler = scaler or ApproxByteScaler()
        self.feller = feller or AutoFeller()
        if sawyer is not None and sawyer.scaler is not self.scaler:
            raise ValueError("sawyer and mill must share the same scaler instance")
        self.sawyer = sawyer or SiblingSawyer(
            self.scaler,
            max_tokens=max_tokens,
            skip_empty_sections=skip_empty_sections,
        )
        self.mill = Mill(
            self.scaler,
            seasoner=seasoner or Seasoner(),
            planer=planer or Planer(),
            skip_empty_sections=skip_empty_sections,
        )

    def saw(
        self,
        tree: Tree | str | bytes | Path,
        *,
        format: InputFormat = "auto",
        document_title: str | None = None,
        metadata_overrides: Mapping[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> list[Chunk]:
        """Fell, saw, and mill one raw document into final chunks."""
        if not isinstance(tree, Tree):
            tree = Tree(
                source=tree,
                format=format,
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        log = self.feller.fell(tree)
        bundles = self.sawyer.saw(log)
        return self.mill.mill(log, bundles)


__all__ = ["Lumberjack"]

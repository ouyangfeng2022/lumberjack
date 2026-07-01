from __future__ import annotations

import json
import sys
from pathlib import Path

from lumberjack.cli import main


def test_cli_validates_block_configs_against_detected_html_format(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        "<h1>Guide</h1><table><tr><th>A</th></tr><tr><td>1</td></tr></table>",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lumber",
            str(html_path),
            "--max-tokens",
            "500",
            "--block-config",
            "html_table:isolated",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["document"] == "Guide"
    assert payload["chunk_count"] >= 1

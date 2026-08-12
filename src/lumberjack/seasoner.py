from __future__ import annotations


class Seasoner:
    """Conservatively stabilize text without removing document markup."""

    def season(self, text: str) -> str:
        return (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\ufeff", "")
            .replace("\x00", "")
        )


__all__ = ["Seasoner"]

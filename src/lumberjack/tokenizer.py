from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

from .protocols import TokenizerProtocol

DEFAULT_TRANSFORMERS_MODEL = "bert-base-uncased"


class _TransformersTokenizerProtocol(Protocol):
    def encode(self, text: str) -> Iterable[int]: ...


class TiktokenTokenizer(TokenizerProtocol):
    """Tokenizer backed by the tiktoken library."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_cache_size: int = 1000,
        default_cache: bool = False,
    ):
        try:
            import tiktoken
            from cachetools import LRUCache
        except ImportError as e:
            raise ImportError(
                "TiktokenTokenizer requires the optional 'tiktoken' and "
                "'cachetools' dependencies. Install them with "
                "'lumberjack[tokenizers]'."
            ) from e

        self.model = model
        self.encoding = tiktoken.encoding_for_model(model)
        self.default_cache = default_cache
        self._cache: LRUCache[str, tuple[int, ...]] = LRUCache(maxsize=max_cache_size)

    def encode(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> tuple[int, ...]:
        if not text:
            return ()

        use_cache = self.default_cache if cache is None else cache
        if use_cache:
            cached = self._cache.get(text)
            if cached is not None:
                return cached
        token_ids = tuple(self.encoding.encode(text))

        if use_cache:
            self._cache[text] = token_ids

        return token_ids

    def count(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> int:
        if not text:
            return 0
        return len(self.encode(text, cache=cache))

    def clear_cache(self) -> None:
        self._cache.clear()


class ApproxByteTokenizer(TokenizerProtocol):
    """Approximate tokenizer that estimates tokens as ``len(text.encode(\"utf-8\")) // 3``.

    Assumes an average of 3 UTF-8 bytes per token, which is a better fit for
    mixed ASCII / CJK text than the older ``chars // 4`` heuristic.
    """

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(text.encode("utf-8"))

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(self.encode(text)) // 3


class TransformersTokenizer(TokenizerProtocol):
    """Tokenizer backed by a Hugging Face fast tokenizer."""

    def __init__(
        self,
        model: str = DEFAULT_TRANSFORMERS_MODEL,
        max_cache_size: int = 1000,
        default_cache: bool = False,
    ) -> None:
        try:
            from cachetools import LRUCache
            from transformers import AutoTokenizer
        except ImportError as e:
            raise ImportError(
                "TransformersTokenizer requires the optional 'transformers' "
                "dependency. Install it with 'lumberjack[tokenizers]'."
            ) from e

        self.model = model
        self.tokenizer = cast(
            _TransformersTokenizerProtocol,
            AutoTokenizer.from_pretrained(model, use_fast=True),
        )
        self.default_cache = default_cache
        self._cache: LRUCache[str, tuple[int, ...]] = LRUCache(maxsize=max_cache_size)

    def encode(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> tuple[int, ...]:
        if not text:
            return ()

        use_cache = self.default_cache if cache is None else cache
        if use_cache:
            cached = self._cache.get(text)
            if cached is not None:
                return cached

        token_ids = tuple(self.tokenizer.encode(text))

        if use_cache:
            self._cache[text] = token_ids

        return token_ids

    def count(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> int:
        if not text:
            return 0
        return len(self.encode(text, cache=cache))

    def clear_cache(self) -> None:
        self._cache.clear()

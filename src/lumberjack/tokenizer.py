from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

from .protocols import TokenizerProtocol

DEFAULT_TRANSFORMERS_MODEL = "bert-base-uncased"


class _TransformersTokenizerProtocol(Protocol):
    def encode(self, text: str) -> Iterable[int]: ...


class _TiktokenEncodingProtocol(Protocol):
    def encode(self, text: str) -> Iterable[int]: ...


class TiktokenTokenizer(TokenizerProtocol):
    """Tokenizer backed by the tiktoken library."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_cache_size: int = 1000,
        default_cache: bool = False,
        *,
        _encoding: _TiktokenEncodingProtocol | None = None,
    ):
        try:
            from cachetools import LRUCache
        except ImportError as e:
            raise ImportError(
                "TiktokenTokenizer requires the optional 'tiktoken' and "
                "'cachetools' dependencies. Install them with "
                "'lumberjack[tokenizers]'."
            ) from e

        if _encoding is None:
            try:
                import tiktoken
            except ImportError as e:
                raise ImportError(
                    "TiktokenTokenizer requires the optional 'tiktoken' and "
                    "'cachetools' dependencies. Install them with "
                    "'lumberjack[tokenizers]'."
                ) from e
            _encoding = tiktoken.encoding_for_model(model)

        self.model = model
        self.encoding = _encoding
        self.max_cache_size = max_cache_size
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

    def with_fresh_cache(self) -> TiktokenTokenizer:
        """Share the encoding backend while allocating a new request-local cache."""
        return TiktokenTokenizer(
            model=self.model,
            max_cache_size=self.max_cache_size,
            default_cache=self.default_cache,
            _encoding=self.encoding,
        )


class ApproxByteTokenizer(TokenizerProtocol):
    """Approximate tokenizer using ``len(text.encode(\"utf-8\")) // 3`` tokens.

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
        *,
        _tokenizer: _TransformersTokenizerProtocol | None = None,
    ) -> None:
        try:
            from cachetools import LRUCache
        except ImportError as e:
            raise ImportError(
                "TransformersTokenizer requires the optional 'transformers' "
                "dependency. Install it with 'lumberjack[tokenizers]'."
            ) from e

        if _tokenizer is None:
            try:
                from transformers import AutoTokenizer
            except ImportError as e:
                raise ImportError(
                    "TransformersTokenizer requires the optional 'transformers' "
                    "dependency. Install it with 'lumberjack[tokenizers]'."
                ) from e
            _tokenizer = cast(
                _TransformersTokenizerProtocol,
                AutoTokenizer.from_pretrained(model, use_fast=True),
            )

        self.model = model
        self.tokenizer = _tokenizer
        self.max_cache_size = max_cache_size
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

    def with_fresh_cache(self) -> TransformersTokenizer:
        """Share the model backend while allocating a new request-local cache."""
        return TransformersTokenizer(
            model=self.model,
            max_cache_size=self.max_cache_size,
            default_cache=self.default_cache,
            _tokenizer=self.tokenizer,
        )

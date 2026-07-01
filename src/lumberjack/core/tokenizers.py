from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Literal, TypeAlias, cast

from .protocols import TokenizerProtocol

TokenCounterMode: TypeAlias = Literal["accurate", "incremental"]  # noqa: UP040
TokenizerName: TypeAlias = Literal["approx", "tiktoken", "transformers"]  # noqa: UP040


DEFAULT_TRANSFORMERS_MODEL = "bert-base-uncased"


def _normalize_token_counter(token_counter: str) -> TokenCounterMode:
    normalized = token_counter.strip().lower()
    if normalized not in {"accurate", "incremental"}:
        raise ValueError(f"Unsupported token_counter: {token_counter}")
    return cast(TokenCounterMode, normalized)


class TokenCountingMixin:
    """Shared token counting behavior implemented by tokenizer engines."""

    _DELTA_WINDOW = 8
    token_counter: TokenCounterMode

    def count(self, text: str, *, cache=False) -> int:
        raise NotImplementedError

    @property
    def is_incremental(self) -> bool:
        return self.token_counter == "incremental"

    def count_text(self, text: str) -> int:
        return self.count(text, cache=True)

    def count_budget_text(self, text: str, *, estimated_count: int) -> int:
        if self.token_counter == "incremental":
            return estimated_count
        return self.count_text(text)

    def count_estimated_text(self, text: str, *, estimated_count: int) -> int:
        if self.token_counter == "incremental":
            return estimated_count
        return self.count_text(text)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        if self.is_incremental:
            text = text.rstrip("\n")[-self._DELTA_WINDOW :]
        return self.count(f"{text}{separator}", cache=True) - self.count(
            text, cache=True
        )


class TiktokenTokenizer(TokenCountingMixin, TokenizerProtocol):
    """Tokenizer backed by the tiktoken library."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_cache_size: int = 1000,
        default_cache: bool | None = None,
        token_counter: str = "accurate",
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
        self.token_counter = _normalize_token_counter(token_counter)
        self.encoding = tiktoken.encoding_for_model(model)
        self.default_cache = (
            self.token_counter == "accurate" if default_cache is None else default_cache
        )
        self._cache: LRUCache[str, tuple[int, ...]] = LRUCache(maxsize=max_cache_size)

        self._lock = RLock()

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
            with self._lock:
                cached = self._cache.get(text)
                if cached is not None:
                    return cached
        token_ids = tuple(self.encoding.encode(text))

        if use_cache:
            with self._lock:
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
        with self._lock:
            self._cache.clear()


class ApproxCharTokenizer(TokenCountingMixin, TokenizerProtocol):
    """Approximate tokenizer that estimates tokens as ``len(text) // 4``.

    A common industry rule of thumb (character count divided by four) used by
    the ``tokenizer="approx"`` engine.  The splitter only uses :meth:`count`;
    :meth:`encode` is a protocol placeholder.
    """

    def __init__(self, token_counter: str = "accurate") -> None:
        self.token_counter = _normalize_token_counter(token_counter)
        if self.token_counter == "incremental":
            raise ValueError(
                "ApproxCharTokenizer does not support incremental counting"
            )

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text) // 4


class TransformersTokenizer(TokenCountingMixin, TokenizerProtocol):
    """Tokenizer backed by a Hugging Face fast tokenizer."""

    def __init__(
        self,
        model: str = DEFAULT_TRANSFORMERS_MODEL,
        max_cache_size: int = 1000,
        token_counter: str = "accurate",
    ) -> None:
        try:
            from transformers import AutoTokenizer  # type: ignore
        except ImportError as e:
            raise ImportError(
                "TransformersTokenizer requires the optional 'transformers' "
                "dependency. Install it with 'lumberjack[tokenizers]'."
            ) from e

        self.model = model
        self.token_counter = _normalize_token_counter(token_counter)
        self.tokenizer = AutoTokenizer.from_pretrained(model, use_fast=True)
        self.max_cache_size = max_cache_size
        self._cache: OrderedDict[str, tuple[int, ...]] = OrderedDict()
        self._lock = RLock()

    def encode(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> tuple[int, ...]:
        if not text:
            return ()

        if cache:
            with self._lock:
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    return cached

        token_ids = tuple(self.tokenizer.encode(text))

        if cache:
            with self._lock:
                self._cache[text] = token_ids
                self._cache.move_to_end(text)
                if len(self._cache) > self.max_cache_size:
                    self._cache.popitem(last=False)

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
        with self._lock:
            self._cache.clear()


def create_tokenizer(
    name: str,
    *,
    token_counter: str = "accurate",
) -> TokenizerProtocol:
    """Instantiate a tokenizer by name."""
    normalized = name.strip().lower()
    if normalized == "approx":
        return ApproxCharTokenizer(token_counter=token_counter)
    if normalized == "tiktoken":
        return TiktokenTokenizer(token_counter=token_counter)
    if normalized == "transformers":
        return TransformersTokenizer(token_counter=token_counter)
    raise ValueError(f"Unsupported tokenizer: {name}")

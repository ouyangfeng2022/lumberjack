from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from .protocols import TokenizerProtocol

DEFAULT_TRANSFORMERS_MODEL = "bert-base-uncased"


class TiktokenTokenizer(TokenizerProtocol):
    """Tokenizer backed by the tiktoken library.

    Incremental-count engine (``is_exact = False``): the splitter uses the
    additive incremental estimate path (pre-measured sections + an 8-char
    separator-delta window in the splitter) for budget decisions, and only
    fully recounts at finalization.
    """

    is_exact = False

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


class ApproxCharTokenizer(TokenizerProtocol):
    """Approximate tokenizer that estimates tokens as ``len(text) // 4``.

    Exact-count engine (``is_exact = True``): the splitter fully recounts
    rendered text at every budget decision and never uses incremental
    arithmetic.
    """

    is_exact = True

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text) // 4


class TransformersTokenizer(TokenizerProtocol):
    """Tokenizer backed by a Hugging Face fast tokenizer (incremental path)."""

    is_exact = False

    def __init__(
        self,
        model: str = DEFAULT_TRANSFORMERS_MODEL,
        max_cache_size: int = 1000,
    ) -> None:
        try:
            from transformers import AutoTokenizer  # type: ignore
        except ImportError as e:
            raise ImportError(
                "TransformersTokenizer requires the optional 'transformers' "
                "dependency. Install it with 'lumberjack[tokenizers]'."
            ) from e

        self.model = model
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


def create_tokenizer(name: str) -> TokenizerProtocol:
    """Instantiate a tokenizer by name."""
    normalized = name.strip().lower()
    if normalized == "approx":
        return ApproxCharTokenizer()
    if normalized == "tiktoken":
        return TiktokenTokenizer()
    if normalized == "transformers":
        return TransformersTokenizer()
    raise ValueError(f"Unsupported tokenizer: {name}")

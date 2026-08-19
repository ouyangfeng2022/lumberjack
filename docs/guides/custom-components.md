# Custom components

[中文](../zh-CN/guides/custom-components.md)

The default `Lumberjack` assembly can be replaced one stage at a time. The public interfaces are declared in `lumberjack.protocols`.

## Custom tokenizer

A tokenizer implements `encode()` and `count()`. Give the same instance to a splitter and to `Lumberjack` so split-time and final counts agree.

```python
from lumberjack import Lumberjack
from lumberjack.splitter import SiblingSplitter


class WordTokenizer:
    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:
        return tuple(range(len(text.split())))

    def count(self, text: str, *, cache: bool = False) -> int:
        return len(text.split())


tokenizer = WordTokenizer()
jack = Lumberjack(
    tokenizer=tokenizer,
    splitter=SiblingSplitter(tokenizer, max_tokens=200),
)
```

## Custom parser or splitter

A parser accepts a `Document` and returns a `DocTree`; it also declares the block kinds it can emit. A splitter exposes its tokenizer and turns that `DocTree` into `ChunkDraft` values. Reuse `DocumentBlock`, `SectionNode`, and `DocTree` rather than introducing a parallel tree model.

```python
jack = Lumberjack(parser=my_parser, splitter=my_splitter)
result = jack.saw("raw source", format="markdown")
```

For Markdown-specific extensions, use the public block handler and block-spec types in `lumberjack.parser`. For a custom block kind, pair the parser output with `CustomBlockConfig` when configuring a built-in splitter.

## Normalize or transform final text

Supply a `normalizer` with `normalize(text)` or a `transformer` with `transform(text)`. Both run after splitting and before the final authoritative count. This is the safe point to change output surface syntax without changing the parser or splitter topology.

```python
from lumberjack.transformer import PlainTextTransformer

jack = Lumberjack(transformer=PlainTextTransformer())
```

See the [Python API reference](../reference/python.md) for every public component and protocol.

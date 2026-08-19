# 自定义组件

[English](../../guides/custom-components.md)

默认 `Lumberjack` 组装可逐阶段替换。公开接口定义在 `lumberjack.protocols`。

## 自定义 tokenizer

tokenizer 需要实现 `encode()` 和 `count()`。把同一个实例同时传给 splitter 和 `Lumberjack`，以保证拆分时与最终计数一致。

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

## 自定义 parser 或 splitter

parser 接受 `Document` 并返回 `DocTree`，还需声明自己可能产生的 block kind。splitter 暴露 tokenizer，并将 `DocTree` 转为 `ChunkDraft`。请复用 `DocumentBlock`、`SectionNode` 和 `DocTree`，不要引入并行的树模型。

```python
jack = Lumberjack(parser=my_parser, splitter=my_splitter)
result = jack.saw("raw source", format="markdown")
```

Markdown 专属扩展请使用 `lumberjack.parser` 中的公开 block handler 与 block spec 类型。自定义 block kind 可在配置内置 splitter 时配合 `CustomBlockConfig`。

## 规范化或转换最终文本

传入具有 `normalize(text)` 的 `normalizer` 或具有 `transform(text)` 的 `transformer`。两者都在拆分后、权威最终计数前执行；这是改变输出表面语法而不改变 parser/splitter 拓扑的安全位置。

```python
from lumberjack.transformer import PlainTextTransformer

jack = Lumberjack(transformer=PlainTextTransformer())
```

所有公开组件与 protocol 请见 [Python API 参考](../reference/python.md)。

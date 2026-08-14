# Lumberjack

面向 RAG 预处理的结构感知 Markdown、HTML 与 DOCX 文档伐木流水线。

```text
Document -> Parser.parse() -> DocTree -> Splitter.split() -> ChunkDraft[]
     -> ChunkFinalizer.finalize() -> TextNormalizer -> TextTransformer -> Chunk[]
```

## 安装

```bash
pip install lumberjack

# 可选 tokenizer、DOCX 与 Web API 依赖
pip install "lumberjack[tokenizers,docx,web]"
```

要求 Python 3.10 或更高版本。

## 主 API

包顶层只暴露 `Lumberjack` 与 `Document`：

```python
from pathlib import Path

from lumberjack import Lumberjack, Document

jack = Lumberjack(max_tokens=1200)

# 原始值会被自动包成 Document。
chunks = jack.saw(Path("guide.md"))

# Document 显式携带格式、标题、元数据和来源信息。
chunks = jack.saw(
    Document(
        source=markdown_text,
        format="markdown",
        document_title="Guide",
        metadata_overrides={"tenant": "docs"},
        source_path="imports/guide.md",
    )
)
```

`Lumberjack()` 默认装配 `AutoParser`、`ApproxByteTokenizer`、增量式
`SiblingSplitter`、`TextNormalizer`、`TextTransformer` 与 `ChunkFinalizer`。Splitter 的预算估算和 ChunkFinalizer
的最终计数使用同一个 tokenizer 实例。

## 组件式流水线

```python
from pathlib import Path

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.parser import AutoParser
from lumberjack.finalizer import ChunkFinalizer
from lumberjack.models import Document
from lumberjack.splitter import SiblingSplitter
from lumberjack.tokenizer import TiktokenTokenizer

tokenizer = TiktokenTokenizer(model="gpt-4o-mini")
parser = AutoParser()
splitter = SiblingSplitter(
    tokenizer,
    max_tokens=1200,
    block_options=[
        MarkdownTableConfig(isolated=True, max_tokens=500),
        BlockConfig(BlockKind.CODE_FENCE, split=False),
    ],
)
finalize = ChunkFinalizer(tokenizer)

document = parser.parse(Document(Path("guide.md")))
drafts = splitter.split(document)
chunks = finalize.finalize(document, drafts)
```

公共组件：

- `lumberjack.parser`：`AutoParser`、`MarkdownParser`、`HTMLParser` 与
  `DocxParser`，负责把 `Document` 砍成统一的 `DocTree`。
- `lumberjack.tokenizer`：`ApproxByteTokenizer`、`TiktokenTokenizer` 与
  `TransformersTokenizer`，提供 `encode()` 和 `count()`。
- `lumberjack.splitter`：默认增量式的 `SiblingSplitter`、`SubtreeSplitter`、
  `SectionSplitter`，以及显式 `Exact*Splitter`，负责产出 `ChunkDraft`。
- `lumberjack.finalizer`：渲染、处理、重计并完成最终 `Chunk`。
- `lumberjack.normalizer` 与 `lumberjack.transformer`：可替换的后处理阶段。
- `lumberjack.models` 与 `lumberjack.protocols`：共享状态和扩展协议。

已移除的 `feller`、`sawyer` 与 `scaler` 不是兼容导入路径；`parser`、`splitter` 与 `tokenizer` 是支持的公共组件命名空间。

## Parser 与 DocTree

`AutoParser` 按以下顺序推断输入格式：

1. `Path` 或 `Document.source_path` 的文件后缀。
2. DOCX ZIP 结构。
3. 文本开头的 HTML doctype 或结构化标签。
4. 回退为 Markdown。

普通 `str` 始终被视为文档内容，不会被隐式当成磁盘路径。格式专属 parser
也允许直接传入原始值：

```python
from lumberjack.parser import MarkdownParser

document = MarkdownParser(disable_lheading=False).parse(
    markdown_text,
    document_title="Guide",
    metadata_overrides={"tenant": "docs"},
    source_path="imports/guide.md",
)
```

`DocTree.metadata` 保存语义元数据；`DocTree.source_path` 单独保存来源，并最终写入
`Chunk.document_path`。

## Splitter 与 ChunkDraft

```python
from lumberjack.splitter import SiblingSplitter

splitter = SiblingSplitter(
    tokenizer,
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    heading_sensitive=True,
    max_heading_level=None,
)

drafts = splitter.split(document)
```

- `SiblingSplitter` 贪心打包相邻同级 section。
- `SubtreeSplitter` 优先收拢可容纳的子树，再回退到 section。
- `SectionSplitter` 递归输出各 section 的直接正文，不折叠子树。
- `Exact*Splitter` 在每次预算决策时完整重计渲染文本；无前缀 splitter 使用增量估算。

`ChunkDraft.token_count` 是锯切时的估算占用。ChunkFinalizer 在文本处理后执行权威重计；增量
splitter 的估算写入 `Chunk.estimated_token_count`，精确 splitter 的估算与最终值相等。

## 风干、刨平与制材

默认 `TextNormalizer` 将 CRLF/CR 规范为 LF，并移除 BOM/NUL。默认 `TextTransformer` 清理行尾
空白和重复空行，但保留 Markdown 语法。

`PlainTextTransformer` 是显式的纯文本选项，会去除常见 Markdown/HTML 表面格式，同时
保留可读正文、代码文本和段落边界：

```python
from lumberjack import Lumberjack
from lumberjack.transformer import PlainTextTransformer

jack = Lumberjack(transformer=PlainTextTransformer())
chunks = jack.saw(markdown_text)
```

可以通过 `Lumberjack(...)` 注入自定义 `ParserProtocol`、`TokenizerProtocol`、
`SplitterProtocol`、`TextNormalizerProtocol` 与 `TextTransformerProtocol` 实现。

## 类型安全的 Block 配置

Python `block_options` 接受 `BlockConfig`、`MarkdownTableConfig`、
`HTMLTableConfig` 或 `CustomBlockConfig` 对象序列。重复 kind 和非正数预算会在
构造阶段直接报错。

## CLI 与 Web API

```bash
lumber guide.md --max-tokens 1200
lumber guide.md --tokenizer tiktoken --splitter sibling
lumber guide.md --splitter exact-sibling
lumber report.docx --input-format docx
lumberjack-serve --reload
```

- `POST /lumber/api/split/text`
- `POST /lumber/api/split/file`

集成协议继续使用既有的 `tokenizer` 和 `splitter` 字段；私有边界适配器负责映射到
Tokenizer 与 Splitter。CLI JSON 和 Web 响应保持既有的 `Chunk` 序列化结构。

## 开发

```bash
uv sync --group dev --group test --extra tokenizers --extra docx --extra web
UV_CACHE_DIR=/tmp/uvcache uv run ty check .
UV_CACHE_DIR=/tmp/uvcache uv run ruff check
UV_CACHE_DIR=/tmp/uvcache uv run ruff format --check
UV_CACHE_DIR=/tmp/uvcache uv run pytest
```

## 许可证

MIT

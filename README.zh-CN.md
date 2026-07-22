# Lumberjack

面向 RAG 预处理的结构感知 Markdown、HTML 与 DOCX 文档切分器。

Lumberjack 将解析、分词计数与切分拆分为清晰的组件。所有 parser 都生成统一的
`DocumentAST`，因此任意 splitter 都可以处理任意受支持的格式。

## 安装

```bash
pip install lumberjack

# 可选 tokenizer、DOCX 与 Web API 依赖
pip install "lumberjack[tokenizers,docx,web]"
```

要求 Python 3.10 或更高版本。

## 极简 API

包顶层只暴露 `lumber()`：

```python
from pathlib import Path

from lumberjack import lumber

chunks = lumber(Path("guide.md"), max_tokens=1200)
```

`lumber()` 固定使用 `AutoParser`、`ApproxCharTokenizer` 和增量式
`SiblingSplitter`。完整签名为：

```python
lumber(
    source: str | bytes | Path,
    *,
    format: Literal["auto", "markdown", "html", "docx"] = "auto",
    max_tokens: int = 1200,
) -> list[Chunk]
```

如需其他配置，请使用分层组件 API。

## 组件式 pipeline

```python
from pathlib import Path

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.parser import AutoParser
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

document = parser.parse(Path("guide.md"))
chunks = splitter.split(document)
```

公共组件按职责直接拥有各自实现：

- `lumberjack.parser`：`AutoParser`、`MarkdownParser`、`HTMLParser`、
  `DocxParser` 以及 Markdown plugin 扩展类型。
- `lumberjack.splitter`：默认增量式的 `SiblingSplitter`、`SubtreeSplitter`、
  `SectionSplitter`，以及显式 `Exact*Splitter`。
- `lumberjack.tokenizer`：三个 tokenizer 实现。
- `lumberjack.block`：类型安全的 block kind 与配置对象。
- `lumberjack.models`：统一 AST 与 `Chunk` 输出类型。
- `lumberjack.protocols`：自定义组件协议。

项目不提供 `lumberjack.core` 公共包或兼容导出；跨组件的私有适配器放在
`lumberjack._internal` 中。

## Parser

### 自动选择 parser

```python
from lumberjack.parser import AutoParser

parser = AutoParser()
document = parser.parse(text, source_path="archive/guide.md")
```

`format="auto"` 按以下顺序推断：

1. `Path` 输入或显式 `source_path` 的文件后缀。
2. DOCX ZIP 结构。
3. 文本开头的 HTML doctype 或结构化 HTML 标签。
4. 回退为 Markdown。

普通 `str` 始终被视为文档内容。读取文件时必须使用 `Path("guide.md")`，不会对
字符串执行隐式磁盘路径检查。

使用 `AutoParser(format="markdown")`、`"html"` 或 `"docx"` 可强制格式。

### Parser 专属配置

```python
from lumberjack.parser import MarkdownParser

# 默认禁用 Setext 标题；传入 False 才启用。
parser = MarkdownParser(disable_lheading=False)
document = parser.parse(markdown_text)
```

所有 parser 接受一致的文档级关键字参数：

```python
document = parser.parse(
    source,
    document_title="Guide",
    metadata_overrides={"tenant": "docs"},
    source_path="imports/guide.md",
)
```

`DocumentAST.metadata` 保存 front matter、HTML metadata 或 DOCX core properties
等语义元数据，`metadata_overrides` 用于补充或覆盖它们。来源标识单独保存在
`DocumentAST.source_path`，并生成 `Chunk.document_path`。

## Splitter

无前缀的 Python 类默认使用增量式计量：

```python
from lumberjack.splitter import SiblingSplitter

splitter = SiblingSplitter(
    tokenizer,
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    render_headings=True,
    max_heading_level=None,
)
```

- `SiblingSplitter`：贪心打包相邻同级 section。
- `SubtreeSplitter`：优先折叠可容纳的子树，再回退为按 section 切分。
- `SectionSplitter`：递归输出各 section 的直接正文；不接受无效的
  `merge_below_ratio` 参数。
- `ExactSiblingSplitter`、`ExactSubtreeSplitter`、`ExactSectionSplitter`：每次预算
  决策都完整重计渲染文本。

增量式 splitter 将最终权威计数写入 `token_count`，将切分时估算写入
`estimated_token_count`；精确 splitter 的两个值相等。

## 类型安全的 Block 配置

Python `block_options` 只接受配置对象序列，不接受 dict：

```python
from lumberjack.block import (
    BlockConfig,
    BlockKind,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)

block_options = [
    BlockConfig(BlockKind.LIST, isolated=True),
    BlockConfig(BlockKind.CODE_FENCE, split=False),
    MarkdownTableConfig(max_tokens=500, repeat_header=True),
    HTMLTableConfig(max_tokens=500, repeat_header=False),
    CustomBlockConfig("callout", isolated=True),
]
```

普通内置 block 由 `BlockKind` 指定；两个表格配置类隐式绑定各自 kind；plugin
自定义 block 使用 `CustomBlockConfig`。重复 kind 和非正数预算会在构造 splitter
时直接报错。

## 自定义组件

实现 `lumberjack.protocols` 中的协议，然后直接组合对象：

```python
from lumberjack.parser import MarkdownParser

document = MarkdownParser().parse(markdown_text)
chunks = custom_splitter.split(document)
```

项目不提供公共 Pipeline、Builder、Options 聚合对象、registry factory 或模块级
`parse()` 函数。

## CLI

```bash
lumber guide.md --max-tokens 1200
lumber guide.md --tokenizer tiktoken --splitter sibling
lumber guide.md --splitter exact-sibling
lumber report.docx --input-format docx
lumber guide.md --block-config table:isolated:500
```

CLI 中无前缀 splitter 名默认使用增量式计量；`incremental-*` 是等价显式别名，
`exact-*` 选择完整重计。输出格式为 JSON。

## Web API

```bash
lumberjack-serve --reload
```

- `POST /lumber/api/split/text`
- `POST /lumber/api/split/file`

CLI 与 Web 的外部字段结构保持不变；边界层负责把 JSON block 配置转换为 Python
类型安全配置对象。

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

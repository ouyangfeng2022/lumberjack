# Lumberjack

面向 RAG 预处理的结构感知 Markdown、HTML 与 DOCX 文档伐木流水线。

```text
Tree -> Feller.fell() -> Log -> Sawyer.saw() -> Bundle[]
     -> Mill.mill() -> Seasoner -> Planer -> Chunk[]
```

## 安装

```bash
pip install lumberjack

# 可选 scaler、DOCX 与 Web API 依赖
pip install "lumberjack[tokenizers,docx,web]"
```

要求 Python 3.10 或更高版本。

## 主 API

包顶层只暴露 `Lumberjack` 与 `Tree`：

```python
from pathlib import Path

from lumberjack import Lumberjack, Tree

jack = Lumberjack(max_tokens=1200)

# 原始值会被自动包成 Tree。
chunks = jack.saw(Path("guide.md"))

# Tree 显式携带格式、标题、元数据和来源信息。
chunks = jack.saw(
    Tree(
        source=markdown_text,
        format="markdown",
        document_title="Guide",
        metadata_overrides={"tenant": "docs"},
        source_path="imports/guide.md",
    )
)
```

`Lumberjack()` 默认装配 `AutoFeller`、`ApproxByteScaler`、增量式
`SiblingSawyer`、`Seasoner`、`Planer` 与 `Mill`。Sawyer 的预算估算和 Mill
的最终计数使用同一个 scaler 实例。

## 组件式流水线

```python
from pathlib import Path

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.feller import AutoFeller
from lumberjack.mill import Mill
from lumberjack.models import Tree
from lumberjack.sawyer import SiblingSawyer
from lumberjack.scaler import TiktokenScaler

scaler = TiktokenScaler(model="gpt-4o-mini")
feller = AutoFeller()
sawyer = SiblingSawyer(
    scaler,
    max_tokens=1200,
    block_options=[
        MarkdownTableConfig(isolated=True, max_tokens=500),
        BlockConfig(BlockKind.CODE_FENCE, split=False),
    ],
)
mill = Mill(scaler)

log = feller.fell(Tree(Path("guide.md")))
bundles = sawyer.saw(log)
chunks = mill.mill(log, bundles)
```

公共组件：

- `lumberjack.feller`：`AutoFeller`、`MarkdownFeller`、`HTMLFeller` 与
  `DocxFeller`，负责把 `Tree` 砍成统一的 `Log`。
- `lumberjack.scaler`：`ApproxByteScaler`、`TiktokenScaler` 与
  `TransformersScaler`，提供 `encode()` 和 `scale()`。
- `lumberjack.sawyer`：默认增量式的 `SiblingSawyer`、`SubtreeSawyer`、
  `SectionSawyer`，以及显式 `Exact*Sawyer`，负责产出 `Bundle`。
- `lumberjack.mill`：渲染、处理、重计并完成最终 `Chunk`。
- `lumberjack.seasoner` 与 `lumberjack.planer`：可替换的后处理阶段。
- `lumberjack.models` 与 `lumberjack.protocols`：共享状态和扩展协议。

已移除的 `parser`、`splitter`、`tokenizer` 与 `core` 包不是兼容导入路径。

## Feller 与 Log

`AutoFeller` 按以下顺序推断输入格式：

1. `Path` 或 `Tree.source_path` 的文件后缀。
2. DOCX ZIP 结构。
3. 文本开头的 HTML doctype 或结构化标签。
4. 回退为 Markdown。

普通 `str` 始终被视为文档内容，不会被隐式当成磁盘路径。格式专属 feller
也允许直接传入原始值：

```python
from lumberjack.feller import MarkdownFeller

log = MarkdownFeller(disable_lheading=False).fell(
    markdown_text,
    document_title="Guide",
    metadata_overrides={"tenant": "docs"},
    source_path="imports/guide.md",
)
```

`Log.metadata` 保存语义元数据；`Log.source_path` 单独保存来源，并最终写入
`Chunk.document_path`。

## Sawyer 与 Bundle

```python
from lumberjack.sawyer import SiblingSawyer

sawyer = SiblingSawyer(
    scaler,
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    heading_sensitive=True,
    max_heading_level=None,
)

bundles = sawyer.saw(log)
```

- `SiblingSawyer` 贪心打包相邻同级 section。
- `SubtreeSawyer` 优先收拢可容纳的子树，再回退到 section。
- `SectionSawyer` 递归输出各 section 的直接正文，不折叠子树。
- `Exact*Sawyer` 在每次预算决策时完整重计渲染文本；无前缀 sawyer 使用增量估算。

`Bundle.token_count` 是锯切时的估算占用。Mill 在文本处理后执行权威重计；增量
sawyer 的估算写入 `Chunk.estimated_token_count`，精确 sawyer 的估算与最终值相等。

## 风干、刨平与制材

默认 `Seasoner` 将 CRLF/CR 规范为 LF，并移除 BOM/NUL。默认 `Planer` 清理行尾
空白和重复空行，但保留 Markdown 语法。

`PlainTextPlaner` 是显式的纯文本选项，会去除常见 Markdown/HTML 表面格式，同时
保留可读正文、代码文本和段落边界：

```python
from lumberjack import Lumberjack
from lumberjack.planer import PlainTextPlaner

jack = Lumberjack(planer=PlainTextPlaner())
chunks = jack.saw(markdown_text)
```

可以通过 `Lumberjack(...)` 注入自定义 `FellerProtocol`、`ScalerProtocol`、
`SawyerProtocol`、`SeasonerProtocol` 与 `PlanerProtocol` 实现。

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
Scaler 与 Sawyer。CLI JSON 和 Web 响应保持既有的 `Chunk` 序列化结构。

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

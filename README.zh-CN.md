<p align="center">
  <img src="assets/logo.png" alt="lumberjack" width="200">
</p>

<h1 align="center">lumberjack</h1>

<p align="center">
  <strong>面向 RAG 预处理的通用结构化文档分割器</strong>
</p>

<p align="center">
  按文档结构而非固定文本窗口，将文档拆成开箱即用的分块。
  保留标题层级、块完整性和有用元数据，并通过可复用估算尽可能减少 tokenizer 计算。
</p>

<p align="center">
  <a href="README.md">English</a>
</p>

---

## 为什么选择 lumberjack？

多数分割器从纯文本窗口开始处理。这很简单，但会忽略真实文档里已经存在的语义结构：标题、嵌套章节、表格、列表、代码块、数学公式、front matter 和源码位置。**lumberjack** 会先解析输入，构建统一的 `DocumentAST`，再把这棵树拆成可直接用于索引、检索或检查的 `Chunk[]`。

- **通用输入，统一输出** —— 当前支持 Markdown、HTML 和 DOCX；每种解析器都会产出同一套 `DocumentAST` 与 `Chunk[]` 数据模型。
- **开箱即用** —— Python API、CLI、Web API 和 Web UI 都已内置，不需要自己拼接 parser 和 splitter。
- **结构化拆分** —— 优先沿标题章节、嵌套章节树和块边界拆分，必要时才回退到文本级拆分。
- **保留上下文** —— 每个分块都带有渲染后的标题面包屑、源码行号、块类型、token 数和文档元数据。
- **块级策略** —— 代码块、表格、数学公式、front matter 等特殊块可以按类型保持完整、允许拆分或单独隔离。
- **估算优先的 token 规划** —— 通过可复用 token 估算、缓存计数和 `ideal_max_tokens_ratio` 拆分预算减少重复 tokenizer 调用，同时最终分块仍会报告实测 token 数。

核心流程：

```text
Markdown 文本 → MarkdownItParser → DocumentAST → splitter → Chunk[]
HTML 文本     → HTMLParser ─────────────────────┤
DOCX 二进制   → DocxParser ─────────────────────┘
```

### 为什么不是朴素文本分割？

朴素文本分割适合无结构笔记，但在结构化文档里容易切断语义边界，让后续检索再去猜上下文。lumberjack 会让文档结构参与整个过程：先解析，再按树拆分，在预算允许时合并，只在块或章节过大时才使用段落、行、句子、词和硬切分回退。

## 安装

### 作为库使用

```bash
pip install lumberjack
```

可选扩展：

```bash
pip install "lumberjack[tokenizers]"   # 基于 tiktoken 的模型 token 计数
pip install "lumberjack[docx]"         # DOCX 文档支持
pip install "lumberjack[web]"          # FastAPI Web 服务器 + UI
pip install "lumberjack[all]"          # 包含全部功能
```

> [!NOTE]
> 需要 Python 3.13+。

### 从源码构建（用于开发）

```bash
git clone https://github.com/tianleG/lumberjack.git
cd lumberjack
uv sync --all-group --all-extra
```

完整的开发工作流请参见[开发](#开发)章节。

## 快速开始

### Python API

```python
from lumberjack import lumber

chunks = lumber(
    "# Introduction\n\nSome content...\n\n## Details\n\nMore content.",
    max_tokens=1200,
)

for chunk in chunks:
    print(f"[{chunk.chunk_id}] tokens={chunk.token_count}")
    print(chunk.body)
    print()
```

### CLI

```bash
lumber document.md --max-tokens 1200
```

### Web UI

```bash
pip install "lumberjack[web]"
lumberjack-serve
```

打开 <http://localhost:9612> —— 粘贴文本或上传文件，配置参数，并可视化查看分块结果。

## 使用说明

### Python API

默认公共 API 只有一个函数 —— [`lumber()`](src/lumberjack/lumber.py)。它是开箱即用的
默认管线，`tokenizer` 和 `splitter` 只接受内置实现的字符串选择器：

```python
from lumberjack import lumber

# 完整选项
chunks = lumber(
    markdown_text,
    format="markdown",        # "auto" | "markdown" | "html" | "docx"
    document_title="guide.md",
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_tokens=50,
    skip_empty_sections=True,
    render_headings=True,      # 设为 False 可从分块正文中移除该分块的公共标题前缀
    tokenizer="simple",        # "simple" | "tiktoken"
    splitter="recursive",      # "recursive" | "section"
)
```

HTML 输入复用同一条切分管线：

```python
chunks = lumber(
    "<h1>Guide</h1><p>Intro</p>",
    format="html",
    max_tokens=1200,
)
```

每个返回的 `Chunk` 都包含：

| 字段 | 说明 |
| --- | --- |
| `chunk_id` | 唯一标识符 |
| `chunk_type` | 来源块类型（`"heading"`、`"paragraph"`、`"code_fence"`、...） |
| `body` | 带有标题面包屑的渲染文本 |
| `token_count` | 根据最终正文计算的 token 数 |
| `estimated_token_count` | 切分时使用的预算估算值 |
| `headings` | `(level, title)` 元组 —— 标题面包屑 |
| `section_level` | 当前分块中最深的标题层级 |
| `document_title` | 从 front matter 或首个 H1 解析得到的文档标题 |
| `start_line` / `end_line` | 源文件中的 1 起始行范围 |

#### 按块类型配置

控制各类块的切分和合并行为：

```python
from lumberjack import lumber
from lumberjack.core.models import BaseParams, TableBlockParams

chunks = lumber(
    markdown_text,
    block_options={
        # 表格：独立分块、500 token 预算，拆分后不重复表头
        "table": TableBlockParams(
            isolated=True,
            max_tokens=500,
            repeat_header=False,
        ),
        # 代码块：即使超长也保持完整
        "code_fence": BaseParams(split=False),
        # 段落：自定义预算
        "paragraph": BaseParams(max_tokens=800),
    },
)
```

`BaseParams` 字段：

- **`isolated`** (`bool`) —— 作为独立分块输出，不会与相邻内容合并
- **`split`** (`bool`) —— 允许拆分超长块
- **`max_tokens`** (`int | None`) —— 该块类型的预算覆盖值；`None` 时使用全局 `max_tokens`
- 各块类型的专属 params 都继承这些公共字段。`TableBlockParams` 为 `table` 和 `html_table` 增加 **`repeat_header`** (`bool`)；其他块类型在定义自己的 params 类型前会拒绝表格专属字段。

有效的块类型包括：`paragraph`、`blockquote`、`list`、`list_item`、`table`、`html_table`、`code_block`、`code_fence`、`html_block`、`front_matter`、`math_block`、`math_block_eqno`。

> [!NOTE]
> **HTML 表格**：HTML 表格（`<table>`）被识别为 `html_table` 块类型，与 Markdown 表格独立处理。它们在切分时保留原始 HTML 格式和属性（如 `border`、`style`、`colspan`、`rowspan`）。使用 `"html_table": TableBlockParams(isolated=True)` 可独立于 Markdown 表格进行配置。

#### 自定义 Parser / Tokenizer / Splitter

`lumber()` 会刻意保持朴素、通用。如果需要自定义 parser、tokenizer 或 splitter，
直接组合底层组件即可：先 parse 一次，再 split 一次。

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.models import SplitOptions
from lumberjack.core.options import resolve_block_options
from lumberjack.core.parsers.markdown.parser import MarkdownItParser
from lumberjack.core.splitters import RecursiveSplitter
from lumberjack.core.tokenizers import TiktokenTokenizer

parser = MarkdownItParser(plugins=(tasklists_plugin,))
tokenizer = TiktokenTokenizer(model="gpt-4o-mini")

document = parser.parse(markdown_text, document_title="guide.md")
options = SplitOptions(
    max_tokens=1200,
    block_options=resolve_block_options(parser.block_kinds, None),
)
splitter = RecursiveSplitter(tokenizer=tokenizer, options=options)

chunks = splitter.split(document)
```

自定义组件应遵循 [`lumberjack.core.protocols`](src/lumberjack/core/protocols.py)
中的协议。它们不通过 `lumber()` 传入，而是用于自行构建的 `parse -> split` 管线。

### CLI

```bash
lumber <input> [options]
```

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `input` | — | Markdown (.md)、HTML (.html) 或 DOCX (.docx) 文件路径 |
| `--input-format` | `auto` | `auto`、`markdown`、`html` 或 `docx` |
| `-o`, `--output` | stdout | 将输出写入文件 |
| `--max-tokens` | `1200` | 最大分块 token 预算 |
| `--ideal-max-tokens-ratio` | `0.8` | 优先切分预算比例 |
| `--merge-below-tokens` | `50` | 小分块合并软阈值 |
| `--tokenizer` | `simple` | `simple` 或 `tiktoken` |
| `--splitter` | `recursive` | `recursive` 或 `section` |
| `--render-headings` | on | 在分块正文中渲染公共标题前缀（用 `--no-render-headings` 关闭；`chunk.headings` 始终保留） |
| `--block-config` | — | 按块类型配置（可重复指定） |
| `--block-config-json` | — | 结构化的按块类型 JSON 配置 |

`--block-config` 的语法为：`KIND[:isolated][:nosplit][:TOKENS]`

```bash
# 表格独立、禁止拆分、500 token 预算
lumber doc.md --block-config table:isolated:nosplit:500

# 代码块保持完整
lumber doc.md --block-config code_fence:nosplit

# 多个块类型配置
lumber doc.md --block-config table:isolated --block-config code_fence:nosplit

# 表格专属参数：拆分表格时只在第一片保留表头
lumber doc.md --block-config-json '{"table":{"repeat_header":false}}'
```

**JSON 输出** 包含 `document`、`chunk_count` 和完整元数据的 `chunks` 数组。

### Web API

启动服务器：

```bash
lumberjack-serve --host 127.0.0.1 --port 9612
```

#### `POST /lumber/api/split/text`

```bash
curl -X POST http://localhost:9612/lumber/api/split/text \
  -H "Content-Type: application/json" \
  -d '{"text": "# Hello\n\nWorld", "input_format": "markdown", "max_tokens": 500}'
```

#### `POST /lumber/api/split/file`

```bash
curl -X POST http://localhost:9612/lumber/api/split/file \
  -F "file=@guide.md" \
  -F "input_format=auto" \
  -F "max_tokens=500" \
  -F "splitter=section"
```

#### Web API 选项

两个接口都接受相同的选项：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `input_format` | string | 文本接口为 `"markdown"`，文件上传为 `"auto"` | `auto`、`markdown`、`html` 或 `docx` |
| `max_tokens` | int | `1200` | 最大分块 token 预算 |
| `ideal_max_tokens_ratio` | float | `0.8` | 优先切分预算比例 |
| `merge_below_tokens` | int | `50` | 小分块合并软阈值 |
| `skip_empty_sections` | bool | `true` | 丢弃仅有标题无正文的分块 |
| `render_headings` | bool | `true` | 在分块正文中渲染公共标题前缀 |
| `block_configs` | object | `null` | 按块类型配置 |
| `tokenizer` | string | `"simple"` | `simple` 或 `tiktoken` |
| `splitter` | string | `"recursive"` | `recursive` 或 `section` |

`block_configs` 示例：

```json
{
  "table": {
    "isolated": true,
    "max_tokens": 500,
    "repeat_header": false
  },
  "html_table": {
    "repeat_header": false
  }
}
```

#### 响应

```json
{
  "document": "guide.md",
  "chunk_count": 1,
  "chunks": [
    {
      "chunk_id": "chunk-001",
      "chunk_type": "heading",
      "body": "# Hello\n\nWorld",
      "token_count": 8,
      "estimated_token_count": 8,
      "headings": [[1, "Hello"]],
      "section_level": 1,
      "document_title": "guide.md",
      "document_path": null,
      "start_line": 1,
      "end_line": 3
    }
  ]
}
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

打开 <http://localhost:9612>。

## 切分策略

| 策略 | 注册名 | 行为 |
| --- | --- | --- |
| **Recursive** | `recursive`（默认） | 结构优先、预算感知；相邻同级章节会在预算允许时合并进同一个分块。 |
| **Section** | `section` | 一个标题章节对应一个分块，子章节则作为单独分块。 |

递归切分顺序：

1. 如果整篇文档已经在预算内，则保持为一个分块
2. 先按标题章节切分
3. 超大章节再按块边界切分
4. 最后回退到段落 → 行 → 句子 → 单词 → 硬切分

> [!IMPORTANT]
> 代码块默认保持完整，即使超过 `max_tokens`；如需允许拆分特定块类型，请使用 `BaseParams(split=True)`。

## 解析覆盖范围

**块级结构：**

Markdown：ATX 标题 · Setext 标题 · 段落 · 引用块 · 有序/无序列表 · 表格 · 围栏代码 · 缩进代码 · HTML 块 · 链接引用定义 · YAML front matter · 数学块（`$$...$$`）· 方括号数学块（`\[...\]`）· 带编号数学 · 插件生成的块

HTML：标题 · 段落 · 引用块 · 列表 · 代码块 · 作为 `html_table` 的表格 · 文档标题和 meta 标签

**行内结构**（在标题和段落中）：

文本 · 链接 · 图片 · 自动链接 · 行内代码 · 强调 · 加粗强调 · 删除线 · 行内 HTML · 换行 · 行内数学（`$...$`）· 方括号行内数学（`\(...\)`）· 脚注引用 · 插件生成的行内元素

**其他保留：**

- 标题文本的行内节点
- `DocumentAST.reference_definitions` 中的引用链接定义
- 标题和块的源码行范围

## 架构

```text
src/lumberjack/
├── __init__.py              # 公共 API 重新导出
├── formats.py               # 输入格式检测和源内容读取辅助函数
├── lumber.py                # 公共 lumber() 实现
├── cli.py                   # CLI 入口（lumber）
├── core/
│   ├── models.py            # 数据模型（Chunk、BaseParams、SplitOptions、...）
│   ├── protocols.py         # 协议接口
│   ├── tokenizers.py        # 简单字符 & tiktoken 分词器
│   ├── block.py             # 超长块切分 + 块配置解析辅助
│   ├── options.py           # 切分选项和块配置辅助函数
│   ├── utils.py             # Markdown 渲染辅助函数
│   ├── visitor.py           # AST 遍历访问器
│   ├── splitters/           # 递归 & 章节切分器
│   │   ├── base.py          # 共享切分器辅助逻辑
│   │   ├── recursive.py     # RecursiveSplitter
│   │   ├── section.py       # SectionSplitter
│   │   └── registry.py      # 切分器注册表/工厂
│   └── parsers/             # 格式解析器：原始输入 -> DocumentAST
│       ├── markdown/
│       │   ├── parser.py    # MarkdownItParser（markdown-it-py 后端）
│       │   └── plugins/     # 自定义 markdown-it 插件（方括号数学）
│       ├── html/
│       │   ├── parser.py    # HTMLParser（stdlib html.parser 后端）
│       │   └── table_parser.py  # HTML 表格抽取和行解析
│       └── docx/
│           └── parser.py    # DocxParser（python-docx 后端）
└── web/
    ├── app.py               # FastAPI 应用
    ├── routes.py            # API 端点
    └── __main__.py          # 服务器入口（lumberjack-serve）
```

## 开发

本项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

```bash
# 克隆并安装全部依赖
git clone https://github.com/tianleG/lumberjack.git
cd lumberjack
uv sync --group dev --group test --extra tokenizers --extra docx

# 运行测试
uv run pytest

# 代码检查和格式化（ruff）
uv run ruff check --fix
uv run ruff format

# 类型检查（ty）
uv run ty check
```

> [!TIP]
> 本项目使用 [ruff](https://docs.astral.sh/ruff/) 进行代码检查与格式化，使用 [ty](https://docs.astral.sh/ty/) 进行类型检查。

## 许可证

[MIT](LICENSE)

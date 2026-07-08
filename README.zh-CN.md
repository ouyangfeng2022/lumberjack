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
pip install "lumberjack[tokenizers]"   # 基于 tiktoken / transformers 的模型 token 计数
pip install "lumberjack[docx]"         # DOCX 文档支持
pip install "lumberjack[web]"          # FastAPI Web 服务器 + UI
pip install "lumberjack[all]"          # 包含全部功能
```

> [!NOTE]
> 需要 Python 3.10+。

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
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    render_headings=True,      # False：从 body 中去掉祖先标题面包屑
    tokenizer="approx",        # "approx" | "tiktoken" | "transformers"
    splitter="recursive",      # "recursive" | "section" | "section-flat"
)
```

计数策略是 splitter 类的固有属性，与 tokenizer 无关。默认的 `recursive`
和 `section` splitter 是**精确法**：每次预算决策都完整重计渲染候选文本
（`token_count == estimated_token_count`）。`incremental-recursive` 和
`incremental-section` 变体则一次性预测量整棵树，使用累加估算值 + 8 字符
尾窗近似 entry 之间的 separator——对重型 tokenizer 更快，代价是
`estimated_token_count` 会与权威的 `token_count`（finalization 时的完整
重计）略有偏差。任何 tokenizer 都可以配合任何 splitter 使用。

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
| `headings` | `(level, title)` 元组 —— 祖先标题面包屑 |
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

#### Markdown Parser 自定义插件

`MarkdownItParser` 通过 `plugins` 参数接收普通的 `markdown-it-py` 插件。如果插件只是改变已有 Markdown 结构，例如 task list 仍然解析成 list item，只是在行内增加 checkbox HTML，就不需要额外声明：

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parsers.markdown import MarkdownItParser

parser = MarkdownItParser(plugins=(tasklists_plugin,))
document = parser.parse("- [x] done", document_title="tasks.md")
```

如果插件会产生新的块级 token type，需要用 `MarkdownBlockSpec` 声明这些 token type 对应的 lumberjack 块类型。解析器会把自定义类型合并进 `parser.block_kinds`，后续 `resolve_block_options()` 和 splitter 校验都应使用这个实例上的 `block_kinds`。

下面是完整示例：使用 `mdit_py_plugins.container.container_plugin` 把自定义 callout 容器解析成一等公民的 `callout` 块类型，并在切分时让它单独成块：

```python
from mdit_py_plugins.container import container_plugin

from lumberjack.core.models import BaseParams, MarkdownBlock, SplitOptions
from lumberjack.core.options import resolve_block_options
from lumberjack.core.parsers.markdown import MarkdownBlockContext, MarkdownBlockSpec
from lumberjack.core.parsers.markdown import MarkdownItParser
from lumberjack.core.splitters import RecursiveSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer


def callout_block(context: MarkdownBlockContext) -> tuple[MarkdownBlock | None, int]:
    close_index = context.parser.find_matching_close(context.tokens, context.index)
    children = context.parser.parse_child_blocks(
        context.tokens,
        context.index + 1,
        close_index,
        context.source_lines,
    )
    body = "\n\n".join(child.text for child in children if child.text)
    return (
        MarkdownBlock(
            kind="callout",
            text=body,
            start_line=context.token.map[0] + 1 if context.token.map else None,
            end_line=context.token.map[1] if context.token.map else None,
            children=children,
            attrs={
                "source_token_type": context.token.type,
                "info": context.token.info.strip(),
            },
        ),
        close_index + 1,
    )


parser = MarkdownItParser(
    plugins=(lambda md: container_plugin(md, name="callout"),),
    block_specs=(
        MarkdownBlockSpec(
            kind="callout",
            token_types=("container_callout_open",),
            handler=callout_block,
        ),
    ),
)

markdown_text = """# Guide

::: callout note
Remember to configure custom block kinds before splitting.
:::
"""

document = parser.parse(markdown_text, document_title="guide.md")
options = SplitOptions(
    max_tokens=1200,
    block_options=resolve_block_options(
        parser.block_kinds,
        {"callout": BaseParams(isolated=True, max_tokens=400)},
    ),
)
chunks = RecursiveSplitter(
    tokenizer=SimpleCharTokenizer(),
    options=options,
).split(document)
```

`MarkdownBlockSpec` 规则：

- `kind` 会规范化为小写，并成为 `MarkdownBlock.kind`。
- `token_types` 必须是自定义 markdown-it token type 字符串组成的可迭代对象，例如 `("container_callout_open",)`。
- `handler` 可选。不提供时，lumberjack 会捕获源码片段；如果是容器类 token，还会递归解析子块。
- handler 接收 `MarkdownBlockContext`，返回 `(block, next_index)`；如果该 token 应被跳过，可以让 `block` 返回 `None`。
- handler 构造的 block 必须使用声明的 `kind`；返回其他 kind 会抛出 `ValueError`。
- `paragraph_open`、`fence`、`table_open`、`html_block` 等内置 Markdown token type 由内部逻辑处理，不能通过 `MarkdownBlockSpec` 重映射。

带插件的解析器应使用 `parser.block_kinds` 校验配置，而不是使用 `MarkdownItParser.default_block_kinds`。后者只包含 Markdown 内置块类型；实例上的 `block_kinds` 还包含 `callout` 这类插件提供的类型。

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
| `--merge-below-ratio` | `0.125` | 尾部碎片合并阈值，max-tokens 的比例（0 禁用） |
| `--tokenizer` | `approx` | `approx`、`tiktoken` 或 `transformers` |
| `--splitter` | `recursive` | `recursive`、`section`、`section-flat`、`exact-recursive`、`incremental-recursive`、`exact-section`、`incremental-section`、`exact-section-flat`、`incremental-section-flat` |
| `--no-render-headings` | off | 从 `body` 中省略祖先标题面包屑（参见[是否渲染标题](#是否渲染标题render_headings)） |
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
| `merge_below_ratio` | float | `0.125` | 尾部碎片合并阈值，max-tokens 的比例（0 禁用） |
| `skip_empty_sections` | bool | `true` | 丢弃仅有标题无正文的分块 |
| `render_headings` | bool | `true` | 为 `false` 时从 `body` 中省略祖先标题面包屑（参见[是否渲染标题](#是否渲染标题render_headings)） |
| `block_configs` | object | `null` | 按块类型配置 |
| `tokenizer` | string | `"approx"` | `approx`、`tiktoken` 或 `transformers` |
| `splitter` | string | `"recursive"` | `recursive`、`section`、`section-flat`、`exact-recursive`、`incremental-recursive`、`exact-section`、`incremental-section`、`exact-section-flat`、`incremental-section-flat` |

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
      "headings": [],
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
| **Section** | `section` | 子树优先：整棵子树（含后代）在预算内且不含独立块时合并为单分块；否则每个标题章节的直接正文一个分块（含尾部碎片合并）。 |
| **Section Flat** | `section-flat` | 每个标题章节的直接正文独立成块、递归子节点；不做子树合并、不做尾部碎片合并。 |
| **Incremental Section** | `incremental-section` | 同 Section 的拓扑结构，使用累加估算路径。 |
| **Incremental Section Flat** | `incremental-section-flat` | 同 Section Flat 的拓扑结构，使用累加估算路径。 |

递归切分顺序：

1. 如果整篇文档已经在预算内，则保持为一个分块
2. 先按标题章节切分
3. 超大章节再按块边界切分
4. 最后回退到段落 → 行 → 句子 → 单词 → 硬切分

> [!IMPORTANT]
> 代码块默认保持完整，即使超过 `max_tokens`；如需允许拆分特定块类型，请使用 `BaseParams(split=True)`。

### 是否渲染标题（`render_headings`）

默认情况下，每个分块渲染出的 `body` 都会以祖先标题面包屑开头，随后保留该分块自身的标题（例如一个 H2 leaf 会渲染为 `# Title\n\n## Section`）。`Chunk.headings` 只保存祖先标题。设置 `render_headings=False` 可以从 `body` 中省略祖先标题面包屑；分块自身标题和 chunk 内部的相对标题仍会渲染。两个切分器都按渲染结果预算：

| 切分器 | body 行为 | 预算行为 |
| --- | --- | --- |
| **Section** | 省略祖先标题面包屑；该 section 自身标题仍会渲染 | **按渲染口径预算**：原先预留给祖先标题的预算会归还给渲染内容，因此 `max_tokens` 会严格约束实际渲染的 body（`token_count` 即实测 body tokens）。 |
| **Recursive**（默认） | 省略祖先标题面包屑；chunk 自身标题和 chunk *内部*的相对标题（例如合并 chunk 中的兄弟 `###` 标题）仍会渲染 | **按渲染口径预算**：切分预算只会因为隐藏祖先标题而增长。有祖先标题的分块，其切分计划（分块数量、边界）可能不同于 `render_headings=True`。 |

> [!NOTE]
> 两个切分器都会在 draft 层保留标题 token，让合并算术保持自洽——当两个 chunk 合并后共享的祖先前缀发生变化，被挤出的标题 token 会回到 body 中，作为仍会渲染的自身标题或内部相对标题。切分预算判断与运行中的 `estimated_token_count` 都按渲染口径处理，因此估算值始终贴合实际渲染出的 `body`（由于 separator 近似，它与 `token_count` 可能相差一两个 token）。

```python
# 两个切分器：按渲染口径预算（body 能填满 max_tokens）
lumber(doc, splitter="section", render_headings=False, max_tokens=1000)
lumber(doc, splitter="recursive", render_headings=False, max_tokens=1000)
```

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
│   ├── tokenizers.py        # 估算、tiktoken 和 transformers 分词器
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

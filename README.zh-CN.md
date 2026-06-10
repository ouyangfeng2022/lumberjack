<p align="center">
  <img src="assets/logo.png" alt="lumberjack" width="200">
</p>

<h1 align="center">lumberjack</h1>

<p align="center">
  <strong>面向 RAG 预处理的结构感知 Markdown 分割器</strong>
</p>

<p align="center">
  按文档结构而非固定文本窗口切分 Markdown。
  保留标题层级、块完整性和行内语义。
</p>

<p align="center">
  <a href="README.md">English</a>
</p>

---

## 为什么选择 lumberjack？

朴素文本分割器在任意字符边界处打断 Markdown — 切断代码块、从表格中间拆行、丢失标题上下文。**lumberjack** 把文档当作一棵树，而非一段字符串：

- **结构优先切分** — 按标题章节和块边界拆分
- **预算感知合并** — 同级相邻章节在预算允许时自动合并
- **块完整性** — 代码块、表格和数学公式默认保持完整
- **标题上下文保留** — 每个分块携带完整的标题面包屑路径
- **多种接口** — Python API、CLI 和 Web UI 开箱即用

核心管线：

```text
Markdown 文本 → 解析器 token → DocumentAST → 切分器 → Chunk[]
```

## 安装

```bash
pip install lumberjack
```

可选扩展：

```bash
pip install "lumberjack[tokenizers]"   # 基于 tiktoken 的模型 token 计数
pip install "lumberjack[web]"          # FastAPI Web 服务器 + UI
pip install "lumberjack[all]"          # 全部
```

> [!NOTE]
> 需要 Python 3.13+。

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
lumber document.md --max-tokens 1200 --format json
```

### Web UI

```bash
pip install "lumberjack[web]"
lumberjack-serve
```

打开 <http://localhost:9612> — 粘贴文本或上传 `.md` 文件，配置选项，可视化查看分块结果。

## 使用说明

### Python API

公共 API 是一个函数 — [`lumber()`](src/lumberjack/__init__.py)：

```python
from lumberjack import lumber
from lumberjack.core.models import BlockConfig

# 完整选项
chunks = lumber(
    markdown_text,
    document_title="guide.md",
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_tokens=50,
    overlap_tokens=0,
    merge_small_chunks=True,
    skip_empty_sections=True,
    recursive_split=False,
    tokenizer="simple",        # "simple" | "tiktoken"
    parser="default",          # "default" | "markdown-it"
    splitter="recursive",      # "recursive" | "section"
)
```

每个返回的 `Chunk` 包含：

| 字段                       | 说明                                                                  |
| -------------------------- | --------------------------------------------------------------------- |
| `chunk_id`                 | 唯一标识符                                                            |
| `chunk_type`               | 来源块类型（`"heading"`、`"paragraph"`、`"code_fence"`、...）         |
| `body`                     | 包含标题面包屑的渲染文本                                              |
| `token_count`              | 从最终正文计算的 token 数                                             |
| `estimated_token_count`    | 切分时使用的预算估算值                                                |
| `headings`                 | `(level, title)` 元组 — 标题面包屑路径                                |
| `section_level`            | 该分块中最深的标题层级                                                |
| `document_title`           | 从 front matter 或首个 H1 解析的文档标题                              |
| `start_line` / `end_line`  | 源文件中的 1 起始行范围                                               |

#### 按块类型配置

控制各块类型的切分和合并行为：

```python
from lumberjack import lumber
from lumberjack.core.models import BlockConfig

chunks = lumber(
    markdown_text,
    block_options={
        # 表格：独立分块、禁止拆分、500 token 预算
        "table": BlockConfig(isolated=True, split=False, max_tokens=500),
        # 代码块：超长时保持完整
        "code_fence": BlockConfig(split=False),
        # 段落：自定义预算
        "paragraph": BlockConfig(max_tokens=800),
    },
)
```

`BlockConfig` 字段：

- **`isolated`** (`bool`) — 作为独立分块输出，不与相邻内容合并
- **`split`** (`bool`) — 允许拆分超长块
- **`max_tokens`** (`int | None`) — 该块类型的预算覆盖值；`None` 使用全局 `max_tokens`

可用块类型：`paragraph`、`blockquote`、`list`、`list_item`、`table`、`code_block`、`code_fence`、`html_block`、`front_matter`、`math_block`、`math_block_eqno`。

> [!TIP]
> `block_options` 也接受普通字典：`{"table": {"isolated": True, "split": False}}`。

#### 自定义解析器插件

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parser import MarkdownItParser
from lumberjack import lumber

chunks = lumber(
    markdown_text,
    parser=MarkdownItParser(plugins=(tasklists_plugin,)),
)
```

### CLI

```bash
lumber <input> [options]
```

| 选项                       | 默认值       | 说明                                            |
| -------------------------- | ------------ | ----------------------------------------------- |
| `input`                    | —            | Markdown 文件路径                               |
| `-o`, `--output`           | 标准输出     | 将输出写入文件                                  |
| `-f`, `--format`           | `json`       | 输出格式：`json` 或 `markdown`                  |
| `--max-tokens`             | `1200`       | 最大分块 token 预算                             |
| `--ideal-max-tokens-ratio` | `0.8`        | 优先切分预算比例                                |
| `--merge-below-tokens`     | `50`         | 小分块合并软阈值                                |
| `--overlap-tokens`         | `0`          | 文本回退切分的 token 重叠量                     |
| `--tokenizer`              | `simple`     | `simple` 或 `tiktoken`                          |
| `--splitter`               | `recursive`  | `recursive` 或 `section`                        |
| `--recursive-split`        | 关闭         | 启用 section 切分器的块/文本回退                |
| `--block-config`           | —            | 按块类型配置（可重复指定）                      |
| `--disable-lheading`       | 关闭         | 禁用 Setext 标题解析                            |

`--block-config` 语法：`KIND[:isolated][:nosplit][:TOKENS]`

```bash
# 表格独立、禁止拆分、500 token 预算
lumber doc.md --block-config table:isolated:nosplit:500

# 代码块超长时保持完整
lumber doc.md --block-config code_fence:nosplit

# 多个块类型配置
lumber doc.md --block-config table:isolated --block-config code_fence:nosplit
```

**JSON 输出** 包含 `document`、`chunk_count` 和带完整元数据的 `chunks` 数组。

**Markdown 输出** 使用 HTML 注释分隔各分块：

```markdown
<!-- chunk 1 tokens=42 -->
## Getting Started

Install with pip...

<!-- chunk 2 tokens=87 -->
## Usage

...
```

### Web API

启动服务器：

```bash
lumberjack-serve --host 127.0.0.1 --port 9612
```

#### `POST /lumber/api/split/text`

```bash
curl -X POST http://localhost:9612/lumber/api/split/text \
  -H "Content-Type: application/json" \
  -d '{"text": "# Hello\n\nWorld", "max_tokens": 500}'
```

#### `POST /lumber/api/split/file`

```bash
curl -X POST http://localhost:9612/lumber/api/split/file \
  -F "file=@guide.md" \
  -F "max_tokens=500" \
  -F "splitter=section"
```

#### Web API 选项

两个接口接受相同的选项：

| 字段                       | 类型    | 默认值        | 说明                                   |
| -------------------------- | ------- | ------------- | -------------------------------------- |
| `max_tokens`               | int     | `1200`        | 最大分块 token 预算                    |
| `ideal_max_tokens_ratio`   | float   | `0.8`         | 优先切分预算比例                       |
| `merge_below_tokens`       | int     | `50`          | 小分块合并软阈值                       |
| `overlap_tokens`           | int     | `0`           | 文本回退切分的 token 重叠量            |
| `merge_small_chunks`       | bool    | `true`        | 合并相邻小分块                         |
| `skip_empty_sections`      | bool    | `true`        | 丢弃仅有标题无正文的分块               |
| `recursive_split`          | bool    | `false`       | 启用 section 切分器的块/文本回退       |
| `block_configs`            | object  | `null`        | 按块类型配置                           |
| `disable_lheading`         | bool    | `false`       | 禁用 Setext 标题解析                   |
| `tokenizer`                | string  | `"simple"`    | `simple` 或 `tiktoken`                 |
| `splitter`                 | string  | `"recursive"` | `recursive` 或 `section`               |

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

| 策略         | 注册名               | 行为                                                                         |
| ------------ | -------------------- | ---------------------------------------------------------------------------- |
| **Recursive** | `recursive`（默认）  | 结构优先、预算感知。同级相邻章节在预算允许时合并进同一个分块。               |
| **Section**  | `section`            | 按标题章节直接正文输出一个分块。子章节独立输出为单独分块。                   |

递归切分顺序：

1. 如果整篇文档已在预算内，保持为一个分块
2. 否则按标题章节切分
3. 超大章节按块边界切分
4. 回退到段落 → 行 → 句子 → 单词 → 硬切分

> [!IMPORTANT]
> 代码块默认保持完整，即使超过 `max_tokens`。使用 `BlockConfig(split=True)` 可允许拆分指定块类型。

## 解析覆盖范围

**块级结构：**

ATX 标题 · Setext 标题 · 段落 · 引用块 · 有序/无序列表 · 表格 · 围栏代码 · 缩进代码 · HTML 块 · 链接引用定义 · YAML front matter · 数学块（`$$...$$`）· 方括号数学块（`\[...\]`）· 带编号数学 · 插件生成的块

**行内结构**（在标题和段落中）：

文本 · 链接 · 图片 · 自动链接 · 行内代码 · 强调 · 加粗强调 · 删除线 · 行内 HTML · 换行 · 行内数学（`$...$`）· 方括号行内数学（`\(...\)`）· 脚注引用 · 插件生成的行内元素

**其他保留：**

- 标题文本的行内节点
- `DocumentAST.reference_definitions` 中的引用链接定义
- 标题和块的源码行范围

## 架构

```text
src/lumberjack/
├── __init__.py              # 公共 API（lumber 函数）
├── cli.py                   # CLI 入口（lumber）
├── core/
│   ├── parser.py            # Markdown 解析器（markdown-it-py 后端）
│   ├── splitter.py          # 递归 & 章节切分器
│   ├── tokenizers.py        # 简单字符 & tiktoken 分词器
│   ├── models.py            # 数据模型（Chunk、BlockConfig、SplitOptions、...）
│   ├── protocols.py         # 协议接口
│   ├── block_config.py      # 块配置解析辅助
│   ├── plugins/             # 自定义 markdown-it 插件（方括号数学）
│   ├── utils.py             # Markdown 渲染辅助函数
│   └── visitor.py           # 访问器模式钩子
└── web/
    ├── app.py               # FastAPI 应用
    ├── routes.py            # API 端点
    └── __main__.py          # 服务器入口（lumberjack-serve）
```

## 开发

```bash
# 安装开发、测试和分词器依赖
uv sync --group dev --group test --extra tokenizers

# 运行测试
uv run pytest

# 代码检查和格式化
uv run ruff check --fix
uv run ruff format
```

## 许可证

[MIT](LICENSE)

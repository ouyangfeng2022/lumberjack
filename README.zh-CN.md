# lumberjack

[English](README.md)

`lumberjack` 是一个面向长文档检索和 RAG 预处理的结构感知 Markdown 分割器。
它按文档结构而非固定文本窗口进行切分。

解析器使用 [`markdown-it-py`](https://markdown-it-py.readthedocs.io/en/latest/) 的 `gfm-like` 模式，
将 token 流归一化为 lumberjack 内部数据模型后再进行分块。

## 功能概述

核心管线：

```text
Markdown 文本 -> 解析器 token -> DocumentAST -> MarkdownSplitter -> Chunk[]
```

当前行为：

- 构建标题树，并将块节点归属到对应章节
- 保留段落、列表、引用块、代码块、HTML 块、分隔线等块级结构
- 捕获标题和段落中的行内节点
- 在文档模型中跟踪链接引用定义
- 尽可能保留标题和块的源码行范围
- 按整篇文档 -> 章节树 -> 块/文本 回退 的顺序切分
- 围栏代码块即使超出 token 预算也保持完整

## 安装

运行时安装：

```bash
uv sync
```

开发安装（含测试、代码检查和可选的 `tiktoken` 支持）：

```bash
uv sync --group dev --group test --extra tokenizers
```

## 命令行

基本用法：

```bash
uv run lumber path/to/file.md --max-tokens 1200 --min-tokens 50 --format json
```

查看帮助：

```bash
uv run lumber --help
```

当前支持的命令行选项：

- `input`：Markdown 文件路径
- `--output`：将输出写入文件而非标准输出
- `--format {json,markdown}`：输出格式，默认 `json`
- `--tokenizer {simple,tiktoken}`：token 计数策略，默认 `simple`
- `--parser {default,markdown-it}`：命令行暴露的解析器选择器
- `--max-tokens`：最大分块预算，默认 `1200`
- `--min-tokens`：小分块合并阈值，默认 `50`
- `--overlap-tokens`：仅在文本回退切分时使用的可选 token 重叠量，默认 `0`
- `--retain-headings`：在渲染的分块文本中包含标题上下文
- `--split-oversized-block <kind>`：允许切分超大的 `list`、`code_block`、`code_fence`、`table` 等受支持的块类型

解析器说明：

- `default` 和 `markdown-it` 均解析为 `markdown-it-py` 解析器
- `MarkdownItParser` 也支持通过构造函数传入 `markdown-it-py` 插件

### JSON 输出

JSON 命令行输出包含：

- `document`
- `chunk_count`
- `chunks`

每个分块从 `Chunk` 数据类序列化，包含以下字段：

- `chunk_id`
- `chunk_type`
- `text`
- `body`
- `token_count`
- `headings`
- `section_level`
- `document_title`
- `document_path`
- `start_line`
- `end_line`

### Markdown 输出

`--format markdown` 将每个分块渲染为 Markdown，并在前面添加显示分块索引和 token 数的 HTML 注释。

## Python API

公共 API 位于 [`src/lumberjack/api.py`](src/lumberjack/api.py)。

```python
from lumberjack import lumber

chunks = lumber(
    markdown_text,
    document_title="guide.md",
    max_tokens=1200,
    min_tokens=50,
    overlap_tokens=0,
    retain_headings=True,
    merge_small_chunks=True,
    split_oversized_blocks=("list", "code_fence"),
    tokenizer="simple",
)

from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parser import MarkdownItParser

plugin_chunks = lumber(
    markdown_text,
    document_title="tasks.md",
    parser=MarkdownItParser(plugins=(tasklists_plugin,)),
)
```

从 [`src/lumberjack/__init__.py`](src/lumberjack/__init__.py) 导出的公共类型：

只导出 `lumber`。高级解析器、切分器、分词器和模型类型仍可从内部模块导入。

## 批量处理

`script/download_and_split.py` 脚本从 Hugging Face 下载 Markdown 数据集，并将每个文档通过相同的 lumberjack 管线进行切分。

### 预设

内置预设配置了数据集名称、子集、字段映射以及是否过滤 Markdown 内容：

| 预设 | 数据集 | 说明 |
|---|---|---|
| `open-markdown` | [`open-index/open-markdown`](https://huggingface.co/datasets/open-index/open-markdown) | 纯 Markdown，无需过滤 |
| `fineweb` | [`HuggingFaceFW/fineweb`](https://huggingface.co/datasets/HuggingFaceFW/fineweb) | 通用网页文本，过滤 Markdown 内容 |

### 用法

```bash
# 安装额外的数据集依赖
uv sync --group scripts

# open-markdown 预设（流式）
uv run script/download_and_split.py --preset open-markdown --max-samples 100

# 从本地 parquet 文件加载 open-markdown
uv run script/download_and_split.py --preset open-markdown --local-dir ./open-index/

# FineWeb 预设
uv run script/download_and_split.py --preset fineweb

# 任意 Hugging Face 数据集
uv run script/download_and_split.py --dataset open-index/open-markdown --subset CC-MAIN-2026-17

# 自定义字段映射
uv run script/download_and_split.py --dataset my/repo --text-field content --title-field url
```

### 选项

- `--preset {open-markdown,fineweb}`：使用内置预设
- `--dataset`：Hugging Face 数据集名称（与 `--preset` 互斥）
- `--subset`：数据集配置/子集名称
- `--split`：数据集划分，默认 `train`
- `--max-samples`：最大处理样本数，默认 `50`
- `--max-tokens` / `--min-tokens`：传递给 lumberjack 的分块大小控制参数
- `--filter-markdown` / `--no-filter-markdown`：启用或禁用 Markdown 内容检测
- `--local-dir`：从本地 parquet 文件加载而非从 Hugging Face 流式加载
- `--text-field`：覆盖自动检测的文本列名
- `--title-field`：覆盖自动检测的标题列名
- `--output`：输出根目录，默认 `output/`

### 输出结构

```text
output/
└── open_index_open_markdown/
    ├── metadata.json
    ├── 0000_my_page.json
    ├── 0001_another_page.json
    └── ...
```

每个 JSON 文件包含：

```json
{
  "source_title": "my_page",
  "source_length": 3240,
  "chunk_count": 3,
  "chunks": [
    {
      "chunk_id": "...",
      "chunk_type": "paragraph",
      "body": "...",
      "token_count": 1100,
      "headings": [[1, "引言"]],
      ...
    }
  ]
}
```

`metadata.json` 记录数据集名称、子集、切分选项和处理统计信息。

## 内部数据模型

[`src/lumberjack/models.py`](src/lumberjack/models.py) 中的主要数据类：

- `MarkdownInline`：归一化的行内节点，含 `kind`、`text`、`children` 和 `attrs`
- `MarkdownBlock`：块级节点，含渲染文本、嵌套块、行内子节点、行范围和属性
- `SectionNode`：标题树节点，含 `path`、`blocks`、`children`、`start_line` 和 `title_inlines`
- `DocumentAST`：根文档对象，含 `source`、`metadata` 和 `reference_definitions`
- `Chunk`：最终的分块单元，含类型、可见文本、正文文本、标题路径和源元数据

## 解析覆盖范围

当前解析器归一化以下块级结构：

- ATX 标题
- Setext 标题
- 段落
- 引用块
- 有序和无序列表
- 表格
- 围栏代码块
- 缩进代码块
- HTML 块
- 分隔线
- 链接引用定义元数据

当前解析器在标题和段落中捕获以下行内结构：

- 文本
- 链接
- 图片
- 自动链接
- 行内代码
- 强调
- 加粗强调
- 删除线
- 行内 HTML
- 软换行和硬换行

解析器还保留：

- 标题标题的行内节点
- `DocumentAST.reference_definitions` 中的引用链接定义
- 标题和渲染块的源码行范围

解析器行为说明：

- `markdown-it-py` 不会将引用定义行作为可见的 `link_reference_definition` 块发出
- 插件生成的块 token 会保留为插件特定的块类型或原始 markdown 回退块
- 插件生成的行内 token 在可能时予以保留，未知行内容器会保持其子文本完整

## 切分策略

切分遵循结构优先、预算感知的原则：

1. 如果整篇文档已在预算内，则保持为一个分块。
2. 否则按标题章节切分。
3. 如果章节过大，则按块边界切分。
4. 如果块仍然过大，则回退到段落、行、句子、单词，最后硬切分。

重要细节：

- 当 `retain_headings=True` 时，标题上下文保留在 `Chunk.text` 中
- 当同级章节合并为一个分块时，共享的父标题会去重
- `Chunk.body` 不包含已由 `Chunk.headings` 表示的公共标题前缀
- 小分块合并仅发生在具有相同标题路径的相邻分块之间
- 可选重叠仅在单个超大块必须按段落、行、句子、单词或硬边界切分时应用
- 超大列表和代码块默认保持完整，但可通过 `split_oversized_blocks` 设为可切分
- 长的 URL 样式文本被视为不可切分，不会跨分块硬切分

## 分词器

[`src/lumberjack/core/tokenizers.py`](src/lumberjack/core/tokenizers.py) 中可用的分词器实现：

- `SimpleCharTokenizer`：按字符计数
- `TiktokenTokenizer`：通过 `tiktoken` 按模型 token 计数

如果未安装 `tiktoken` 但请求了 `TiktokenTokenizer`，库会抛出运行时错误并提供安装指引。

## 仓库结构

```text
src/lumberjack/base/      协议接口
src/lumberjack/core/      解析器、切分器、分词器和访问器实现
src/lumberjack/api.py     公共 Python API
src/lumberjack/models.py  内部数据模型
src/lumberjack/utils.py   Markdown 渲染辅助函数
src/lumberjack/main.py    命令行编排
script/                   批量处理脚本（数据集下载与切分）
tests/                    解析器、切分器和 API 测试
docs/                     架构和开发笔记
```

## 测试

运行完整测试套件：

```bash
uv run pytest
```

运行单个模块：

```bash
uv run pytest tests/test_parser.py
uv run pytest tests/test_splitter.py
uv run pytest tests/test_api.py
```

代码检查和格式化：

```bash
uv run ruff check --fix
uv run ruff format
```

## 当前限制

`lumberjack` 有意聚焦于语义切分，而非完美的 Markdown 往返转换。

当前限制和说明：

- 仅支持 Markdown；本包不计划支持 PDF、HTML 或 DOCX 的导入管线
- 解析器面向 GFM 风格的语法，而非严格的多后端兼容层
- 命令行解析器选择器仅作为显式访问 markdown-it 实现的途径而保留

## 状态

当前仓库已包含：

- 解析器测试：标题树构建、代码围栏标题安全、CommonMark 块/行内归一化和行范围保留
- 切分器测试：整篇文档适配、递归章节下降、标题去重、隐藏标题渲染和分块正文行为
- API 测试：文件/文本一致性和元数据传播

这使项目成为章节感知 Markdown 分块的坚实基础，同时为未来更丰富的元数据和更多 Markdown 方言支持留有空间。

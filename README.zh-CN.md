# lumberjack

[English](README.md)

`lumberjack` 是一个面向长文档检索和 RAG 预处理的结构感知 Markdown 分割器。
它按文档结构而非固定文本窗口进行切分。

解析器使用 [`markdown-it-py`](https://markdown-it-py.readthedocs.io/en/latest/) 的 `gfm-like` 模式，
内置 LaTeX 数学（dollarmath 和方括号语法）、YAML front matter 以及自定义方括号数学插件。
将 token 流归一化为 lumberjack 内部数据模型后再进行分块。

## 功能概述

核心管线：

```text
Markdown 文本 -> 解析器 token -> DocumentAST -> splitter -> Chunk[]
```

当前行为：

- 构建标题树，并将块节点归属到对应章节
- 解析 YAML front matter；按用户输入、front matter 或首个 H1 解析文档标题
- 保留段落、列表、引用块、代码块、HTML 块、分隔线、数学块等块级结构
- 捕获标题和段落中的行内节点，包括行内数学和脚注引用
- 在文档模型中跟踪链接引用定义
- 尽可能保留标题和块的源码行范围
- 按整篇文档 -> 章节树 -> 块/文本 回退 的顺序切分
- 围栏代码块默认保持完整，即使超出 token 预算
- 将 front matter 作为第一个分块隔离；跳过仅有标题无正文的空章节

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
uv run lumber path/to/file.md --max-tokens 1200 --merge-below-tokens 50 --format json
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
- `--splitter {recursive,section}`：切分策略，默认 `recursive`
- `--max-tokens`：最大分块预算，默认 `1200`
- `--merge-below-tokens`：小分块合并软阈值，默认 `50`
- `--overlap-tokens`：仅在文本回退切分时使用的可选 token 重叠量，默认 `0`
- `--recursive-split`：使用 `--splitter section` 时递归拆分超大的章节直接正文
- `--retain-headings`：在渲染的分块文本中包含标题上下文
- `--no-include-common-headings`：排除分块正文中的公共标题前缀（需配合 `--retain-headings` 使用）
- `--no-isolate-front-matter`：不将 front matter 作为第一个分块隔离
- `--split-oversized-block <kind>`：允许切分超大的 `list`、`code_block`、`code_fence`、`table` 等受支持的块类型；可重复指定以启用多种类型
- `--disable-lheading`：禁用 Setext 标题解析

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
- `estimated_token_count`
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
    merge_below_tokens=50,
    overlap_tokens=0,
    retain_headings=True,
    include_common_headings=True,
    merge_small_chunks=True,
    isolate_front_matter=True,
    skip_empty_sections=True,
    split_oversized_blocks=("paragraph", "blockquote", "html_block"),
    recursive_split=False,
    disable_lheading=False,
    tokenizer="simple",
    parser="default",
    splitter="recursive",
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

## 内部数据模型

[`src/lumberjack/models.py`](src/lumberjack/models.py) 中的主要数据类：

- `MarkdownInline`：归一化的行内节点，含 `kind`、`text`、`children` 和 `attrs`
- `MarkdownBlock`：块级节点，含渲染文本、嵌套块、行内子节点、行范围和属性
- `SectionNode`：标题树节点，含 `path`、`blocks`、`children`、`start_line`、`title_inlines` 和 `index`
- `DocumentAST`：根文档对象，含 `source`、`metadata` 和 `reference_definitions`；标题从 front matter 或首个 H1 解析
- `Chunk`：最终的分块单元，含 `chunk_id`、`chunk_type`、可见文本（`body`）、标题路径、token 计数和源元数据

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
- 链接引用定义
- YAML front matter
- 数学块（`$$...$$`）
- 带编号数学块
- 方括号数学块（`\[...\]`）
- 带编号方括号数学块（`\[...\](label)`）
- 插件生成的块保留为插件特定的块类型

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
- 行内数学（`$...$`）
- 方括号行内数学（`\(...\)`）
- 脚注引用和锚点
- 插件生成的行内 token 保留源 token 元数据

解析器还保留：

- 标题标题的行内节点
- `DocumentAST.reference_definitions` 中的引用链接定义
- 标题和渲染块的源码行范围

解析器行为说明：

- `markdown-it-py` 不会将引用定义行作为可见的 `link_reference_definition` 块发出
- 插件生成的块 token 会保留为插件特定的块类型或原始 markdown 回退块
- 插件生成的行内 token 在可能时予以保留，未知行内容器会保持其子文本完整

## 切分策略

切分器注册表支持以下名称：

- `recursive` / `default`：`RecursiveMarkdownSplitter` — 结构优先且感知预算；同级章节在预算允许时可以合并进同一个分块。
- `section`：`SectionMarkdownSplitter` — 按标题章节的直接正文输出不重叠分块；子章节独立输出，不重复出现在父章节分块里。

API 默认值为 `splitter="recursive"`。

递归切分遵循以下顺序：

1. 如果整篇文档已在预算内，则保持为一个分块。
2. 否则按标题章节切分。
3. 如果章节过大，则按块边界切分。
4. 如果块仍然过大，则回退到段落、行、句子、单词，最后硬切分。

重要细节：

- 当 `retain_headings=True` 时，标题上下文保留在 `Chunk.body` 中
- 当同级章节合并为一个分块时，共享的父标题会去重
- `include_common_headings=False` 时，`Chunk.body` 不包含已由 `Chunk.headings` 表示的公共标题前缀
- `estimated_token_count` 是用于切分的加法预算估算：章节正文、标题文本和子树计数自底向上缓存。标题标记（前导 `#` 序列）和 Markdown 分隔符各计为一个 token。`token_count` 仍从最终渲染的分块正文一次性计数用于报告。
- `merge_below_tokens` 不是最终分块的最小 token 数，而是针对 fragment 或文本回退切分产生的短尾块的合并软阈值：低于该值的相邻短尾块只会在标题路径相同且估算合并大小仍不超过 `max_tokens` 时被合并。
- 可选重叠仅在单个超大块必须按段落、行、句子、单词或硬边界切分时应用
- 默认 `split_oversized_blocks` 包含 `paragraph`、`blockquote` 和 `html_block`；超大列表和代码块默认保持完整，但可通过设置变为可切分
- 长的 URL 样式文本被视为不可切分，不会跨分块硬切分
- `isolate_front_matter=True` 始终将 front matter 作为第一个分块（`chunk_type="front_matter"`）
- `skip_empty_sections=True` 丢弃仅有标题无正文的空章节分块
- 分隔线会附加到前面的段落、引用块、HTML 块、数学块或带编号数学块上
- 对 `section` 切分器，`recursive_split=False` 会保留超大的章节正文。
  设置 `recursive_split=True` 后，超大的章节直接正文会复用同一套块/文本回退切分逻辑。

## 分词器

[`src/lumberjack/core/tokenizers.py`](src/lumberjack/core/tokenizers.py) 中可用的分词器实现：

- `SimpleCharTokenizer`：按字符计数
- `TiktokenTokenizer`：通过 `tiktoken` 按模型 token 计数，带 LRU 缓存

如果未安装 `tiktoken` 但请求了 `TiktokenTokenizer`，库会抛出运行时错误并提供安装指引。

## 仓库结构

```text
src/lumberjack/base/          协议接口
src/lumberjack/core/          解析器、切分器、分词器和访问器实现
src/lumberjack/core/plugins/  自定义 markdown-it 插件（方括号数学）
src/lumberjack/api.py         公共 Python API
src/lumberjack/models.py      内部数据模型
src/lumberjack/utils.py       Markdown 渲染辅助函数
src/lumberjack/main.py        命令行编排
src/lumberjack/web/           FastAPI Web 层（应用、路由、静态文件服务）
lumberjack_webui/             React + TypeScript 前端
script/                       批量处理脚本
tests/                        解析器、切分器、API 和 Web 测试
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
uv run pytest tests/test_web.py
```

代码检查和格式化：

```bash
uv run ruff check --fix
uv run ruff format
```

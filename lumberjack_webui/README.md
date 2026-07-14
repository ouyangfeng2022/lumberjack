# Lumberjack Web UI

Lumberjack 的 Web 前端，提供可视化的 Markdown 文档拆分界面。

## 技术栈

- **React 19** + **TypeScript** + **Vite**
- CSS Modules 样式方案
- 通过 Vite 代理与后端 FastAPI 通信

## 开发

```bash
cd lumberjack_webui

# 安装依赖
npm install

# 启动开发服务器（默认 localhost:5173，代理 /lumber -> localhost:8000）
npm run dev

# 生产构建（输出到 ../src/lumberjack/web/static/）
npm run build

# 预览生产构建
npm run preview

# 代码检查
npm run lint
```

开发时需要同时启动后端服务：

```bash
# 在项目根目录
uv sync --group web
uv run lumberjack-serve --reload
```

## Markdown Parser 自定义插件

Web UI 通过 HTTP 调用后端 `/lumber/api/split/*` 接口，浏览器端不能运行时注册 Python `markdown-it-py` 插件。需要自定义 Markdown parser 插件时，应在后端代码中直接组合 `MarkdownItParser -> Splitter` 管线；UI 仍然可以展示返回的 chunk 结果。

如果插件只改变已有 Markdown 结构，例如 task list 仍然解析成 list item，只是在行内增加 checkbox HTML，只需要把插件传给 `MarkdownItParser`：

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parsers.markdown import MarkdownItParser

parser = MarkdownItParser(plugins=(tasklists_plugin,))
document = parser.parse("- [x] done", document_title="tasks.md")
```

如果插件会产生新的块级 token type，需要用 `MarkdownBlockSpec` 声明 token type 到 lumberjack 块类型的映射。下面是完整示例：用 `mdit_py_plugins.container.container_plugin` 解析 callout 容器，并把 `callout` 作为可配置的块类型交给 splitter：

```python
from mdit_py_plugins.container import container_plugin

from lumberjack.core.models import BaseParams, MarkdownBlock, SplitOptions
from lumberjack.core.options import resolve_block_options
from lumberjack.core.parsers.markdown import MarkdownBlockContext, MarkdownBlockSpec
from lumberjack.core.parsers.markdown import MarkdownItParser
from lumberjack.core.splitter import RecursiveSplitter
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

使用规则：

- `MarkdownBlockSpec.kind` 会规范化为小写，并成为 `MarkdownBlock.kind`。
- `token_types` 必须声明自定义 markdown-it token type，例如 `("container_callout_open",)`。
- 不提供 `handler` 时，lumberjack 会捕获源码片段；容器类 token 会递归解析子块。
- `handler` 接收 `MarkdownBlockContext`，返回 `(block, next_index)`；需要跳过 token 时可返回 `None` 作为 block。
- handler 返回的 block 必须使用声明的 `kind`。
- 内置 token type（如 `paragraph_open`、`fence`、`table_open`、`html_block`）不能通过 `MarkdownBlockSpec` 重映射。
- 配置插件产生的块类型时，请使用 `parser.block_kinds` 调用 `resolve_block_options()`；不要用只包含内置类型的 `MarkdownItParser.default_block_kinds`。

## 项目结构

```
lumberjack_webui/
├── public/              # 静态资源
├── src/
│   ├── api/
│   │   └── split.ts     # 后端 API 客户端
│   ├── components/
│   │   ├── MarkdownInput.tsx  # 文本输入 / 文件上传
│   │   ├── SplitOptions.tsx   # 拆分配置（基础 + 高级）
│   │   ├── ChunkList.tsx      # 拆分结果列表
│   │   └── ChunkResult.tsx    # 单个 Chunk 卡片
│   ├── types/
│   │   └── chunk.ts     # TypeScript 类型定义
│   ├── App.tsx           # 主应用组件
│   ├── App.module.css    # 应用样式
│   ├── main.tsx          # 入口
│   └── index.css         # 全局样式
├── index.html
├── vite.config.ts        # Vite 配置（代理 + 输出目录）
├── tsconfig.json
└── eslint.config.js
```

## 功能

- **双模式输入**：直接输入 Markdown 文本或上传 `.md` / `.markdown` / `.txt` 文件
- **基础选项**：max_tokens
- **高级选项**：ideal_max_tokens_ratio、merge_below_tokens、merge_small_chunks、tokenizer 选择、可拆分块类型
- **结果展示**：Chunk 列表，显示 token 数、行范围、标题层级，支持展开/折叠和 text/body 切换

## 构建 & 部署

`npm run build` 将产物输出到 `../src/lumberjack/web/static/`，后端 `lumberjack-serve` 会自动托管该目录。生产环境只需启动后端即可同时提供 API 和前端页面。

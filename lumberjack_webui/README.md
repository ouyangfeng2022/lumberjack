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
uv sync --extra web
uv run lumberjack-serve --reload
```

## Markdown Parser 自定义插件

Web UI 通过 HTTP 调用后端 `/lumber/api/split/*` 接口，浏览器端不能运行时注册
Python `markdown-it-py` 插件。需要自定义 Markdown parser 时，应在后端组合
`MarkdownItParser -> Splitter -> ChunkFinalizer`；UI 仍然展示最终 chunk。

```python
from mdit_py_plugins.tasklists import tasklists_plugin

from lumberjack.parser import MarkdownItParser
from lumberjack.finalizer import ChunkFinalizer
from lumberjack.splitter import SiblingSplitter
from lumberjack.tokenizer import ApproxByteTokenizer

tokenizer = ApproxByteTokenizer()
parser = MarkdownItParser(plugins=(tasklists_plugin,))
document = parser.parse("- [x] done", document_title="tasks.md")
drafts = SiblingSplitter(tokenizer).split(document)
chunks = ChunkFinalizer(tokenizer).finalize(document, drafts)
```

产生新块级 token type 的插件可通过 `MarkdownBlockSpec` 声明映射；自定义 handler
接收 `MarkdownBlockContext`，并通过 `context.parser` 使用 parser 的辅助方法。

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
- **高级选项**：`ideal_max_tokens_ratio`、`merge_below_ratio`、exact/incremental splitter、tokenizer 选择与块级策略
- **结果展示**：Chunk 列表，显示 token 数、行范围、标题层级，支持展开/折叠和 text/body 切换

## 构建 & 部署

`npm run build` 将产物输出到 `../src/lumberjack/web/static/`，后端 `lumberjack-serve` 会自动托管该目录。生产环境只需启动后端即可同时提供 API 和前端页面。

# lumberjack

`lumberjack` 是一个面向长文档检索与 RAG 预处理场景的文档切分工具。当前版本聚焦 Markdown，并以“先解析 AST，再基于结构切分”为核心设计原则。

当前仓库已经从 `demo.py` 里的实验代码整理为一个可持续开发的基础版本：

- 不再依赖 `langchain_text_splitters`
- 使用项目内自研的 Markdown block/section AST
- 以标题层级为主干，保留正文、代码块等 block 结构
- 提供可扩展的 tokenizer、parser、splitter 接口

## 当前目标

v0.1 只支持 Markdown，先把下面这条链路打稳：

1. 读取 Markdown 文本
2. 解析为文档树
3. 基于 AST 生成带层级上下文的 chunk
4. 按 token 上限合并或拆分 chunk

## 项目结构

```text
lumberjack/
├─ demo.py
├─ docs/
│  ├─ architecture.md
│  └─ development.md
├─ src/lumberjack/
│  ├─ base/
│  │  ├─ __init__.py
│  │  └─ interfaces.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ parser.py
│  │  ├─ splitter.py
│  │  ├─ tokenizers.py
│  │  └─ visitor.py
│  ├─ __init__.py
│  ├─ main.py
│  ├─ models.py
│  └─ utils.py
└─ tests/
   ├─ fixtures/markdown/
   │  └─ sample.md
   ├─ __init__.py
   ├─ test_parser.py
   └─ test_splitter.py
```

## 快速开始

安装为本地开发包后可以直接使用 CLI：

```bash
python -m pip install -e .
lumberjack path/to/file.md --max-tokens 1200 --min-tokens 200
```

输出 JSON：

```bash
lumberjack path/to/file.md --format json --output chunks.json
```

如果你想使用 `tiktoken` 进行更接近模型实际行为的 token 统计：

```bash
python -m pip install -e .[tokenizers]
lumberjack path/to/file.md --tokenizer tiktoken
```

## 实现说明

目前的 parser 是一个“面向切分场景”的 Markdown AST，不追求完整覆盖整个 Markdown 规范，而是优先保证：

- 正确识别 `#` 到 `######` 标题层级
- 正确跳过 fenced code block 内部的伪标题
- 保留段落、列表、引用、表格、代码块等 block 边界
- 让 splitter 能按 section 和 block 两层语义切分

后续如果需要更强的 Markdown 兼容性，可以在现有接口之上增加 `marko` 适配层，而不用重写 splitter。

## 与 `demo.py` 的关系

`demo.py` 保留为思路参考，不作为正式实现的一部分。正式代码不再依赖 `langchain_text_splitters`，后续开发请以 `src/lumberjack/` 为准。

## 下一步建议

- 增加 `marko` 适配实现，对照自研 AST 做兼容性验证
- 引入 chunk metadata，例如 section path、chunk index、source line range
- 为代码块、表格、超长列表设计更细的降级切分策略
- 加入针对真实语料的 golden tests

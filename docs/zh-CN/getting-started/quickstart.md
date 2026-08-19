# 快速开始

[English](../../getting-started/quickstart.md)

默认流水线接受字符串、bytes 或 `pathlib.Path`。普通字符串始终表示文档内容，而不是文件路径。

```python
from pathlib import Path

from lumberjack import Lumberjack

jack = Lumberjack(max_tokens=1200)
result = jack.saw(Path("handbook.md"))

for chunk in result.chunks:
    print({"heading": chunk.own_heading, "body": chunk.body, "tokens": chunk.token_count})
```

`Lumberjack.saw()` 返回 `SplitResult`。其中 `document` 是解析后的 `DocTree`，`chunks` 是可直接入库的最终 `Chunk`。

## 选择输入格式

默认 `format="auto"`。传入 `Path` 时，会按扩展名选择 Markdown、HTML 或 DOCX parser；当来源名称不可用时可以显式指定：

```python
html = "<h1>Release notes</h1><p>Ship the package.</p>"
result = Lumberjack(max_tokens=300).saw(html, format="html")
```

DOCX 输入需要 `docx` extra，可传 bytes 或路径：

```python
result = Lumberjack(max_tokens=800).saw(Path("report.docx"), format="docx")
```

## 查看输出

标题作为 metadata 与正文分离，因此可以用正文生成 embedding，同时保留检索或展示需要的上下文。

```python
chunk = result.chunks[0]
print(chunk.ancestor_headings)
print(chunk.own_heading)
print(chunk.body)
print(chunk.token_count)
```

完整字段语义见[Chunk 与来源信息](../concepts/chunks.md)；如果工作流从文件开始，可改用 [CLI](../reference/cli.md)。

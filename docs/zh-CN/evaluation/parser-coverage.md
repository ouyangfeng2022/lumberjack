# Parser 覆盖范围与鲁棒性

本文定义 Lumberjack 中“解析成功”的含义。没有抛出异常只是第一层验证，解析质量由
三个相互独立的层面衡量：

1. **包与树有效性**：完成解析，并满足层级、来源范围、非空 block 等 `DocTree`
   不变量。
2. **内容保真**：使用词法 token recall 和非空白字符 recall 对比源文档可见内容与
   解析树。DOCX 的生产工具会任意拆分或合并 run，因此字符 recall 是判断这类文档
   是否真正丢字的补充指标。
3. **元素一致性**：版本化用例明确断言必须出现和禁止出现的 section、block、inline
   类型，避免“文字还在，但公式、链接、表格或代码被识别成普通正文”。

大语料 benchmark 是回归基线，不等于已经证明可以处理世界上所有文档。

## Markdown 方言

默认解析器采用 `markdown-it-py` 的 GFM-like 模式，并加入 YAML front matter 和
Lumberjack 数学扩展。CommonMark 本身没有定义数学公式，因此下列数学规则是
Lumberjack 明确提供的方言契约。

| 输入元素 | 输出表示 | 当前行为 |
| --- | --- | --- |
| ATX 标题 | `SectionNode` | 识别 H1-H6 层级与标题内 inline |
| Setext 标题 | `SectionNode` | 默认关闭；可用 `disable_lheading=False` 开启 |
| 段落 | `paragraph` | 保留 inline 结构和源行范围 |
| 强调、加粗、删除线 | inline 节点 | 保留嵌套内容 |
| 行内代码 | `code_span` | 保留 literal；其中的公式分隔符不会被解析 |
| 链接、自动链接、图片 | inline 节点 | 保留目标、标题和子文本 |
| 软换行、硬换行 | inline 节点 | 分别识别为 `soft_break`、`hard_break` |
| 引用 | `blockquote` | 保留嵌套 block |
| 有序、无序列表 | `list` / `list_item` | 保留嵌套、顺序属性和 tight/loose 状态 |
| Pipe 表格 | `table` | 保留原始 Markdown 表面文本 |
| 围栏、缩进代码 | `code_fence` / `code_block` | 保留 language/info 和 literal |
| 原始 HTML、HTML 表格 | `html_block` / `html_table` | HTML 作为 opaque 内容；表格有独立类型 |
| YAML front matter | `front_matter` + metadata | 同时保留源 block 和解析后的 metadata |
| 引用定义 | `reference_definitions` | 独立保留 label、destination、title |
| 主题分隔线 | 丢弃 | 作为结构分隔符消费，明确不写入 `DocTree` 和 chunk |

任务列表的 checkbox 目前仍作为 list item 文本保留，还没有独立的 checked 状态字段。
脚注及其他第三方 `markdown-it-py` 扩展属于可选 plugin，不是默认方言。原始 HTML
会被正确分类，但不会把任意 HTML DOM 全部转换为 inline 语义节点。

### 数学公式识别

| 语法 | 分类 | 说明 |
| --- | --- | --- |
| `$a+b=c$` | `math_inline` | dollar 行内公式 |
| `$ a+b=c$`、`$a+b=c $`、`$ a+b=c $` | `math_inline` | 允许分隔符内侧空格，并在 `literal` 中保留 |
| `\(a+b=c\)` | `math_inline` | 保留分隔符类型 |
| 独立 block 中的 `$$...$$` | `math_block` | 支持单行、多行、matrix、aligned 和空行；内容按 opaque literal 保存 |
| `$$...$$ (label)` | `math_block_eqno` | 编号保存在 `attrs.eqno` |
| `\[...\]`、`\[...\] (label)` | block math | 支持多行和编号 |

Lumberjack 负责识别公式元素和保留 TeX literal，但不验证 TeX 文法，也不构建公式
AST。转义 dollar、未闭合分隔符以及代码中的 dollar 会保持为非公式内容。为避免把
货币误判成公式，`price $5 and $10`、`1$x$`、`$x$2` 不会识别为公式；公式内部的
数字（如 `$2x$`）仍然支持。正文内部的 `$$...$$` 不属于当前行内方言，请使用
`$...$` 或 `\(...\)`。

## DOCX 覆盖范围

| DOCX 特性 | 当前行为 |
| --- | --- |
| 标题 | 仅将直接或继承的 OOXML `outlineLvl` 0-8 转为 section 1-9；不解释样式名或可见编号 |
| 段落和 run 格式 | 段落、加粗、斜体、下划线 metadata |
| 列表 | 仅使用直接或继承的 OOXML numbering（含 `numStyleLink`）；只有 `numId`、层级和编号格式完全一致才分组 |
| 表格 | 保留文档顺序、嵌套表格、wrapper 内 cell、转义 pipe/反斜线和多行 cell |
| 超链接、图片 | 保留 relationship、图片 part、title/alt，包括表格单元格内部 |
| 文本框、drawing | 保留段落 drawing 内的可见 textbox 文本 |
| 内容控件、修订 | 保留 `sdt`、`ins`、`moveTo`；忽略已删除或 moved-from 内容 |
| Office Math (OMML) | 区分行内/块公式，并保留线性可见公式文本 |
| 来源信息 | `SourceLocation.element_id` 使用真实 OOXML element path |
| Core properties | 提取 title、author |
| Strict OOXML | 在内存中规范化已知 Strict namespace 后解析 |
| 损坏的 OPC metadata | 修复缺失图片 Content-Type、悬空的可选图片/缩略图 relationship、模板主 Content-Type，并记录到 `metadata.docx_repairs` |

当前不能或不能完整处理的情况：

- `word/document.xml` 本身标签错配时拒绝解析；自动猜测缺失 XML 会造成不可控的数据
  损坏。
- 不支持加密/密码保护文档和旧式二进制 `.doc`。
- header、footer、comment、footnote/endnote、chart、SmartArt 语义、macro 和嵌入式
  OLE payload 当前不会输出为正文 block。
- 对 markup-compatibility `AlternateContent` 仅使用明确的 `Fallback`；没有
  fallback 的 `Choice` 会被省略，不会猜测当前实现支持其 `Requires` namespace。
- OMML 当前保留线性可见文本，不承诺无损转换为 LaTeX 或完整运算符树。
- `Heading 2.1`、`标题 1`、`3.1.1`、`Quote`、`List Bullet Custom`
  这类样式名本身不构成语义；等宽文本也不会被猜成代码。
- part 名重复或不安全、entry 超过 100,000 个、解压后总内容超过 512 MiB 的
  package 会在修复和解析前被拒绝。

## 可复现基线

基线使用 seed `20260824`，大型来源每个随机抽取最多 500 份，小型 DOCX 和元素
一致性语料全部运行：

| 语料/格式 | 数量 | 结果 |
| --- | ---: | --- |
| Markdown 元素一致性 | 20 | 20 成功；元素断言 58/58 |
| CommonMark 0.31.2 | 652 中抽取 500 | 500 成功；token recall 1.0 |
| Kubernetes website Markdown | 2,453 中抽取 500 | 500 成功；平均 token recall 0.9975 |
| python-docx fixtures | 45 | 45 成功；DOCX 字符 recall 1.0 |
| LibreOffice Writer OOXML | 377 | 376 成功；所有成功文档的 DOCX 字符 recall 均为 1.0 |
| **总计** | **1,442** | **1,441 成功；仅 1 个 malformed XML 失败** |

LibreOffice 中有 19 份成功文档的词法 token recall 低于 0.99，原因是 OOXML run
边界以不同方式连接或拆分了相同可见字符；这些文档的非空白字符 recall 都是 1.0，
因此将其保留为指标诊断，而不报告为内容丢失。

运行方式：

```bash
uv run python -m benchmarks.fetch_parser_corpora
uv run python -m benchmarks.parser_run \
  --seed 20260824 \
  --sample-size-per-source 500
```

`raw.json` 是单文档失败和诊断的权威证据；`summary.json` 提供总体、按格式和按
数据集汇总。

# `standalone_blocks` 特殊 Block 独立切分计划

**Summary**
- 新增公开参数 `standalone_blocks`，默认 `{"table", "code_block", "code_fence"}`。
- 匹配的 `MarkdownBlock.kind` 必须单独成为 chunk，不参与同 section、同 subtree、短尾 chunk 的合并。
- 如果该 block 超过 `max_tokens`，是否切分仍由 `split_oversized_blocks` 决定；切出来的每个 piece 也保持独立。

**Key Changes**
- 在 `SplitOptions` 与 `lumber()` 增加 `standalone_blocks`，空集合表示关闭该行为。
- splitter 层从源头处理独立 block：
  - 整个 section/document 即使 fits budget，只要 subtree 内有 standalone block，也不能直接合成单 chunk。
  - `_split_section_body` 遇到 standalone block 先 flush 普通内容，再输出该 block 的独立 draft。
  - `RecursiveMarkdownSplitter` 和 `SectionMarkdownSplitter` 都应用该规则。
  - standalone chunk 的 `chunk_type` 设置为原 block kind；普通 chunk 维持现状。
- 暴露到全入口：
  - CLI：新增 `--standalone-block <kind>` 可重复；新增 `--no-standalone-blocks` 禁用默认值。
  - Web API：新增 form 字段 `standalone_blocks`，默认 `"table,code_block,code_fence"`。
  - Web UI：新增独立 block 复选项组，默认选中表格、代码块、代码围栏。
- 更新 README 中 Python API、CLI 参数、splitter 行为说明。

**Test Plan**
- Core splitter:
  - 默认情况下，表格和 fenced/indented code block 即使整体文档未超预算，也独立成 chunk。
  - `standalone_blocks=frozenset()` 时恢复旧的合并行为。
  - standalone block 不被 `merge_small_chunks` 合并回相邻段落。
  - 超大 standalone code fence 未加入 `split_oversized_blocks` 时保持一个超大 chunk；加入后拆成多个独立 code chunk。
  - `SectionMarkdownSplitter` 在 direct body 中同样拆出 standalone block。
- API/CLI/Web:
  - `lumber(..., standalone_blocks=...)` 传参生效。
  - Web API 能解析默认值、空字符串、显式 block 列表。
  - CLI 默认启用表格/代码块独立，`--no-standalone-blocks` 可关闭，`--standalone-block` 可覆盖默认集合。
- Verification:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run pytest tests/test_splitter.py tests/test_api.py tests/test_web.py`
  - 如果修改 Web UI：运行 `npm run lint` 和 `npm run build` 更新生产静态资源。

**Assumptions**
- “代码块”包含 `code_block` 和 `code_fence`。
- standalone chunk 仍遵守 `retain_headings` / `include_common_headings`，即可以带标题上下文，但正文不与其他 block 合并。
- 当前工作区已有 `src/lumberjack/core/splitter.py` 未提交修改；实现时保留并基于该现状继续改。

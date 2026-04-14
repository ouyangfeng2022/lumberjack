# lumberjack Development Notes

## Project

AST-driven markdown document splitter for RAG preprocessing. Python 3.13+, src-layout package built with hatchling.

## Commands

```bash
# Install for development (with test dependencies and tiktoken support)
uv sync --group test --extra tokenizers

# Run CLI
lumberjack path/to/file.md --max-tokens 1200 --min-tokens 200 --format json

# Run tests
uv run pytest
uv run pytest tests/test_parser.py  # individual test file
```

## Architecture

Core pipeline: `Markdown text → MarkdownParser → DocumentAST → MarkdownSplitter → Chunk[]`

- **Parser**: Custom AST, heading-tree based. Ignores headings inside fenced code blocks.
- **Splitter**: Three-tier fallback - sections → blocks → paragraph/line/sentence/word
- **Tokenizer**: Pluggable via `TokenizerProtocol` (simple char count or tiktoken)

Protocol interfaces in `src/lumberjack/base/interfaces.py`. Data models use `@dataclass(slots=True)`.

## Constraints

- **Only Markdown** - no PDF/HTML/DOCX planned
- **demo.py is reference only** - not part of the actual implementation
- **Code fences are never split** - kept intact even when oversized
- **No langchain dependency** - custom AST, not third-party splitters

## Testing

Tests use `pytest`. Project root is added to `sys.path` via `tests/conftest.py`.

When adding features:
1. Update fixtures in `tests/fixtures/markdown/`
2. Implement parser/splitter code
3. Add assertions in `tests/test_*.py`

After every code change:
1. Run `ruff check --fix`
2. Review the output and decide whether it is necessary and safe to run `ruff check --fix --unsafe-fixes`
3. Run `ruff format` after linting is complete

Regression fixtures should cover: FAQ docs, API docs, tutorials with code blocks, mixed CJK/English.

## Code Organization

- `src/lumberjack/base/` - Protocol interfaces
- `src/lumberjack/core/` - Parser, splitter, tokenizer implementations
- `src/lumberjack/models.py` - Data models (DocumentAST, SectionNode, MarkdownBlock, Chunk)
- `src/lumberjack/main.py` - CLI orchestration only (no business logic)

## Roadmap

- **M1**: Markdown AST splitting (current focus)
- **M2**: Chunk metadata (line ranges, section paths)
- **M3**: `marko` adapter as alternative parser
- **M4**: Production hardening (error handling, golden tests, benchmarks)

# Parser validation corpora

The default parser suite is self-contained and does not access the network.
`tests/parser/test_parser_robustness.py` combines 20 Markdown block shapes with
16 inline shapes (320 cases) and creates 32 deterministic DOCX documents in
memory. These cases supplement the focused parser regression tests.

For a broader pre-release audit, `validate_parsers.py` accepts external corpora
that are deliberately not copied into the repository:

- CommonMark 0.31.2 provides 652 normative Markdown examples. The specification
  is CC BY-SA 4.0 and its `spec.json` SHA-256 is
  `d431b29d97b6f73e69d547109cf5081578fac931e72afe95639ebe766c1b2a20`.
- The `python-openxml/python-docx` repository is MIT licensed. Its own DOCX
  fixtures exercise packages produced by Word with hyperlinks, drawings,
  tables, page breaks, missing properties, and other OOXML variations. Pin
  corpus downloads to commit `e45454602b53e8e572b179ccf1c91093ec9f4ed7`.

Example:

```bash
curl -fsSL https://spec.commonmark.org/0.31.2/spec.json \
  -o /tmp/commonmark-0.31.2.json

uv run python tests/corpora/validate_parsers.py \
  --commonmark-json /tmp/commonmark-0.31.2.json \
  --docx-dir /tmp/python-docx-fixtures
```

The validator checks that every input parses and that every resulting tree has
valid section indexes, heading paths, increasing hierarchy, non-empty blocks,
and paired source ranges. It is a parser robustness smoke test, not an assertion
that Lumberjack renders the same HTML as CommonMark.

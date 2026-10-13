import type { SplitOptions, SplitterName, TokenizerName } from "../types/chunk";
import { inputFilename, resolvedFormat, type DocumentInput } from "./formats";

const SPLITTER_CLASSES: Record<SplitterName, string> = {
  sibling: "SiblingSplitter",
  "exact-sibling": "ExactSiblingSplitter",
  "incremental-sibling": "SiblingSplitter",
  subtree: "SubtreeSplitter",
  "exact-subtree": "ExactSubtreeSplitter",
  "incremental-subtree": "SubtreeSplitter",
  section: "SectionSplitter",
  "exact-section": "ExactSectionSplitter",
  "incremental-section": "SectionSplitter",
  record: "RecordSplitter",
};
const TOKENIZER_CLASSES: Record<TokenizerName, string> = {
  approx: "ApproxByteTokenizer",
  tiktoken: "TiktokenTokenizer",
  transformers: "TransformersTokenizer",
};
const DEFAULT_INPUT: DocumentInput = {
  text: "",
  file: null,
  format: "markdown",
};
export const shellQuote = (value: string) =>
  "'" + value.replaceAll("'", "'\\''") + "'";

export function buildCliSnippet(
  options: SplitOptions,
  input: DocumentInput = DEFAULT_INPUT,
): string {
  const flags = [
    "lumber " +
      shellQuote(
        inputFilename(input).startsWith("-")
          ? "./" + inputFilename(input)
          : inputFilename(input),
      ),
    "--input-format " + resolvedFormat(input),
    "--splitter " + options.splitter,
    "--tokenizer " + options.tokenizer,
    "--max-tokens " + options.max_tokens,
    "--ideal-max-tokens-ratio " + options.ideal_max_tokens_ratio,
    "--merge-below-ratio " + options.merge_below_ratio,
  ];
  if (!options.skip_empty_sections) flags.push("--no-skip-empty-sections");
  if (!options.heading_sensitive) flags.push("--no-heading-sensitive");
  for (const [kind, config] of Object.entries(options.block_configs ?? {})) {
    const settings = Object.entries(config)
      .filter(([, value]) => value != null)
      .map(([key, value]) => key.replaceAll("_", "-") + "=" + value);
    if (settings.length)
      flags.push("--block " + shellQuote(kind + ":" + settings.join(",")));
  }
  return flags.join(" \\\n  ");
}

export function buildPythonSnippet(
  options: SplitOptions,
  input: DocumentInput = DEFAULT_INPUT,
): string {
  const splitter = SPLITTER_CLASSES[options.splitter];
  const blocks = Object.entries(options.block_configs ?? {});
  // Decode JSON in Python so quotes, booleans and Unicode need no code interpolation.
  const literal = (value: unknown) =>
    "json.loads(" + JSON.stringify(JSON.stringify(value)) + ")";
  const blockLines = blocks.map(([kind, value]) => {
    const cls =
      kind === "table"
        ? "MarkdownTableConfig"
        : kind === "html_table"
          ? "HTMLTableConfig"
          : "BlockConfig";
    return (
      "        " +
      cls +
      "(" +
      (cls === "BlockConfig"
        ? "kind=BlockKind(" + JSON.stringify(kind) + "), "
        : "") +
      "**" +
      literal(value) +
      "),"
    );
  });
  return [
    "import json",
    "from pathlib import Path",
    "from lumberjack import Document, Lumberjack",
    "from lumberjack.splitter import " + splitter,
    "from lumberjack.tokenizer import " + TOKENIZER_CLASSES[options.tokenizer],
    ...(blocks.length
      ? [
          "from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig, HTMLTableConfig",
        ]
      : []),
    "",
    "splitter = " + splitter + "(",
    "    " + TOKENIZER_CLASSES[options.tokenizer] + "(),",
    "    max_tokens=" + options.max_tokens + ",",
    "    ideal_max_tokens_ratio=" + options.ideal_max_tokens_ratio + ",",
    "    merge_below_ratio=" + options.merge_below_ratio + ",",
    "    skip_empty_sections=" +
      (options.skip_empty_sections ? "True" : "False") +
      ",",
    "    heading_sensitive=" +
      (options.heading_sensitive ? "True" : "False") +
      ",",
    ...(blocks.length ? ["    block_options=[", ...blockLines, "    ],"] : []),
    ")",
    "result = Lumberjack(splitter=splitter, max_tokens=" +
      options.max_tokens +
      ").saw(",
    "    Document(source=" +
      (input.file
        ? "Path(" + JSON.stringify(inputFilename(input)) + ")"
        : literal(input.text)) +
      ", format=" +
      JSON.stringify(resolvedFormat(input)) +
      ")",
    ")",
    "for chunk in result.chunks:",
    "    print(chunk.chunk_id, chunk.token_count)",
  ].join("\n");
}

export function buildCurlSnippet(
  options: SplitOptions,
  input: DocumentInput,
  origin: string,
): string {
  if (input.file) {
    return [
      "curl --fail-with-body " + shellQuote(origin + "/lumber/api/split/file"),
      "-F " +
        shellQuote(
          'file=@"' +
            inputFilename(input)
              .replaceAll("\\", "\\\\")
              .replaceAll('"', '\\"') +
            '"',
        ),
      ...Object.entries({ input_format: input.format, ...options })
        .filter(([, value]) => value !== null)
        .map(
          ([key, value]) =>
            "--form-string " +
            shellQuote(
              key +
                "=" +
                (typeof value === "object" ? JSON.stringify(value) : value),
            ),
        ),
    ].join(" \\\n  ");
  }
  return [
    "curl --fail-with-body " + shellQuote(origin + "/lumber/api/split/text"),
    "-H 'Content-Type: application/json'",
    "--data-raw " +
      shellQuote(
        JSON.stringify({
          text: input.text,
          input_format: resolvedFormat(input),
          ...options,
        }),
      ),
  ].join(" \\\n  ");
}
export function configurationJson(
  options: SplitOptions,
  input: DocumentInput,
): string {
  return JSON.stringify(
    { input_format: resolvedFormat(input), ...options },
    null,
    2,
  );
}
export function splitterClassName(name: SplitterName): string {
  return SPLITTER_CLASSES[name];
}

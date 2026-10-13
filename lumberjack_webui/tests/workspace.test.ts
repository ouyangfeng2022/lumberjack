import { describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import {
  DEFAULT_OPTIONS,
  budgetCount,
  chunksAtLine,
  summarize,
  validateOptions,
} from "../src/lib/workspace";
import {
  buildCliSnippet,
  buildCurlSnippet,
  buildPythonSnippet,
  configurationJson,
  shellQuote,
} from "../src/lib/exportConfig";
import {
  ACCEPTED_FILES,
  FORMATS,
  TEXT_FORMATS,
  detectFormat,
  resolvedFormat,
  type DocumentInput,
} from "../src/lib/formats";
import { splitDocument } from "../src/api/split";
import type { ChunkData, SplitResponse } from "../src/types/chunk";

const chunk = (overrides: Partial<ChunkData> = {}): ChunkData => ({
  chunk_id: "c1",
  chunk_type: "paragraph",
  body: "hello",
  token_count: 30,
  body_token_count: 20,
  estimated_token_count: 29,
  headings_token_count: 10,
  ancestor_headings: [],
  own_heading: null,
  section_level: 0,
  document_title: "Test",
  document_path: null,
  start_line: 1,
  end_line: 3,
  source_locations: [],
  protected: false,
  ...overrides,
});
describe("workspace data", () => {
  test("budget statistics use run options and retain protected oversize chunks", () => {
    const result = {
      chunks: [
        chunk(),
        chunk({ token_count: 80, body_token_count: 60, protected: true }),
      ],
    } as SplitResponse;
    expect(summarize(result, { ...DEFAULT_OPTIONS, max_tokens: 70 })).toEqual({
      count: 2,
      total: 110,
      largest: 80,
      over: 1,
    });
    expect(
      summarize(result, {
        ...DEFAULT_OPTIONS,
        max_tokens: 70,
        heading_sensitive: false,
      }).over,
    ).toBe(0);
    expect(
      budgetCount(chunk(), { ...DEFAULT_OPTIONS, heading_sensitive: false }),
    ).toBe(20);
  });
  test("overlapping line ranges preserve every association", () => {
    expect(
      chunksAtLine(
        [
          chunk(),
          chunk({ start_line: 3, end_line: 5 }),
          chunk({ start_line: null, end_line: null }),
        ],
        3,
      ),
    ).toEqual([0, 1]);
    expect(chunksAtLine([chunk()], 6)).toEqual([]);
  });
  test("validates nonfinite, empty, fractional and out of range settings", () => {
    expect(validateOptions(DEFAULT_OPTIONS)).toBe(true);
    for (const max_tokens of [0, -1, 0.5, NaN, Infinity])
      expect(validateOptions({ ...DEFAULT_OPTIONS, max_tokens })).toBe(false);
    expect(validateOptions({ ...DEFAULT_OPTIONS, merge_below_ratio: 1 })).toBe(
      false,
    );
    expect(
      validateOptions({ ...DEFAULT_OPTIONS, ideal_max_tokens_ratio: 0 }),
    ).toBe(false);
  });
  test("format detection mirrors backend suffixes and binary classification", () => {
    expect(detectFormat("REPORT.PDF")).toBe("pdf");
    expect(detectFormat("data.ndjson")).toBe("jsonl");
    expect(detectFormat("file.unknown")).toBe("markdown");
    expect(FORMATS).toContain("tsx");
    expect(TEXT_FORMATS).not.toContain("sqlite");
    expect(ACCEPTED_FILES).toContain(".docx");
    expect(
      resolvedFormat({
        text: "",
        file: new File([], "a.xlsx"),
        format: "auto",
      }),
    ).toBe("xlsx");
  });
});
describe("export contracts", () => {
  const input: DocumentInput = {
    text: '# 中文\nApostrophe \' and $HOME and \\ and "quote"\n',
    file: null,
    format: "markdown",
  };
  const options = {
    ...DEFAULT_OPTIONS,
    max_tokens: 50,
    block_configs: {
      table: { repeat_header: false },
      code_fence: { split: false },
    },
  };
  test("Python snippet applies typed block configuration and literal text", () => {
    const snippet = buildPythonSnippet(options, input);
    expect(snippet).toContain("MarkdownTableConfig(");
    expect(snippet).toContain("block_options=[");
    const result = spawnSync(
      "python3",
      ["-c", "import ast,sys;ast.parse(sys.stdin.read())"],
      { input: snippet, encoding: "utf8" },
    );
    expect(result.stderr).toBe("");
    expect(result.status).toBe(0);
  });
  test("CLI flags and cURL payload preserve all settings without shell expansion", () => {
    const cli = buildCliSnippet(options, input);
    expect(cli).not.toContain("--counting");
    expect(cli).toContain("repeat-header=false");
    const curl = buildCurlSnippet(options, input, "http://localhost:8000");
    const decoded = spawnSync(
      "bash",
      [
        "-c",
        'printf "%s" ' +
          shellQuote(
            JSON.stringify({
              text: input.text,
              input_format: "markdown",
              ...options,
            }),
          ),
      ],
      { encoding: "utf8" },
    );
    expect(JSON.parse(decoded.stdout).text).toBe(input.text);
    expect(curl).toContain("--data-raw");
    const config = JSON.parse(configurationJson(options, input));
    expect(config.block_configs).toEqual(options.block_configs);
    expect(config).not.toHaveProperty("text");
  });
  test("file exports preserve filenames and explicit formats", () => {
    const fileInput: DocumentInput = {
      text: "",
      file: new File([], "report's $(touch nope).pdf"),
      format: "pdf",
    };
    expect(
      buildCliSnippet(options, {
        ...fileInput,
        file: new File([], "-flag.md"),
      }),
    ).toContain("'./-flag.md'");
    expect(buildPythonSnippet(options, fileInput)).toContain("Path(");
    expect(buildCliSnippet(options, fileInput)).toContain("--input-format pdf");
    expect(
      buildCurlSnippet(options, fileInput, "http://localhost:8000"),
    ).toContain("--form-string");
  });
});
describe("API boundary", () => {
  test("forwards input format and block configs in text and multipart requests", async () => {
    const original = globalThis.fetch;
    const requests: RequestInit[] = [];
    globalThis.fetch = (async (_url, init) => {
      requests.push(init!);
      return new Response(
        JSON.stringify({ schema_version: "lumberjack.chunk.v1", chunks: [] }),
      );
    }) as typeof fetch;
    try {
      await splitDocument(
        { text: "a,b\n1,2", file: null, format: "csv" },
        DEFAULT_OPTIONS,
      );
      expect(JSON.parse(requests[0].body as string).input_format).toBe("csv");
      await splitDocument(
        { text: "", file: new File(["PDF"], "a.pdf"), format: "pdf" },
        { ...DEFAULT_OPTIONS, block_configs: { table: { split: false } } },
      );
      const form = requests[1].body as FormData;
      expect(form.get("input_format")).toBe("pdf");
      expect(JSON.parse(form.get("block_configs") as string).table.split).toBe(
        false,
      );
    } finally {
      globalThis.fetch = original;
    }
  });
  test("retains HTTP status and server validation detail", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: "missing pdf extra" }), {
        status: 400,
      })) as typeof fetch;
    try {
      await expect(
        splitDocument(
          { text: "", file: null, format: "markdown" },
          DEFAULT_OPTIONS,
        ),
      ).rejects.toThrow("HTTP 400: missing pdf extra");
    } finally {
      globalThis.fetch = original;
    }
  });
});

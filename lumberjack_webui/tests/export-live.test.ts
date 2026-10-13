import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { spawnSync } from "node:child_process";
import {
  buildCliSnippet,
  buildCurlSnippet,
  buildPythonSnippet,
} from "../src/lib/exportConfig";
import { DEFAULT_OPTIONS } from "../src/lib/workspace";
import type { DocumentInput } from "../src/lib/formats";
import { splitDocument } from "../src/api/split";

describe.skipIf(!process.env.LUMBERJACK_E2E_LIVE)(
  "exported code against real backend",
  () => {
    test("CLI, cURL and Python preserve text, file input and typed block configuration", async () => {
      const root = resolve("..");
      const directory = mkdtempSync(join(tmpdir(), "lumberjack-export-"));
      const options = {
        ...DEFAULT_OPTIONS,
        max_tokens: 60,
        splitter: "exact-section" as const,
        block_configs: {
          table: { repeat_header: false },
          code_fence: { split: false },
        },
      };
      const text =
        "# Export test\n\nQuotes ' \" and literal $(touch SHOULD_NOT_EXIST) and 中文.\n\n## Table\n\n| A | B |\n|---|---|\n| one | two |\n\n" +
        "Words for splitting. ".repeat(60);
      const filename = "report's $(touch SHOULD_NOT_EXIST).md";
      writeFileSync(join(directory, filename), text);
      const inputs: DocumentInput[] = [
        { text, file: null, format: "markdown" },
        { text, file: new File([text], filename), format: "markdown" },
      ];
      const originalFetch = globalThis.fetch;
      globalThis.fetch = ((url, init) =>
        originalFetch(
          new URL(String(url), "http://127.0.0.1:8000"),
          init,
        )) as typeof fetch;
      const env = {
        ...process.env,
        PATH: join(root, ".venv/bin") + ":" + process.env.PATH,
        PYTHONPATH: join(root, "src"),
        UV_CACHE_DIR: "/tmp/uvcache",
      };
      try {
        for (const input of inputs) {
          writeFileSync(
            join(directory, input.file ? filename : "document.md"),
            text,
          );
          const expected = await splitDocument(input, options);
          const expectedCounts = expected.chunks.map(
            (chunk) => chunk.token_count,
          );
          for (const command of [
            buildCliSnippet(options, input),
            buildCurlSnippet(options, input, "http://127.0.0.1:8000"),
          ]) {
            const output = spawnSync("bash", ["-c", command], {
              cwd: directory,
              env,
              encoding: "utf8",
              timeout: 15000,
            });
            expect(output.status).toBe(0);
            const actual = JSON.parse(output.stdout);
            expect(
              actual.chunks.map(
                (chunk: { token_count: number }) => chunk.token_count,
              ),
            ).toEqual(expectedCounts);
          }
          const python = spawnSync(
            "uv",
            [
              "run",
              "--no-sync",
              "--project",
              root,
              "python",
              "-c",
              buildPythonSnippet(options, input),
            ],
            { cwd: directory, env, encoding: "utf8", timeout: 15000 },
          );
          expect(python.stderr).toBe("");
          expect(python.status).toBe(0);
          expect(
            python.stdout
              .trim()
              .split("\n")
              .map((line) => Number(line.split(" ").at(-1))),
          ).toEqual(expectedCounts);
        }
      } finally {
        globalThis.fetch = originalFetch;
        rmSync(directory, { recursive: true, force: true });
      }
    });
  },
);

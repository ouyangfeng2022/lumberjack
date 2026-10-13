import type { ChunkData, SplitOptions, SplitResponse } from "../types/chunk";
import type { DocumentInput } from "./formats";

export const DEFAULT_OPTIONS: SplitOptions = {
  max_tokens: 1200,
  ideal_max_tokens_ratio: 0.8,
  merge_below_ratio: 0.125,
  skip_empty_sections: true,
  heading_sensitive: true,
  block_configs: null,
  tokenizer: "approx",
  splitter: "section",
};
export interface RunSnapshot {
  input: DocumentInput;
  options: SplitOptions;
  revision: number;
  result: SplitResponse;
  elapsedMs: number;
}
export function budgetCount(chunk: ChunkData, options: SplitOptions): number {
  return options.heading_sensitive ? chunk.token_count : chunk.body_token_count;
}
export function chunkBudget(chunk: ChunkData, options: SplitOptions): number {
  return (
    options.block_configs?.[chunk.chunk_type]?.max_tokens ?? options.max_tokens
  );
}
export function summarize(result: SplitResponse, options: SplitOptions) {
  return {
    count: result.chunks.length,
    total: result.chunks.reduce((sum, chunk) => sum + chunk.token_count, 0),
    largest: result.chunks.reduce(
      (max, chunk) => Math.max(max, budgetCount(chunk, options)),
      0,
    ),
    over: result.chunks.filter(
      (chunk) => budgetCount(chunk, options) > chunkBudget(chunk, options),
    ).length,
  };
}
// Source ranges can overlap when a single source block is split into pieces.
export function chunksAtLine(chunks: ChunkData[], line: number): number[] {
  return chunks.flatMap((chunk, index) =>
    chunk.start_line != null &&
    chunk.end_line != null &&
    line >= chunk.start_line &&
    line <= chunk.end_line
      ? [index]
      : [],
  );
}
export function validateOptions(options: SplitOptions): boolean {
  return (
    Number.isInteger(options.max_tokens) &&
    options.max_tokens > 0 &&
    Number.isFinite(options.ideal_max_tokens_ratio) &&
    options.ideal_max_tokens_ratio > 0 &&
    options.ideal_max_tokens_ratio <= 1 &&
    Number.isFinite(options.merge_below_ratio) &&
    options.merge_below_ratio >= 0 &&
    options.merge_below_ratio < 1
  );
}

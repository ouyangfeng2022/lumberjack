export interface ChunkData {
  chunk_id: string;
  chunk_type: string;
  body: string;
  token_count: number;
  estimated_token_count: number;
  headings_token_count: number;
  body_token_count: number;
  ancestor_headings: [number, string][];
  own_heading: [number, string] | null;
  section_level: number;
  document_title: string;
  document_path: string | null;
  start_line: number | null;
  end_line: number | null;
  source_locations: SourceLocation[];
  protected: boolean;
}

export interface SourceLocation {
  source: string | null;
  byte_start: number | null;
  byte_end: number | null;
  line_start: number | null;
  line_end: number | null;
  page_start: number | null;
  page_end: number | null;
  sheet: string | null;
  row_start: number | null;
  row_end: number | null;
  column_start: number | null;
  column_end: number | null;
  json_path: string | null;
  element_id: string | null;
  bounding_box: [number, number, number, number] | null;
}

export interface SplitResponse {
  document: string;
  metadata: Record<string, unknown>;
  reference_definitions: Record<
    string,
    { destination: string; title: string }
  >;
  chunk_count: number;
  chunks: ChunkData[];
}

export interface BlockHandlingState {
  isolated?: boolean;
  split?: boolean;
  max_tokens?: number | null;
  repeat_header?: boolean;
}

export type TokenizerName = 'approx' | 'tiktoken' | 'transformers';

export type SplitterName =
  | 'sibling'
  | 'exact-sibling'
  | 'incremental-sibling'
  | 'subtree'
  | 'exact-subtree'
  | 'incremental-subtree'
  | 'section'
  | 'exact-section'
  | 'incremental-section'
  | 'record';

export interface SplitOptions {
  max_tokens: number;
  ideal_max_tokens_ratio: number;
  merge_below_ratio: number;
  skip_empty_sections: boolean;
  heading_sensitive: boolean;
  block_configs: Record<string, BlockHandlingState> | null;
  tokenizer: TokenizerName;
  splitter: SplitterName;
}

export interface CompareColumn {
  splitter: SplitterName;
  options: SplitOptions;
  result: SplitResponse | null;
  error: string | null;
  elapsedMs: number | null;
}

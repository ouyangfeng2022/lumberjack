export interface ChunkData {
  chunk_id: string;
  chunk_type: string;
  body: string;
  token_count: number;
  headings: [number, string][];
  section_level: number;
  document_title: string;
  document_path: string | null;
  start_line: number | null;
  end_line: number | null;
}

export interface SplitResponse {
  document: string;
  chunk_count: number;
  chunks: ChunkData[];
}

export interface BlockHandlingState {
  isolated?: boolean;
  split?: boolean;
  max_tokens?: number | null;
  repeat_header?: boolean;
}

export interface SplitOptions {
  max_tokens: number;
  ideal_max_tokens_ratio: number;
  merge_below_tokens: number | null;
  skip_empty_sections: boolean;
  recursive_split: boolean;
  block_configs: Record<string, BlockHandlingState> | null;
  tokenizer: string;
  splitter: string;
  document_title: string;
}

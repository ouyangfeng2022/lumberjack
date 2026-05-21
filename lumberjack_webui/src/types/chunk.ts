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

export interface SplitOptions {
  max_tokens: number;
  merge_below_tokens: number;
  overlap_tokens: number;
  retain_headings: boolean;
  include_common_headings: boolean;
  merge_small_chunks: boolean;
  isolate_front_matter: boolean;
  skip_empty_sections: boolean;
  split_oversized_blocks: string;
  disable_lheading: boolean;
  tokenizer: string;
  document_title: string;
}

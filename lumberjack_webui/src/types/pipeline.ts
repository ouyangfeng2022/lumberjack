export interface RawTextInfo {
  char_count: number;
  line_count: number;
  word_count: number;
  full_text: string;
}

export interface TokenData {
  type: string;
  tag: string;
  nesting: number;
  attrs: Record<string, string | number> | null;
  map: [number, number] | null;
  level: number;
  content: string;
  markup: string;
  info: string;
  block: boolean;
  hidden: boolean;
  children?: TokenData[];
}

export interface TokensStage {
  count: number;
  tokens: TokenData[];
}

export interface InlineData {
  kind: string;
  text: string;
  children: InlineData[];
  attrs: Record<string, unknown>;
}

export interface BlockData {
  kind: string;
  text: string;
  start_line: number | null;
  end_line: number | null;
  children: BlockData[];
  inlines: InlineData[];
  attrs: Record<string, unknown>;
}

export interface SectionData {
  level: number;
  title: string;
  path: [number, string][];
  blocks: BlockData[];
  children: SectionData[];
  index: number;
  start_line: number | null;
}

export interface ASTStage {
  document_title: string;
  root: SectionData;
  reference_definitions: Record<string, Record<string, string>>;
}

export interface EntryData {
  headings: [number, string][];
  body: string;
  section_level: number;
  start_line: number | null;
  end_line: number | null;
}

export interface ChunkDraftData {
  entries: EntryData[];
  token_count: number;
}

export interface SplitStage {
  entries: EntryData[];
  drafts: ChunkDraftData[];
  options: {
    max_tokens: number;
    min_tokens: number;
    overlap_tokens: number;
  };
}

export interface ChunksStage {
  document: string;
  chunk_count: number;
  chunks: {
    chunk_id: string;
    text: string;
    body: string;
    token_count: number;
    headings: [number, string][];
    section_level: number;
    document_title: string;
    document_path: string | null;
    start_line: number | null;
    end_line: number | null;
  }[];
}

export interface PipelineResponse {
  stage_1_raw: RawTextInfo;
  stage_2_tokens: TokensStage;
  stage_3_ast: ASTStage;
  stage_4_split: SplitStage;
  stage_5_chunks: ChunksStage;
}

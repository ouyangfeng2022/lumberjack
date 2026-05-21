const en = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown document splitter',
  tab_split: 'Split',
  tab_pipeline: 'Pipeline',
  view_tabs: 'Workspace view',
  btn_split: 'Start Split',
  btn_pipeline: 'Run Pipeline',
  btn_splitting: 'Splitting...',
  btn_running: 'Running...',
  html_title: 'Lumberjack - Markdown Splitter',
  panel_input_kicker: 'Source',
  panel_options_kicker: 'Control',
  panel_results_kicker: 'Output',
  panel_results_title: 'Split Results',
  result_budget_use: 'Largest chunk budget use',
  empty_split_title: 'Ready to split',
  empty_split_body: 'Paste Markdown or upload a file, tune the token budget, then run the splitter to preview chunked output.',
  empty_pipeline_title: 'Pipeline preview waits here',
  empty_pipeline_body: 'Run the pipeline view to inspect raw text, parser tokens, AST construction, split planning, and final chunks.',

  // Markdown Input
  md_label: 'Markdown Input',
  md_placeholder: 'Paste your Markdown here...',
  md_upload: 'Upload .md file',
  md_clear: 'Clear',
  md_text_mode: 'Editing pasted Markdown',
  md_file_ready: 'File upload will be submitted',

  // Split Options
  opts_label: 'Split Settings',
  opts_basic_section: 'Basic Settings',
  opts_strategy_section: 'Split Strategy',
  opts_max_tokens: 'Max tokens',
  opts_retain_headings: 'Retain headings',
  opts_include_common_headings: 'Include common headings',
  opts_show_advanced: 'Show advanced options',
  opts_hide_advanced: 'Hide advanced options',
  opts_merge_below_tokens: 'Merge below tokens',
  opts_overlap_tokens: 'Overlap tokens',
  opts_merge_small: 'Merge small chunks',
  opts_isolate_front_matter: 'Isolate front matter',
  opts_skip_empty_sections: 'Skip empty sections',
  opts_disable_lheading: 'Disable Setext headings',
  opts_tokenizer: 'Tokenizer',
  opts_tokenizer_simple: 'Simple',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_split_oversized: 'Split oversized blocks',
  opts_block_paragraph: 'Paragraph',
  opts_block_blockquote: 'Blockquote',
  opts_block_list: 'List',
  opts_block_table: 'Table',
  opts_block_code_block: 'Code block',
  opts_block_code_fence: 'Code fence',
  opts_block_html_block: 'HTML block',

  // Chunk Result
  chunk_tokens: '{{count}} tokens',
  chunk_lines: 'Lines {{from}}-{{to}}',

  // Chunk List
  chunks_count: '{{count}} chunk',
  chunks_count_plural: '{{count}} chunks',
  chunks_total_tokens: '{{count}} total tokens',

  // Pipeline View
  step_raw_text: 'Raw Text',
  step_tokens: 'Tokens',
  step_ast: 'AST',
  step_splitting: 'Splitting',
  step_chunks: 'Chunks',
  nav_previous: 'Previous',
  nav_next: 'Next',

  // Step Raw Text
  stats_characters: 'Characters',
  stats_lines: 'Lines',
  stats_words: 'Words',

  // Step Tokens
  tokens_produced_suffix: 'tokens produced by markdown-it parser',
  tok_col_index: '#',
  tok_col_type: 'Type',
  tok_col_tag: 'Tag',
  tok_col_nesting: 'Nesting',
  tok_col_content: 'Content',
  tok_col_lines: 'Lines',

  // Step AST
  ast_blocks: '{{count}} blocks',
  ast_children: '{{count}} children',

  // Step Split
  split_budget: 'Budget',
  split_tokens: 'tokens',
  split_overlap: 'Overlap',
  split_entries: 'Entries',
  split_draft_chunks: 'Draft chunks',
  split_over_budget: 'over budget',
  split_entry_label: 'Entry {{index}}',
  split_chunk_label: 'Chunk {{index}}',

  // Step Chunks
  step_chunks_label: 'Chunks',
  step_total_tokens: 'Total Tokens',
  step_document: 'Document',
};

export default en;

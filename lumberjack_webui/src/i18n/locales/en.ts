const en = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown document splitter',
  btn_split: 'Start Split',
  btn_splitting: 'Splitting...',
  html_title: 'Lumberjack - Markdown Splitter',
  panel_results_title: 'Split Results',
  panel_compare_title: 'Splitter Comparison',
  result_budget_use: 'Largest chunk budget use',
  empty_split_title: 'Ready to split',
  empty_split_body: 'Paste Markdown or upload a file, adjust the token budget, then run the splitter to preview chunked output.',

  // Samples
  sample_label: 'Load sample…',
  sample_technical: 'Technical guide',
  sample_table: 'Wide tables',
  sample_long_paragraph: 'Long paragraphs',
  sample_mixed: 'Mixed 中/EN',
  sample_code: 'Code heavy',

  // Compare mode
  compare_toggle: 'Compare splitters',
  compare_preset: 'Preset',
  compare_preset_topology: 'Topologies (incremental)',
  compare_preset_counting: 'Counting (section)',
  compare_preset_custom: 'Custom selection',
  compare_custom_hint: 'Pick at least two splitters to compare.',

  // Boundary map
  boundary_title: 'Chunk boundaries',
  boundary_uncovered: '{{count}} unassigned lines',
  boundary_truncated: 'Showing first lines of {{count}}.',
  boundary_show: 'Boundaries',
  boundary_hide: 'Hide boundaries',

  // Export / download
  export_title: 'Copy configuration',
  export_hide: 'Hide configuration',
  export_python: 'Python',
  export_cli: 'CLI',
  export_copy: 'Copy',
  export_copied: 'Copied!',
  download_json: 'JSON',
  download_jsonl: 'JSONL',

  // Markdown Input
  md_label: 'Markdown Input',
  md_placeholder: 'Paste your Markdown here...',
  md_upload: 'Upload .md file',
  md_clear: 'Clear',
  md_text_mode: 'Editing pasted Markdown',
  md_file_ready: 'File upload will be submitted',

  // Split Options
  opts_label: 'Split Settings',
  opts_basic_section: 'Basic',
  opts_strategy_section: 'Strategy',
  opts_max_tokens: 'Max tokens',
  opts_ideal_max_tokens_ratio: 'Ideal max ratio',
  opts_show_advanced: 'Show advanced options',
  opts_hide_advanced: 'Hide advanced options',
  opts_merge_below_ratio: 'Tail merge ratio (0 disables)',
  opts_skip_empty_sections: 'Skip empty sections',
  opts_heading_sensitive: 'Count headings toward the split budget',
  opts_splitter: 'Splitter',
  opts_splitter_sibling: 'Sibling packing',
  opts_splitter_exact_sibling: 'Sibling packing (exact)',
  opts_splitter_incremental_sibling: 'Sibling packing (incremental)',
  opts_splitter_subtree: 'Subtree',
  opts_splitter_exact_subtree: 'Subtree (exact)',
  opts_splitter_incremental_subtree: 'Subtree (incremental)',
  opts_splitter_section: 'Section',
  opts_splitter_exact_section: 'Section (exact)',
  opts_splitter_incremental_section: 'Section (incremental)',
  opts_splitter_record: 'Record packing',
  opts_counting_help: 'Tokenizers encode and count text; the splitter selects exact or incremental measurement.',
  opts_tokenizer: 'Tokenizer',
  opts_tokenizer_approx: 'Approx',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_tokenizer_transformers: 'Transformers',
  opts_block_handling: 'Block handling',
  opts_isolated: 'Isolated',
  opts_isolated_desc: 'Prevent block from merging with adjacent content',
  opts_nosplit: 'No split',
  opts_nosplit_desc: 'Keep block intact even if it exceeds token budget',
  opts_repeat_header: 'Repeat header',
  opts_repeat_header_desc: 'Repeat table header rows in every split table chunk',
  opts_block_paragraph: 'Paragraph',
  opts_block_blockquote: 'Blockquote',
  opts_block_list: 'List',
  opts_block_table: 'Table',
  opts_block_html_table: 'HTML Table',
  opts_block_code_block: 'Code block',
  opts_block_code_fence: 'Code fence',
  opts_block_html_block: 'HTML block',
  opts_block_front_matter: 'Front matter',

  // Chunk Result
  chunk_tokens: '{{count}} tokens',
  chunk_lines: 'Lines {{from}}-{{to}}',
  chunk_estimated: 'est. {{count}}',
  chunk_estimated_title:
    'Split-time estimate vs the authoritative final token count (Δ = relative error)',
  chunk_protected: 'protected',

  // Chunk List
  chunks_count: '{{count}} chunk',
  chunks_count_plural: '{{count}} chunks',
  chunks_total_tokens: '{{count}} total tokens',
  chunks_mean_error: 'Δ {{value}}% avg',
  chunks_mean_error_title: 'Mean relative error of split-time estimates',

  // Stats
  stats_characters: 'Characters',
  stats_lines: 'Lines',
};

export default en;

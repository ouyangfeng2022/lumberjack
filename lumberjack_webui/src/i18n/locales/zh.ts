const zh = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown 文档拆分器',
  tab_split: '拆分',
  tab_pipeline: '流水线',
  btn_split: '拆分文档',
  btn_pipeline: '运行流水线',
  btn_splitting: '拆分中...',
  btn_running: '运行中...',
  html_title: 'Lumberjack - Markdown 拆分器',

  // Markdown Input
  md_label: 'Markdown 输入',
  md_placeholder: '在此粘贴 Markdown...',
  md_upload: '上传 .md 文件',
  md_clear: '清除',

  // Split Options
  opts_label: '拆分选项',
  opts_max_tokens: '最大 Token 数',
  opts_retain_headings: '保留标题',
  opts_show_advanced: '+ 显示高级选项',
  opts_hide_advanced: '- 隐藏高级选项',
  opts_min_tokens: '最小 Token 数',
  opts_overlap_tokens: '重叠 Token 数',
  opts_merge_small: '合并小块',
  opts_tokenizer: '分词器',
  opts_tokenizer_simple: '简易',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_split_oversized: '拆分超大块',
  opts_block_paragraph: '段落',
  opts_block_blockquote: '引用块',
  opts_block_list: '列表',
  opts_block_table: '表格',
  opts_block_code_block: '代码块',
  opts_block_code_fence: '代码围栏',
  opts_block_html_block: 'HTML 块',

  // Chunk Result
  chunk_tokens: '{{count}} 个 token',
  chunk_lines: '第 {{from}}–{{to}} 行',
  chunk_show_full: '显示完整文本',
  chunk_show_body: '仅显示正文',

  // Chunk List
  chunks_count: '{{count}} 个块',
  chunks_total_tokens: '共 {{count}} 个 token',

  // Pipeline View
  step_raw_text: '原始文本',
  step_tokens: 'Token',
  step_ast: 'AST',
  step_splitting: '拆分',
  step_chunks: '块',
  nav_previous: '上一步',
  nav_next: '下一步',

  // Step Raw Text
  stats_characters: '字符',
  stats_lines: '行',
  stats_words: '词',

  // Step Tokens
  tokens_produced_suffix: '个 token（由 markdown-it 解析器生成）',
  tok_col_index: '#',
  tok_col_type: '类型',
  tok_col_tag: '标签',
  tok_col_nesting: '嵌套',
  tok_col_content: '内容',
  tok_col_lines: '行',

  // Step AST
  ast_blocks: '{{count}} 个块',
  ast_children: '{{count}} 个子节点',

  // Step Split
  split_budget: '预算',
  split_tokens: '个 token',
  split_overlap: '重叠',
  split_entries: '条目',
  split_draft_chunks: '草稿块',
  split_over_budget: '超出预算',
  split_entry_label: '条目 {{index}}',
  split_chunk_label: '块 {{index}}',

  // Step Chunks
  step_chunks_label: '块',
  step_total_tokens: '总 Token 数',
  step_document: '文档',
};

export default zh;

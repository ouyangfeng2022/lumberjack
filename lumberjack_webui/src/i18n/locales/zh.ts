const zh = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown 文档拆分器',
  tab_split: '拆分',
  tab_pipeline: '流水线',
  view_tabs: '工作区视图',
  btn_split: '开始拆分',
  btn_pipeline: '运行流水线',
  btn_splitting: '拆分中...',
  btn_running: '运行中...',
  html_title: 'Lumberjack - Markdown 拆分器',
  panel_input_kicker: 'Source',
  panel_options_kicker: 'Control',
  panel_results_kicker: 'Output',
  panel_results_title: '拆分结果',
  result_budget_use: '最大块预算占用',
  empty_split_title: '等待一次清晰拆分',
  empty_split_body: '粘贴 Markdown 或上传文件，调整词元预算后即可预览拆分结果。',
  empty_pipeline_title: '流水线预览在这里展开',
  empty_pipeline_body: '运行流水线视图后，可以检查原始文本、解析 token、AST、拆分计划和最终块。',

  // Markdown Input
  md_label: 'Markdown 输入',
  md_placeholder: '在这里粘贴 Markdown...',
  md_upload: '上传 .md 文件',
  md_clear: '清除',
  md_text_mode: '正在编辑粘贴文本',
  md_file_ready: '将提交已上传文件',

  // Split Options
  opts_label: '拆分设置',
  opts_basic_section: '基础设置',
  opts_strategy_section: '拆分策略',
  opts_max_tokens: '最大词元数',
  opts_retain_headings: '保留标题',
  opts_include_common_headings: '包含公共标题',
  opts_show_advanced: '显示高级选项',
  opts_hide_advanced: '隐藏高级选项',
  opts_merge_below_tokens: '低于此词元数时合并',
  opts_overlap_tokens: '重叠词元数',
  opts_merge_small: '合并小块',
  opts_isolate_front_matter: '独立首页元数据',
  opts_tokenizer: '分词器',
  opts_tokenizer_simple: '简单',
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
  chunk_tokens: '{{count}} 个词元',
  chunk_lines: '第 {{from}}-{{to}} 行',

  // Chunk List
  chunks_count: '{{count}} 个块',
  chunks_total_tokens: '共 {{count}} 个词元',

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
  stats_lines: '行数',
  stats_words: '词数',

  // Step Tokens
  tokens_produced_suffix: '个词元，由 markdown-it 解析器生成',
  tok_col_index: '#',
  tok_col_type: '类型',
  tok_col_tag: '标签',
  tok_col_nesting: '嵌套',
  tok_col_content: '内容',
  tok_col_lines: '行号',

  // Step AST
  ast_blocks: '{{count}} 个块',
  ast_children: '{{count}} 个子节点',

  // Step Split
  split_budget: '预算',
  split_tokens: '词元',
  split_overlap: '重叠',
  split_entries: '条目',
  split_draft_chunks: '草稿块',
  split_over_budget: '超出预算',
  split_entry_label: '条目 {{index}}',
  split_chunk_label: '块 {{index}}',

  // Step Chunks
  step_chunks_label: '块',
  step_total_tokens: '总词元数',
  step_document: '文档',
};

export default zh;

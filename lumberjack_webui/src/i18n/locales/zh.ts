const zh = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown 文档拆分器',
  btn_split: '开始拆分',
  btn_splitting: '拆分中...',
  html_title: 'Lumberjack - Markdown 拆分器',
  panel_input_kicker: 'Source',
  panel_options_kicker: 'Control',
  panel_results_kicker: 'Output',
  panel_results_title: '拆分结果',
  result_budget_use: '最大块预算占用',
  empty_split_title: '等待一次清晰拆分',
  empty_split_body: '粘贴 Markdown 或上传文件，调整词元预算后即可预览拆分结果。',

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
  opts_show_advanced: '显示高级选项',
  opts_hide_advanced: '隐藏高级选项',
  opts_merge_below_tokens: '低于此词元数时合并',
  opts_overlap_tokens: '重叠词元数',
  opts_merge_small: '合并小块',
  opts_isolate_front_matter: '独立首页元数据',
  opts_skip_empty_sections: '跳过空白章节',
  opts_disable_lheading: '禁用 Setext 标题',
  opts_splitter: '切分器',
  opts_splitter_default: '默认切分',
  opts_splitter_section: '章节切分',
  opts_splitter_recursive: '递归切分',
  opts_recursive_split: '递归拆分超大章节',
  opts_tokenizer: '分词器',
  opts_tokenizer_simple: '简单',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_split_oversized: '拆分超大块',
  opts_standalone_blocks: '独立块',
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

  // Step Raw Text (reused by input stats)
  stats_characters: '字符',
  stats_lines: '行数',
};

export default zh;

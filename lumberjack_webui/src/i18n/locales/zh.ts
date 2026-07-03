const zh = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown 文档拆分器',
  btn_split: '开始拆分',
  btn_splitting: '拆分中...',
  html_title: 'Lumberjack - Markdown 拆分器',
  panel_results_title: '拆分结果',
  result_budget_use: '最大块预算占用',
  empty_split_title: '等待拆分',
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
  opts_basic_section: '基础',
  opts_strategy_section: '策略',
  opts_max_tokens: '最大词元数',
  opts_ideal_max_tokens_ratio: '理想最大比例',
  opts_show_advanced: '显示高级选项',
  opts_hide_advanced: '隐藏高级选项',
  opts_merge_below_tokens: '低于此词元数时合并（留空禁用）',
  opts_skip_empty_sections: '跳过空白章节',
  opts_render_headings: '在每个块中包含章节标题',
  opts_splitter: '切分器',
  opts_splitter_recursive: '递归切分',
  opts_splitter_section: '章节切分',
  opts_tokenizer: '分词器',
  opts_tokenizer_approx: '估算字符',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_tokenizer_transformers: 'Transformers',
  opts_block_handling: '块处理策略',
  opts_isolated: '隔离',
  opts_isolated_desc: '阻止该块与相邻内容合并',
  opts_nosplit: '禁止拆分',
  opts_nosplit_desc: '即使超出词元预算也保持该块完整',
  opts_repeat_header: '重复表头',
  opts_repeat_header_desc: '表格拆分后在每个表格块中重复表头行',
  opts_block_paragraph: '段落',
  opts_block_blockquote: '引用块',
  opts_block_list: '列表',
  opts_block_table: '表格',
  opts_block_html_table: 'HTML 表格',
  opts_block_code_block: '代码块',
  opts_block_code_fence: '代码围栏',
  opts_block_html_block: 'HTML 块',
  opts_block_front_matter: '首页元数据',

  // Chunk Result
  chunk_tokens: '{{count}} 个词元',
  chunk_lines: '第 {{from}}-{{to}} 行',

  // Chunk List
  chunks_count: '{{count}} 个块',
  chunks_total_tokens: '共 {{count}} 个词元',

  // Stats
  stats_characters: '字符',
  stats_lines: '行数',
};

export default zh;

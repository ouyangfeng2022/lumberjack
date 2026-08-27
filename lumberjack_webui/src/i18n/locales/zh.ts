const zh = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown 文档拆分器',
  btn_split: '开始拆分',
  btn_splitting: '拆分中...',
  html_title: 'Lumberjack - Markdown 拆分器',
  panel_results_title: '拆分结果',
  panel_compare_title: '切分器对比',
  result_budget_use: '最大块预算占用',
  empty_split_title: '等待拆分',
  empty_split_body: '粘贴 Markdown 或上传文件，调整词元预算后即可预览拆分结果。',

  // Samples
  sample_label: '加载示例…',
  sample_technical: '技术文档',
  sample_table: '宽表格',
  sample_long_paragraph: '长段落',
  sample_mixed: '中英混合',
  sample_code: '代码密集',

  // Compare mode
  compare_toggle: '对比多个切分器',
  compare_preset: '预设',
  compare_preset_topology: '拓扑对比（增量计量）',
  compare_preset_counting: '计量对比（章节）',
  compare_preset_custom: '自选组合',
  compare_custom_hint: '至少选择两个切分器进行对比。',

  // Boundary map
  boundary_title: '块边界',
  boundary_uncovered: '{{count}} 行未归属',
  boundary_truncated: '仅显示 {{count}} 行中的前若干行。',
  boundary_show: '边界视图',
  boundary_hide: '收起边界',

  // Export / download
  export_title: '复制配置',
  export_hide: '收起配置',
  export_python: 'Python',
  export_cli: 'CLI',
  export_copy: '复制',
  export_copied: '已复制！',
  download_json: 'JSON',
  download_jsonl: 'JSONL',

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
  opts_merge_below_ratio: '尾块合并比例',
  opts_skip_empty_sections: '跳过空白章节',
  opts_heading_sensitive: '切分预算计入标题 Token',
  opts_splitter: '切分器',
  opts_splitter_sibling: '同级合并',
  opts_splitter_exact_sibling: '同级合并（精确计量）',
  opts_splitter_incremental_sibling: '同级合并（增量计量）',
  opts_splitter_subtree: '子树切分',
  opts_splitter_exact_subtree: '子树切分（精确计量）',
  opts_splitter_incremental_subtree: '子树切分（增量计量）',
  opts_splitter_section: '章节切分',
  opts_splitter_exact_section: '章节切分（精确计量）',
  opts_splitter_incremental_section: '章节切分（增量计量）',
  opts_splitter_record: '记录打包',
  opts_counting_help: 'tokenizer 只负责编码与计数；精确或增量计量由 splitter 决定。',
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
  chunk_estimated: '估 {{count}}',
  chunk_estimated_title: '切分时估算 vs 最终权威词元数（Δ 为相对误差）',
  chunk_protected: '受保护',

  // Chunk List
  chunks_count: '{{count}} 个块',
  chunks_total_tokens: '共 {{count}} 个词元',
  chunks_mean_error: '平均误差 {{value}}%',
  chunks_mean_error_title: '切分时估算的平均相对误差',

  // Stats
  stats_characters: '字符',
  stats_lines: '行数',
};

export default zh;

import type { SplitOptions, SplitResponse } from '../types/chunk';

export async function splitMarkdown(
  text: string | null,
  file: File | null,
  options: SplitOptions,
): Promise<SplitResponse> {
  const formData = new FormData();

  if (file) {
    formData.append('file', file);
  } else if (text) {
    formData.append('text', text);
  }

  formData.append('max_tokens', String(options.max_tokens));
  formData.append('merge_below_tokens', String(options.merge_below_tokens));
  formData.append('overlap_tokens', String(options.overlap_tokens));
  formData.append('render_common_headings', String(options.render_common_headings));
  formData.append('merge_small_chunks', String(options.merge_small_chunks));
  formData.append('isolate_front_matter', String(options.isolate_front_matter));
  formData.append('skip_empty_sections', String(options.skip_empty_sections));
  formData.append('recursive_split', String(options.recursive_split));
  formData.append('disable_lheading', String(options.disable_lheading));
  const blocks = options.split_oversized_blocks
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (!blocks.includes('paragraph')) {
    blocks.unshift('paragraph');
  }
  formData.append('split_oversized_blocks', blocks.join(','));
  formData.append('standalone_blocks', options.standalone_blocks);
  formData.append('tokenizer', options.tokenizer);
  formData.append('splitter', options.splitter);
  formData.append('document_title', options.document_title);

  const response = await fetch('/lumber/api/split', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed with status ${response.status}`);
  }

  return response.json();
}

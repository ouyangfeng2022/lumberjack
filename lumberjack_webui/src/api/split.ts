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
  formData.append('ideal_max_tokens_ratio', String(options.ideal_max_tokens_ratio));
  formData.append('merge_below_tokens', String(options.merge_below_tokens));
  formData.append('overlap_tokens', String(options.overlap_tokens));
  formData.append('merge_small_chunks', String(options.merge_small_chunks));
  formData.append('skip_empty_sections', String(options.skip_empty_sections));
  formData.append('recursive_split', String(options.recursive_split));
  formData.append('disable_lheading', String(options.disable_lheading));
  if (options.block_configs) {
    formData.append('block_configs', JSON.stringify(options.block_configs));
  }
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

import type { SplitOptions } from '../types/chunk';
import type { PipelineResponse } from '../types/pipeline';

export async function fetchPipeline(
  text: string | null,
  file: File | null,
  options: SplitOptions,
): Promise<PipelineResponse> {
  const formData = new FormData();

  if (file) {
    formData.append('file', file);
  } else if (text) {
    formData.append('text', text);
  }

  formData.append('max_tokens', String(options.max_tokens));
  formData.append('merge_below_tokens', String(options.merge_below_tokens));
  formData.append('overlap_tokens', String(options.overlap_tokens));
  formData.append('retain_headings', String(options.retain_headings));
  formData.append('include_common_headings', String(options.include_common_headings));
  formData.append('merge_small_chunks', String(options.merge_small_chunks));
  formData.append('isolate_front_matter', String(options.isolate_front_matter));
  const blocks = options.split_oversized_blocks
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (!blocks.includes('paragraph')) {
    blocks.unshift('paragraph');
  }
  formData.append('split_oversized_blocks', blocks.join(','));
  formData.append('tokenizer', options.tokenizer);
  formData.append('document_title', options.document_title);

  const response = await fetch('/lumber/api/pipeline', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed with status ${response.status}`);
  }

  return response.json();
}

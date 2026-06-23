import type { SplitOptions, SplitResponse } from '../types/chunk';

export async function splitMarkdown(
  text: string | null,
  file: File | null,
  options: SplitOptions,
): Promise<SplitResponse> {
  if (file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('max_tokens', String(options.max_tokens));
    formData.append('ideal_max_tokens_ratio', String(options.ideal_max_tokens_ratio));
    if (options.merge_below_tokens !== null) {
      formData.append('merge_below_tokens', String(options.merge_below_tokens));
    }
    formData.append('skip_empty_sections', String(options.skip_empty_sections));
    if (options.block_configs) {
      formData.append('block_configs', JSON.stringify(options.block_configs));
    }
    formData.append('tokenizer', options.tokenizer);
    formData.append('splitter', options.splitter);

    const response = await fetch('/lumber/api/split/file', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(error || `Request failed with status ${response.status}`);
    }

    return response.json();
  }

  const response = await fetch('/lumber/api/split/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: text ?? '',
      max_tokens: options.max_tokens,
      ideal_max_tokens_ratio: options.ideal_max_tokens_ratio,
      merge_below_tokens: options.merge_below_tokens,
      skip_empty_sections: options.skip_empty_sections,
      block_configs: options.block_configs,
      tokenizer: options.tokenizer,
      splitter: options.splitter,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed with status ${response.status}`);
  }

  return response.json();
}

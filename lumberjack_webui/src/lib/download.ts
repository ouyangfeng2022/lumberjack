import type { SplitResponse } from '../types/chunk';

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function safeName(title: string): string {
  const cleaned = title.trim().replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '');
  return cleaned.length > 0 ? cleaned.toLowerCase().slice(0, 60) : 'lumberjack';
}

export function downloadResultJson(result: SplitResponse): void {
  const blob = new Blob([JSON.stringify(result, null, 2)], {
    type: 'application/json',
  });
  triggerDownload(blob, `${safeName(result.document)}-result.json`);
}

export function downloadChunksJsonl(result: SplitResponse): void {
  const lines = result.chunks.map((chunk) => JSON.stringify(chunk)).join('\n');
  const blob = new Blob([lines], { type: 'application/x-ndjson' });
  triggerDownload(blob, `${safeName(result.document)}-chunks.jsonl`);
}

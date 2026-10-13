import type { SplitOptions, SplitResponse } from "../types/chunk";
import { resolvedFormat, type DocumentInput } from "../lib/formats";

async function readResponse(response: Response) {
  const body = await response.text();
  if (!response.ok) {
    let detail = body;
    try {
      const data = JSON.parse(body);
      detail =
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail ?? data);
    } catch {
      /* A proxy can return plain-text errors. */
    }
    throw new Error(
      "HTTP " + response.status + ": " + (detail || response.statusText),
    );
  }
  return JSON.parse(body);
}
export async function splitDocument(
  input: DocumentInput,
  options: SplitOptions,
  signal?: AbortSignal,
): Promise<SplitResponse> {
  if (input.file) {
    const form = new FormData();
    form.append("file", input.file);
    form.append("input_format", input.format);
    for (const [key, value] of Object.entries(options)) {
      if (value !== null)
        form.append(
          key,
          typeof value === "object" ? JSON.stringify(value) : String(value),
        );
    }
    return readResponse(
      await fetch("/lumber/api/split/file", {
        method: "POST",
        body: form,
        signal,
      }),
    );
  }
  return readResponse(
    await fetch("/lumber/api/split/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: input.text,
        input_format: resolvedFormat(input),
        ...options,
      }),
      signal,
    }),
  );
}
export async function getServiceInfo(
  signal?: AbortSignal,
): Promise<{ version: string; commit: string | null }> {
  const [health, version] = await Promise.all([
    fetch("/lumber/api/health", { signal }).then(readResponse),
    fetch("/lumber/api/version", { signal }).then(readResponse),
  ]);
  if (health.status !== "ok") throw new Error("Service unavailable");
  return version;
}

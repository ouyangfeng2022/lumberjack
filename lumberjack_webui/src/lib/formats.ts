export const FORMAT_EXTENSIONS = {
  markdown: "md markdown",
  html: "html htm",
  text: "txt text",
  log: "log",
  csv: "csv",
  tsv: "tsv",
  json: "json",
  jsonl: "jsonl ndjson",
  xml: "xml",
  yaml: "yaml yml",
  toml: "toml",
  sql: "sql",
  python: "py",
  javascript: "js mjs cjs",
  typescript: "ts",
  tsx: "tsx",
  bash: "sh bash",
  c: "c h",
  cpp: "cpp cc cxx hpp",
  csharp: "cs",
  go: "go",
  java: "java",
  kotlin: "kt kts",
  lua: "lua",
  php: "php",
  ruby: "rb",
  rust: "rs",
  swift: "swift",
  zig: "zig",
  notebook: "ipynb",
  docx: "docx",
  pdf: "pdf",
  epub: "epub",
  pptx: "pptx",
  ppt: "ppt",
  odp: "odp",
  eml: "eml",
  msg: "msg",
  mbox: "mbox",
  xlsx: "xlsx",
  sqlite: "sqlite sqlite3 db",
} as const;

export type InputFormat = keyof typeof FORMAT_EXTENSIONS;
export type FileFormat = InputFormat | "auto";
const BINARY_FORMATS = new Set<InputFormat>([
  "docx",
  "pdf",
  "epub",
  "pptx",
  "ppt",
  "odp",
  "eml",
  "msg",
  "mbox",
  "xlsx",
  "sqlite",
]);
export const FORMATS = Object.keys(FORMAT_EXTENSIONS) as InputFormat[];
export const TEXT_FORMATS = FORMATS.filter(
  (format) => !BINARY_FORMATS.has(format),
);
export const ACCEPTED_FILES = Object.values(FORMAT_EXTENSIONS)
  .flatMap((value) => value.split(" ").map((suffix) => "." + suffix))
  .join(",");

export function detectFormat(name: string): InputFormat {
  const suffix = name.split(".").at(-1)?.toLowerCase();
  return (
    FORMATS.find((format) =>
      (FORMAT_EXTENSIONS[format] as string).split(" ").includes(suffix ?? ""),
    ) ?? "markdown"
  );
}
export function isBinaryFormat(format: InputFormat): boolean {
  return BINARY_FORMATS.has(format);
}
export interface DocumentInput {
  text: string;
  file: File | null;
  format: FileFormat;
}
export function resolvedFormat(input: DocumentInput): InputFormat {
  return input.format === "auto"
    ? detectFormat(input.file?.name ?? "document.md")
    : input.format;
}
export function inputFilename(input: DocumentInput): string {
  return (
    input.file?.name ??
    "document." + FORMAT_EXTENSIONS[resolvedFormat(input)].split(" ")[0]
  );
}

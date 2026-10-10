import type { SplitterName } from "../types/chunk";

export const PRESET_SPLITTERS: Record<"topology" | "counting", SplitterName[]> =
  {
    topology: [
      "incremental-section",
      "incremental-sibling",
      "incremental-subtree",
    ],
    counting: ["incremental-section", "exact-section"],
  };

export const ALL_SPLITTERS: SplitterName[] = [
  "section",
  "incremental-section",
  "exact-section",
  "sibling",
  "incremental-sibling",
  "exact-sibling",
  "subtree",
  "incremental-subtree",
  "exact-subtree",
  "record",
];

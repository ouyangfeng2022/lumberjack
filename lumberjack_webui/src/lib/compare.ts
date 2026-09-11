import type { SplitterName } from '../types/chunk';

export type ComparePreset = 'topology' | 'counting' | 'custom';

export const PRESET_SPLITTERS: Record<
  Exclude<ComparePreset, 'custom'>,
  SplitterName[]
> = {
  topology: ['incremental-section', 'incremental-sibling', 'incremental-subtree'],
  counting: ['incremental-section', 'exact-section'],
};

export const ALL_SPLITTERS: SplitterName[] = [
  'section',
  'incremental-section',
  'exact-section',
  'sibling',
  'incremental-sibling',
  'exact-sibling',
  'subtree',
  'incremental-subtree',
  'exact-subtree',
  'record',
];

export function resolveCompareSplitters(
  preset: ComparePreset,
  customSplitters: SplitterName[],
): SplitterName[] {
  if (preset === 'custom') return customSplitters;
  return PRESET_SPLITTERS[preset];
}

import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import type { SectionData, BlockData } from '../types/pipeline';
import styles from './StepAST.module.css';

const LEVEL_COLORS: Record<number, string> = {
  0: '#64748b',
  1: '#3b82f6',
  2: '#6366f1',
  3: '#8b5cf6',
  4: '#ec4899',
};

function getLevelColor(level: number): string {
  return LEVEL_COLORS[Math.min(level, 4)] || '#ec4899';
}

function pathKey(path: [number, string][] | null): string {
  if (!path || path.length === 0) return 'root';
  return path.map(([l, t]) => `${l}:${t}`).join('/');
}

interface BlockCardProps {
  block: BlockData;
}

function BlockCard({ block }: BlockCardProps) {
  return (
    <div className={styles.blockCard}>
      <span className={styles.blockKind}>{block.kind}</span>
      {block.start_line != null && (
        <span className={styles.blockLines}>
          L{block.start_line}
          {block.end_line != null && block.end_line !== block.start_line && `-${block.end_line}`}
        </span>
      )}
      <div className={styles.blockPreview}>
        {block.text.length > 120 ? block.text.slice(0, 120) + '...' : block.text}
      </div>
    </div>
  );
}

interface TreeNodeProps {
  node: SectionData;
  depth: number;
}

function TreeNode({ node, depth }: TreeNodeProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(depth < 2);
  const toggle = useCallback(() => setExpanded((e) => !e), []);
  const hasContent = node.blocks.length > 0 || node.children.length > 0;
  const color = getLevelColor(node.level);

  return (
    <div className={styles.node} style={{ marginLeft: depth * 20 }}>
      <div className={styles.nodeHeader} onClick={hasContent ? toggle : undefined}>
        {hasContent && (
          <span className={`${styles.toggle} ${expanded ? styles.toggleOpen : ''}`}>▶</span>
        )}
        {node.level > 0 && (
          <span className={styles.levelBadge} style={{ background: `${color}18`, color }}>
            H{node.level}
          </span>
        )}
        <span className={styles.nodeTitle}>{node.title}</span>
        <span className={styles.nodeMeta}>
          {node.blocks.length > 0 && t('ast_blocks', { count: node.blocks.length })}
          {node.children.length > 0 && ` / ${t('ast_children', { count: node.children.length })}`}
          {node.start_line != null && ` / L${node.start_line}`}
        </span>
      </div>

      {expanded && (
        <div className={styles.nodeContent}>
          {node.blocks.map((block, i) => (
            <BlockCard key={i} block={block} />
          ))}
          {node.children.map((child) => (
            <TreeNode key={pathKey(child.path)} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

interface Props {
  data: { root: SectionData };
}

export default function StepAST({ data }: Props) {
  return (
    <div className={styles.tree}>
      <TreeNode node={data.root} depth={0} />
    </div>
  );
}

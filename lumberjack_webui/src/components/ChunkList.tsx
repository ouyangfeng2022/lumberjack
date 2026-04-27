import type { SplitResponse } from '../types/chunk';
import ChunkResult from './ChunkResult';
import styles from './ChunkList.module.css';

interface Props {
  result: SplitResponse;
}

export default function ChunkList({ result }: Props) {
  const totalTokens = result.chunks.reduce((sum, c) => sum + c.token_count, 0);

  return (
    <div className={styles.container}>
      <div className={styles.summary}>
        <h3 className={styles.title}>{result.document}</h3>
        <div className={styles.stats}>
          <span className={styles.stat}>
            {result.chunk_count} chunk{result.chunk_count !== 1 ? 's' : ''}
          </span>
          <span className={styles.stat}>{totalTokens} total tokens</span>
        </div>
      </div>
      <div className={styles.list}>
        {result.chunks.map((chunk, i) => (
          <ChunkResult key={chunk.chunk_id} chunk={chunk} index={i} />
        ))}
      </div>
    </div>
  );
}

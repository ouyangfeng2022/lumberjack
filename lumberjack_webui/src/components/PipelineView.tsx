import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PipelineResponse } from '../types/pipeline';
import StepRawText from './StepRawText';
import StepTokens from './StepTokens';
import StepAST from './StepAST';
import StepSplit from './StepSplit';
import StepChunks from './StepChunks';
import styles from './PipelineView.module.css';

const STEP_KEYS = ['step_raw_text', 'step_tokens', 'step_ast', 'step_splitting', 'step_chunks'] as const;

interface Props {
  data: PipelineResponse;
}

export default function PipelineView({ data }: Props) {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(0);

  const goPrev = () => setCurrentStep((s) => Math.max(0, s - 1));
  const goNext = () => setCurrentStep((s) => Math.min(STEP_KEYS.length - 1, s + 1));

  return (
    <div className={styles.container}>
      <div className={styles.stepper}>
        {STEP_KEYS.map((key, i) => (
          <div key={key} className={styles.stepItem}>
            {i > 0 && (
              <div className={`${styles.stepLine} ${i <= currentStep ? styles.stepLineDone : ''}`} />
            )}
            <div
              className={`${styles.stepCircle} ${
                i < currentStep
                  ? styles.stepCircleDone
                  : i === currentStep
                    ? styles.stepCircleActive
                    : ''
              }`}
            >
              {i < currentStep ? '✓' : i + 1}
            </div>
            <span
              className={`${styles.stepLabel} ${i <= currentStep ? styles.stepLabelActive : ''}`}
            >
              {t(key)}
            </span>
          </div>
        ))}
      </div>

      <div className={styles.content}>
        {currentStep === 0 && <StepRawText data={data.stage_1_raw} />}
        {currentStep === 1 && <StepTokens data={data.stage_2_tokens} />}
        {currentStep === 2 && <StepAST data={data.stage_3_ast} />}
        {currentStep === 3 && <StepSplit data={data.stage_4_split} />}
        {currentStep === 4 && <StepChunks data={data.stage_5_chunks} />}
      </div>

      <div className={styles.nav}>
        <button
          className={`${styles.navBtn} ${styles.navBtnPrev}`}
          disabled={currentStep === 0}
          onClick={goPrev}
        >
          {t('nav_previous')}
        </button>
        <span className={styles.stepIndicator}>
          {currentStep + 1} / {STEP_KEYS.length}
        </span>
        <button
          className={`${styles.navBtn} ${styles.navBtnNext}`}
          disabled={currentStep === STEP_KEYS.length - 1}
          onClick={goNext}
        >
          {t('nav_next')}
        </button>
      </div>
    </div>
  );
}

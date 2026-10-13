import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { splitDocument } from "./api/split";
import { BUILT_IN_SAMPLES } from "./samples";
import {
  DEFAULT_OPTIONS,
  validateOptions,
  type RunSnapshot,
} from "./lib/workspace";
import {
  isBinaryFormat,
  resolvedFormat,
  type DocumentInput,
} from "./lib/formats";
import type { CompareColumn, SplitOptions } from "./types/chunk";

export default function useWorkspace() {
  const { t } = useTranslation();
  const [input, setInput] = useState<DocumentInput>({
    text: BUILT_IN_SAMPLES.find((sample) => sample.id === "technical")!.text,
    file: null,
    format: "markdown",
  });
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const [revision, setRevision] = useState(0);
  const currentRevision = useRef(0);
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [plans, setPlans] = useState<SplitOptions[]>([
    DEFAULT_OPTIONS,
    { ...DEFAULT_OPTIONS, splitter: "sibling" },
  ]);
  const customPlans = useRef(false);
  const [planRevision, setPlanRevision] = useState(0);
  const [comparison, setComparison] = useState<{
    input: DocumentInput;
    revision: number;
    planRevision: number;
    columns: CompareColumn[];
  } | null>(null);
  const [busy, setBusy] = useState<"split" | "compare" | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const generation = useRef(0);
  const inputGeneration = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const cancel = () => {
    generation.current++;
    controller.current?.abort();
    setBusy(null);
  };
  useEffect(
    () => () => {
      generation.current++;
      inputGeneration.current++;
      controller.current?.abort();
    },
    [],
  );
  const invalidate = () => {
    cancel();
    currentRevision.current++;
    setRevision(currentRevision.current);
    setError("");
  };
  const updateInput = (next: DocumentInput) => {
    invalidate();
    setInput(next);
    setReading(false);
    const stamp = ++inputGeneration.current;
    if (!next.file || isBinaryFormat(resolvedFormat(next))) return;
    setReading(true);
    next.file
      .arrayBuffer()
      .then((bytes) => {
        const text = new TextDecoder("utf-8", { fatal: true })
          .decode(bytes)
          .replace(/^\uFEFF/, "");
        if (stamp === inputGeneration.current) setInput({ ...next, text });
      })
      .catch(() => {
        if (stamp === inputGeneration.current) setError(t("ws_decode_error"));
      })
      .finally(() => {
        if (stamp === inputGeneration.current) setReading(false);
      });
  };
  const updateOptions = (next: SplitOptions) => {
    invalidate();
    setOptions(next);
    if (!customPlans.current)
      setPlans([
        structuredClone(next),
        {
          ...structuredClone(next),
          splitter: next.splitter === "sibling" ? "section" : "sibling",
        },
      ]);
  };
  const updatePlans = (next: SplitOptions[]) => {
    customPlans.current = true;
    cancel();
    setPlans(next);
    setPlanRevision((value) => value + 1);
  };
  const execute = async (compare = false) => {
    if (
      reading ||
      (!input.file && !input.text.trim()) ||
      !(compare
        ? plans.length >= 2 && plans.every(validateOptions)
        : validateOptions(options))
    )
      return false;
    cancel();
    const token = generation.current;
    const abort = new AbortController();
    controller.current = abort;
    const snapshotInput = { ...input };
    const snapshotOptions = structuredClone(options);
    const snapshotRevision = currentRevision.current;
    setBusy(compare ? "compare" : "split");
    setError("");
    try {
      if (compare) {
        const columns = plans.map((plan, index): CompareColumn => ({
          id: String.fromCharCode(65 + index),
          splitter: plan.splitter,
          options: structuredClone(plan),
          result: null,
          error: null,
          elapsedMs: null,
        }));
        setComparison({
          input: snapshotInput,
          revision: snapshotRevision,
          planRevision,
          columns,
        });
        for (let index = 0; index < columns.length; index++) {
          if (generation.current !== token) return false;
          const start = performance.now();
          let column = columns[index];
          try {
            const result = await splitDocument(
              snapshotInput,
              column.options,
              abort.signal,
            );
            column = {
              ...column,
              result,
              elapsedMs: performance.now() - start,
            };
          } catch (cause) {
            if (generation.current !== token) return false;
            column = {
              ...column,
              error: cause instanceof Error ? cause.message : String(cause),
              elapsedMs: performance.now() - start,
            };
          }
          if (generation.current !== token) return false;
          columns[index] = column;
          setComparison({
            input: snapshotInput,
            revision: snapshotRevision,
            planRevision,
            columns: [...columns],
          });
        }
      } else {
        const start = performance.now();
        const result = await splitDocument(
          snapshotInput,
          snapshotOptions,
          abort.signal,
        );
        if (generation.current !== token) return false;
        setRun({
          input: snapshotInput,
          options: snapshotOptions,
          revision: snapshotRevision,
          result,
          elapsedMs: performance.now() - start,
        });
      }
      return true;
    } catch (cause) {
      if (generation.current === token)
        setError(cause instanceof Error ? cause.message : String(cause));
      return false;
    } finally {
      if (generation.current === token) setBusy(null);
    }
  };
  const adopt = (column: CompareColumn) => {
    if (
      !comparison ||
      comparison.revision !== revision ||
      comparison.planRevision !== planRevision ||
      !column.result ||
      busy
    )
      return;
    invalidate();
    const next = structuredClone(column.options);
    setOptions(next);
    setRun({
      input: comparison.input,
      options: next,
      revision: currentRevision.current,
      result: column.result,
      elapsedMs: column.elapsedMs ?? 0,
    });
  };
  return {
    input,
    options,
    revision,
    run,
    plans,
    comparison,
    planRevision,
    busy,
    reading,
    error,
    updateInput,
    updateOptions,
    updatePlans,
    execute,
    adopt,
    cancel,
  };
}

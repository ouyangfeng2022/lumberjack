import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import MarkdownInput from "./components/MarkdownInput";
import SplitOptions from "./components/SplitOptions";
import LanguageSwitcher from "./components/LanguageSwitcher";
import CompareResults from "./components/CompareResults";
import ConfigExport, { CopyButton } from "./components/ConfigExport";
import BoundaryMap from "./components/BoundaryMap";
import DocumentPreview from "./components/DocumentPreview";
import Dialog from "./components/Dialog";
import Icon from "./components/Icon";
import { getServiceInfo } from "./api/split";
import {
  downloadChunksJsonl,
  downloadResultJson,
  triggerDownload,
} from "./lib/download";
import { PRESET_SPLITTERS, ALL_SPLITTERS } from "./lib/compare";
import {
  budgetCount,
  chunkBudget,
  summarize,
  validateOptions,
} from "./lib/workspace";
import { configurationJson } from "./lib/exportConfig";
import { inputFilename, resolvedFormat } from "./lib/formats";
import { BUILT_IN_SAMPLES } from "./samples";
import useWorkspace from "./useWorkspace";
import styles from "./App.module.css";

type Page = "split" | "compare" | "export";
function hashPage(): Page {
  const value = window.location.hash.slice(1);
  return value === "compare" || value === "export" ? value : "split";
}
export default function App() {
  const { t, i18n } = useTranslation();
  const w = useWorkspace();
  const [page, setPage] = useState<Page>(hashPage);
  const [view, setView] = useState<"input" | "preview">("input");
  const [theme, setTheme] = useState(() =>
    localStorage.getItem("lumberjack_theme") === "light" ? "light" : "dark",
  );
  const [menu, setMenu] = useState(false);
  const navRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const [modal, setModal] = useState<
    "options" | "samples" | "detail" | "json" | null
  >(null);
  const [planIndex, setPlanIndex] = useState(0);
  const [selected, setSelected] = useState(0);
  const [service, setService] = useState<{
    status: "checking" | "online" | "offline";
    version?: string;
  }>({ status: "checking" });
  const [healthRetry, setHealthRetry] = useState(0);

  useEffect(() => {
    if (!menu) return;
    const trigger = menuRef.current;
    navRef.current?.querySelector<HTMLElement>("a")?.focus();
    return () => trigger?.focus();
  }, [menu]);
  useEffect(() => {
    const listener = () => {
      setPage(hashPage());
      setMenu(false);
    };
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("lumberjack_theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = i18n.language;
    document.title = t("ws_title");
  }, [i18n.language, t]);
  useEffect(() => {
    const controller = new AbortController();
    getServiceInfo(
      AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
    )
      .then((info) => setService({ status: "online", version: info.version }))
      .catch(() => {
        if (!controller.signal.aborted) setService({ status: "offline" });
      });
    return () => controller.abort();
  }, [healthRetry]);

  const navigate = (next: Page) => {
    window.location.assign("#" + next);
    setPage(next);
    setMenu(false);
  };
  const run = w.run;
  const stale = !!run && run.revision !== w.revision;
  const compareStale =
    !!w.comparison &&
    (w.comparison.revision !== w.revision ||
      w.comparison.planRevision !== w.planRevision);
  const chunk = run?.result.chunks[selected];
  const stats = run && summarize(run.result, run.options);
  const canRun =
    (!!w.input.file || !!w.input.text.trim()) &&
    !w.busy &&
    !w.reading &&
    (page === "compare"
      ? w.plans.length >= 2 && w.plans.every(validateOptions)
      : validateOptions(w.options));
  const select = (index: number) => setSelected(index);
  const execute = async () => {
    if (await w.execute(page === "compare")) {
      setSelected(0);
      if (page === "split") setView("preview");
    }
  };
  const openOptions = () => {
    setModal("options");
  };
  const detail = chunk && run && (
    <>
      <div className={styles.inspectorCard}>
        <div className={styles.toolbar}>
          <strong className={styles.chunkNumber}>
            #{String(selected + 1).padStart(2, "0")}
          </strong>
          {chunk.protected && (
            <span className={styles.warning}>{t("chunk_protected")}</span>
          )}
        </div>
        <div className={styles.meter}>
          <i
            style={{
              width:
                Math.min(
                  100,
                  (budgetCount(chunk, run.options) /
                    chunkBudget(chunk, run.options)) *
                    100,
                ) + "%",
              background:
                budgetCount(chunk, run.options) >
                chunkBudget(chunk, run.options)
                  ? "var(--warning)"
                  : "var(--primary)",
            }}
          />
        </div>
        <p
          className={
            budgetCount(chunk, run.options) > chunkBudget(chunk, run.options)
              ? styles.warning
              : styles.muted
          }
        >
          {budgetCount(chunk, run.options)} / {chunkBudget(chunk, run.options)}{" "}
          tokens
        </p>
        <dl className={styles.details}>
          <dt>{t("ws_heading_path")}</dt>
          <dd>
            {[
              ...chunk.ancestor_headings,
              ...(chunk.own_heading ? [chunk.own_heading] : []),
            ]
              .map(([, value]) => value)
              .join(" / ") || "—"}
          </dd>
          <dt>{t("ws_location")}</dt>
          <dd>
            {chunk.start_line != null
              ? "L" + chunk.start_line + "–L" + chunk.end_line
              : "—"}{" "}
            · {inputFilename(run.input)}
            {chunk.source_locations.map((location, index) => (
              <div key={index}>
                {[
                  location.page_start != null
                    ? t("ws_page") +
                      " " +
                      location.page_start +
                      (location.page_end !== location.page_start
                        ? "–" + location.page_end
                        : "")
                    : "",
                  location.sheet,
                  location.row_start != null
                    ? t("ws_row") +
                      " " +
                      location.row_start +
                      "–" +
                      location.row_end
                    : "",
                  location.json_path,
                  location.element_id,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            ))}
          </dd>
          <dt>{t("ws_block_type")}</dt>
          <dd>{chunk.chunk_type}</dd>
          <dt>{t("ws_body_headings")}</dt>
          <dd>
            {chunk.body_token_count} + {chunk.headings_token_count}
          </dd>
          <dt>{t("ws_estimated")}</dt>
          <dd>
            {chunk.estimated_token_count}{" "}
            {chunk.token_count > 0
              ? "(Δ " +
                Math.round(
                  ((chunk.estimated_token_count - chunk.token_count) /
                    chunk.token_count) *
                    100,
                ) +
                "%)"
              : ""}
          </dd>
        </dl>
        <div className={styles.toolbar}>
          <CopyButton
            key={chunk.chunk_id}
            text={chunk.body}
            label={t("ws_copy_content")}
          />
          <button
            aria-label={t("ws_chunk_json")}
            onClick={() => setModal("json")}
          >
            {"{ }"}
          </button>
        </div>
      </div>
      <h3>{t("ws_parameters")}</h3>
      <div className={styles.inspectorCard}>
        <dl className={styles.details}>
          <dt>max_tokens</dt>
          <dd>{run.options.max_tokens}</dd>
          <dt>tokenizer</dt>
          <dd>{run.options.tokenizer}</dd>
          <dt>splitter</dt>
          <dd>{run.options.splitter}</dd>
          <dt>{t("ws_counting")}</dt>
          <dd>
            {run.options.splitter.startsWith("exact-") ||
            run.options.splitter === "record"
              ? "exact"
              : "incremental"}
          </dd>
        </dl>
        <button className={styles.textButton} onClick={openOptions}>
          {t("ws_adjust")} ›
        </button>
      </div>
      <h3>{t("ws_statistics")}</h3>
      <div className={styles.inspectorCard}>
        <strong>
          {stats?.count} {t("ws_chunks")} · {stats?.total.toLocaleString()}{" "}
          tokens
        </strong>
        <p className={styles.muted}>
          {t("ws_largest")}: {stats?.largest} · {stats?.over} {t("ws_over")}
        </p>
      </div>
      <p className={styles.requestInfo}>
        POST /lumber/api/split/{run.input.file ? "file" : "text"} · 200 OK ·{" "}
        {Math.round(run.elapsedMs)} ms
      </p>
    </>
  );

  return (
    <div className={styles.workspace}>
      <aside
        ref={navRef}
        role={menu ? "dialog" : undefined}
        aria-modal={menu ? true : undefined}
        aria-label={t("ws_workspace")}
        className={styles.sidebar + " " + (menu ? styles.sidebarOpen : "")}
        onKeyDown={(event) => {
          if (!menu) return;
          if (event.key === "Escape") {
            setMenu(false);
            return;
          }
          if (event.key !== "Tab") return;
          const items =
            navRef.current!.querySelectorAll<HTMLElement>("a, button");
          const target = event.shiftKey ? items[0] : items[items.length - 1];
          if (document.activeElement === target) {
            event.preventDefault();
            (event.shiftKey ? items[items.length - 1] : items[0]).focus();
          }
        }}
      >
        <a
          className={styles.brand}
          href="#split"
          onClick={() => setMenu(false)}
        >
          <span className={styles.logo}>◎</span> Lumberjack
        </a>
        <span className={styles.navLabel}>{t("ws_workspace")}</span>
        <nav aria-label={t("ws_workspace")}>
          {(["split", "compare"] as const).map((name) => (
            <a
              key={name}
              href={"#" + name}
              aria-current={page === name ? "page" : undefined}
              onClick={() => navigate(name)}
            >
              <Icon name={name} />
              {t("ws_" + name)}
            </a>
          ))}
          <span className={styles.navLabel}>{t("ws_resources")}</span>
          <a
            href="#export"
            aria-current={page === "export" ? "page" : undefined}
            onClick={() => navigate("export")}
          >
            <Icon name="export" />
            {t("ws_export")}
          </a>
          <button
            onClick={() => {
              setMenu(false);
              setModal("samples");
            }}
          >
            <Icon name="samples" />
            {t("ws_samples")}
          </button>
        </nav>
        <div className={styles.sidebarBottom}>
          <button
            className={styles.serviceCard}
            onClick={() => {
              setService({ status: "checking" });
              setHealthRetry(healthRetry + 1);
            }}
            title={t("ws_retry")}
          >
            <strong>
              <i className={styles.statusDot} data-status={service.status} />
              {t("ws_service_" + service.status)}
            </strong>
            <small>
              {window.location.host}{" "}
              {service.version ? "· v" + service.version : ""}
            </small>
          </button>
          <div className={styles.toolbar}>
            <LanguageSwitcher />
            <button
              className={styles.themeButton}
              aria-label={t(theme === "dark" ? "ws_light" : "ws_dark")}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              <Icon name="sun" />
            </button>
          </div>
        </div>
      </aside>
      {menu && (
        <button
          className={styles.navBackdrop}
          onClick={() => setMenu(false)}
          aria-label={t("ws_close")}
        />
      )}
      <main className={styles.main} inert={menu}>
        <header className={styles.topbar}>
          <button
            ref={menuRef}
            className={styles.menuButton}
            onClick={() => setMenu(!menu)}
            aria-label={t("ws_menu")}
            aria-expanded={menu}
            aria-haspopup="dialog"
          >
            <Icon name="menu" />
          </button>
          <div className={styles.pageTitle}>
            <span className={styles.titleIcon}>
              <Icon name={page === "split" ? "doc" : page} />
            </span>
            <div>
              <h1>
                {page === "split" ? inputFilename(w.input) : t("ws_" + page)}
              </h1>
              <p>
                {page === "split"
                  ? resolvedFormat(w.input) +
                    " · " +
                    (w.input.file
                      ? (w.input.file.size / 1024).toFixed(1) + " KB"
                      : w.input.text.length + " " + t("stats_characters"))
                  : t("ws_" + page + "_subtitle")}
              </p>
            </div>
          </div>
          <div className={styles.topActions}>
            <span className={styles.endpoint}>
              <i className={styles.statusDot} data-status={service.status} />
              {window.location.host}
            </span>
            {page !== "export" ? (
              <>
                <button onClick={openOptions}>
                  {t(page === "compare" ? "ws_adjust_plans" : "ws_adjust")}
                </button>
                {w.busy ? (
                  <button onClick={w.cancel}>{t("ws_cancel")}</button>
                ) : (
                  <button
                    className={styles.primaryButton}
                    disabled={!canRun}
                    onClick={() => void execute()}
                  >
                    <Icon name={page === "compare" ? "compare" : "play"} />
                    {t(page === "compare" ? "ws_run_compare" : "ws_run_split")}
                  </button>
                )}
              </>
            ) : (
              <button
                className={styles.primaryButton}
                onClick={() =>
                  triggerDownload(
                    new Blob([configurationJson(w.options, w.input)], {
                      type: "application/json",
                    }),
                    "lumber.json",
                  )
                }
              >
                {t("ws_download_config")}
              </button>
            )}
          </div>
        </header>
        {(w.error ||
          (page === "split" && stale) ||
          (page === "compare" && compareStale)) && (
          <div
            role={w.error ? "alert" : "status"}
            className={w.error ? styles.error : styles.notice}
          >
            {w.error || t("ws_stale")}
          </div>
        )}
        {w.busy && (
          <div className={styles.progress} role="status">
            {t("btn_splitting")}
          </div>
        )}
        {page === "split" && (
          <>
            <div className={styles.viewTabs}>
              <div className={styles.tabs} role="tablist">
                <button
                  role="tab"
                  aria-selected={view === "input"}
                  onClick={() => setView("input")}
                >
                  {t("ws_input")}
                </button>
                <button
                  role="tab"
                  aria-selected={view === "preview"}
                  disabled={!run}
                  onClick={() => setView("preview")}
                >
                  {t("ws_preview")}
                </button>
              </div>
              {view === "preview" && chunk && (
                <button
                  className={styles.detailButton}
                  onClick={() => setModal("detail")}
                >
                  {t("ws_selected")} #{selected + 1}
                </button>
              )}
            </div>
            {view === "input" ? (
              <div className={styles.inputArea}>
                <MarkdownInput input={w.input} onChange={w.updateInput} />
              </div>
            ) : (
              run && (
                <div className={styles.previewLayout}>
                  <DocumentPreview
                    key={run.revision + ":" + run.elapsedMs}
                    run={run}
                    selected={selected}
                    onSelect={select}
                  />
                  <aside className={styles.inspector}>
                    <h3>{t("ws_selected")}</h3>
                    {detail}
                  </aside>
                </div>
              )
            )}
            {view === "preview" && run && (
              <BoundaryMap
                chunks={run.result.chunks}
                options={run.options}
                selected={selected}
                onSelect={select}
              />
            )}
          </>
        )}
        {page === "compare" &&
          (w.comparison ? (
            <CompareResults
              columns={w.comparison.columns}
              input={w.comparison.input}
              stale={compareStale}
              loading={!!w.busy}
              onAdopt={(column) => {
                w.adopt(column);
                setSelected(0);
                setView("preview");
                navigate("split");
              }}
            />
          ) : (
            <div className={styles.empty}>
              <Icon name="compare" />
              <h2>{t("ws_compare")}</h2>
              <p>{t("ws_compare_hint")}</p>
              <button onClick={openOptions}>{t("ws_adjust_plans")}</button>
            </div>
          ))}
        {page === "export" && (
          <>
            <div className={styles.exportLayout}>
              <aside className={styles.exportSummary}>
                <h3>{t("ws_parameters")}</h3>
                <pre>{configurationJson(w.options, w.input)}</pre>
                <h3>{t("ws_input")}</h3>
                <p>
                  {inputFilename(w.input)} · {resolvedFormat(w.input)}
                </p>
                <p className={styles.muted}>{t("ws_export_hint")}</p>
                {run && (
                  <div className={styles.downloads}>
                    <button onClick={() => downloadResultJson(run.result)}>
                      {t("ws_result_json")}
                    </button>
                    <button onClick={() => downloadChunksJsonl(run.result)}>
                      {t("ws_result_jsonl")}
                    </button>
                    {stale && (
                      <p className={styles.warning}>{t("ws_stale_download")}</p>
                    )}
                  </div>
                )}
              </aside>
              <ConfigExport options={w.options} input={w.input} />
            </div>
            <footer className={styles.envBar}>
              {t("ws_environment")} ·{" "}
              {service.version
                ? "v" + service.version
                : t("ws_service_" + service.status)}{" "}
              · /lumber/api/split/*
            </footer>
          </>
        )}
      </main>
      {modal === "options" && (
        <Dialog
          drawer
          title={t(page === "compare" ? "ws_adjust_plans" : "ws_adjust")}
          onClose={() => setModal(null)}
        >
          {page === "compare" && (
            <div className={styles.planControls}>
              <label>
                {t("compare_preset")}{" "}
                <select
                  aria-label={t("compare_preset")}
                  defaultValue=""
                  onChange={(event) => {
                    const names =
                      event.target.value === "topology"
                        ? PRESET_SPLITTERS.topology
                        : event.target.value === "counting"
                          ? PRESET_SPLITTERS.counting
                          : ([
                              w.options.splitter,
                              w.options.splitter === "sibling"
                                ? "section"
                                : "sibling",
                            ] as const);
                    w.updatePlans(
                      names.map((splitter) => ({
                        ...structuredClone(w.options),
                        splitter,
                      })),
                    );
                    setPlanIndex(0);
                  }}
                >
                  <option value="" disabled>
                    {t("compare_preset_custom")}
                  </option>
                  <option value="ab">A / B</option>
                  <option value="topology">
                    {t("compare_preset_topology")}
                  </option>
                  <option value="counting">
                    {t("compare_preset_counting")}
                  </option>
                </select>
              </label>
              <div className={styles.tabs}>
                {w.plans.map((_, index) => (
                  <button
                    key={index}
                    aria-pressed={planIndex === index}
                    onClick={() => setPlanIndex(index)}
                  >
                    {String.fromCharCode(65 + index)}
                  </button>
                ))}
                <button
                  aria-label={t("ws_add_plan")}
                  disabled={w.plans.length >= ALL_SPLITTERS.length}
                  onClick={() => {
                    w.updatePlans([...w.plans, structuredClone(w.options)]);
                    setPlanIndex(w.plans.length);
                  }}
                >
                  +
                </button>
                <button
                  aria-label={t("ws_remove_plan")}
                  disabled={w.plans.length <= 2}
                  onClick={() => {
                    w.updatePlans(
                      w.plans.filter((_, index) => index !== planIndex),
                    );
                    setPlanIndex(0);
                  }}
                >
                  −
                </button>
              </div>
            </div>
          )}
          <SplitOptions
            options={
              page === "compare"
                ? (w.plans[planIndex] ?? w.plans[0])
                : w.options
            }
            onChange={(next) =>
              page === "compare"
                ? w.updatePlans(
                    w.plans.map((plan, index) =>
                      index === planIndex ? next : plan,
                    ),
                  )
                : w.updateOptions(next)
            }
          />
          {!(page === "compare"
            ? w.plans.every(validateOptions)
            : validateOptions(w.options)) && (
            <p role="alert" className={styles.error}>
              {t("ws_invalid_options")}
            </p>
          )}
          <footer className={styles.dialogFooter}>
            <button
              className={styles.primaryButton}
              onClick={() => setModal(null)}
            >
              {t("ws_done")}
            </button>
          </footer>
        </Dialog>
      )}
      {modal === "samples" && (
        <Dialog title={t("ws_samples")} onClose={() => setModal(null)}>
          <div className={styles.sampleGrid}>
            {BUILT_IN_SAMPLES.map((sample) => (
              <button
                key={sample.id}
                onClick={() => {
                  w.updateInput({
                    file: null,
                    text: sample.text,
                    format: sample.format ?? "markdown",
                  });
                  setSelected(0);
                  setView("input");
                  navigate("split");
                  setModal(null);
                }}
              >
                <Icon name="doc" />
                <strong>{t(sample.labelKey)}</strong>
                <small>
                  {sample.format ?? "markdown"} · {sample.text.length}{" "}
                  {t("stats_characters")}
                </small>
              </button>
            ))}
          </div>
        </Dialog>
      )}
      {modal === "detail" && (
        <Dialog drawer title={t("ws_selected")} onClose={() => setModal(null)}>
          {detail}
        </Dialog>
      )}
      {modal === "json" && chunk && (
        <Dialog title={t("ws_chunk_json")} onClose={() => setModal(null)}>
          <CopyButton text={JSON.stringify(chunk, null, 2)} />
          <pre className={styles.json}>{JSON.stringify(chunk, null, 2)}</pre>
        </Dialog>
      )}
    </div>
  );
}

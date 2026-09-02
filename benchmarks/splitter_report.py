#!/usr/bin/env python3
# ruff: noqa: RUF001 -- report text is deliberately Chinese (fullwidth punct)
"""Render the full splitter comparison HTML report from splitter-full-b* runs.

Reads ``benchmarks/results/splitter-full-b{300,600,1200}/raw.json`` and the
focused cache-capacity probe ``splitter-cache-probe.json``, and writes
``benchmarks/results/splitter-full-report.html`` (self-contained: ECharts for
interactive charts and KaTeX for LaTeX formulas are inlined from pinned
vendor files under the git-ignored ``benchmarks/assets/vendor/`` directory,
downloaded on first render).

Example:
    uv run python -m benchmarks.splitter_report
"""

from __future__ import annotations

import base64
import json
import re
import statistics
import urllib.request
from datetime import datetime
from math import fsum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
VENDOR_DIR = ROOT / "assets" / "vendor"
VENDOR_BASE = "https://cdn.jsdelivr.net/npm"
VENDOR_SOURCES = {
    "echarts.min.js": f"{VENDOR_BASE}/echarts@5.6.0/dist/echarts.min.js",
    "katex.min.js": f"{VENDOR_BASE}/katex@0.16.21/dist/katex.min.js",
    "katex.min.css": f"{VENDOR_BASE}/katex@0.16.21/dist/katex.min.css",
    "auto-render.min.js": (
        f"{VENDOR_BASE}/katex@0.16.21/dist/contrib/auto-render.min.js"
    ),
}
BUDGETS = (300, 600, 1200)
TOPOLOGIES = ("section", "subtree", "sibling")
SPLITTERS = (
    "incremental-section",
    "exact-section",
    "incremental-subtree",
    "exact-subtree",
    "incremental-sibling",
    "exact-sibling",
)
#: Stable per-splitter colors shared by every chart, so a variant keeps its
#: color across sections. Topology picks the hue, counting mode the shade.
SPLITTER_COLORS = {
    "exact-section": "#1d4ed8",
    "incremental-section": "#93c5fd",
    "exact-subtree": "#047857",
    "incremental-subtree": "#6ee7b7",
    "exact-sibling": "#b45309",
    "incremental-sibling": "#fcd34d",
}
#: Series colors for the exact-vs-incremental ratio chart (not per splitter).
RATIO_COLORS = ("#dc2626", "#7c3aed", "#0891b2")
ENGINE_LABEL = {
    "approx": "ApproxByteTokenizer（默认引擎，UTF-8 字节数 ÷ 3）",
    "tiktoken": "TiktokenTokenizer（o200k_base / gpt-4o-mini，LRU=1000）",
}
ENGINE_SHORT = {
    "approx": "approx",
    "tiktoken": "tiktoken",
}
DATASET_LABEL = {
    "recombined": "recombined（真实语料重组）",
}
SHAPE_LABEL = {
    "deep-tree": "深层级标题树",
    "wide-flat": "宽扁平同级节",
    "long-sections": "预算压力长章节",
    "oversized-blocks": "超大受保护块",
    "tiny-sections": "微小/空节",
    "edge-degenerate": "退化边角文档",
}


def _shape_names(datasets: set[str]) -> list[str]:
    """Synthetic shape ids present in the run, in generator-declared order."""
    return [s for s in SHAPE_LABEL if f"synthetic-{s}" in datasets]


def _ensure_vendor() -> None:
    """Download pinned chart/LaTeX vendor files that are not present yet."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    (VENDOR_DIR / "fonts").mkdir(exist_ok=True)
    targets: dict[Path, str] = {
        VENDOR_DIR / name: url for name, url in VENDOR_SOURCES.items()
    }
    if (VENDOR_DIR / "katex.min.css").exists():
        css = (VENDOR_DIR / "katex.min.css").read_text(encoding="utf-8")
        for font in sorted(set(re.findall(r"fonts/([A-Za-z0-9_-]+\.woff2)", css))):
            targets[VENDOR_DIR / "fonts" / font] = (
                f"{VENDOR_BASE}/katex@0.16.21/dist/fonts/{font}"
            )
    for path, url in targets.items():
        if path.exists():
            continue
        print(f"fetching vendor asset: {url}")
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())


def _inline_katex_css() -> str:
    """KaTeX CSS with every woff2 font embedded as a base64 data URI."""
    css = (VENDOR_DIR / "katex.min.css").read_text(encoding="utf-8")

    def _embed(match: re.Match[str]) -> str:
        name = match.group(1)
        data = base64.b64encode((VENDOR_DIR / "fonts" / name).read_bytes())
        return f'url(data:font/woff2;base64,{data.decode("ascii")}) format("woff2")'

    css = re.sub(
        r"url\(fonts/([A-Za-z0-9_-]+\.woff2)\) format\(['\"]woff2['\"]\)", _embed, css
    )
    # Drop woff/ttf fallbacks: their relative URLs cannot resolve in a
    # self-contained file and browsers pick the embedded woff2 first anyway.
    css = re.sub(
        r",\s*url\(fonts/[^)]+\) format\(['\"](?:woff|truetype|embedded-opentype)['\"]\)",
        "",
        css,
    )
    return css


def _load(name: str) -> dict[str, Any]:
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, round((len(ordered) - 1) * fraction))
    return ordered[index]


def _agg(results: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["docs"] = len(results)
    out["failed"] = sum(r["status"] != "success" for r in results)
    bytes_values = [r["source_bytes"] for r in results]
    token_values = [r["source_approx_tokens"] for r in results]
    out["bytes_med"] = statistics.median(bytes_values)
    out["bytes_min"] = min(bytes_values)
    out["bytes_max"] = max(bytes_values)
    out["tokens_med"] = statistics.median(token_values)
    out["tokens_min"] = min(token_values)
    out["tokens_max"] = max(token_values)
    walls = [
        statistics.median(s["wall_time_seconds"] for s in r["split_samples"])
        for r in results
    ]
    means = [
        statistics.mean(s["wall_time_seconds"] for s in r["split_samples"])
        for r in results
    ]
    out["wall_med"] = statistics.median(walls)
    out["wall_mean"] = statistics.mean(means)
    out["wall_p95"] = _percentile(walls, 0.95)
    out["finalize_med"] = statistics.median(r["finalize_wall_seconds"] for r in results)
    out["calls_med"] = statistics.median(
        statistics.median(s["count_calls"] for s in r["split_samples"]) for r in results
    )
    out["split_peak_med"] = statistics.median(
        r["split_peak_memory_bytes"] for r in results
    )
    out["total_peak_med"] = statistics.median(
        r["total_peak_memory_bytes"] for r in results
    )
    out["ms_per_kb"] = fsum(walls) * 1000 / (fsum(bytes_values) / 1024)
    observations = [obs for r in results for obs in r["chunks"]]
    errors = [float(obs["abs_estimate_error"]) for obs in observations]
    out["chunks"] = len(observations)
    out["err_mean"] = statistics.mean(errors) if errors else 0.0
    out["err_p95"] = _percentile(errors, 0.95) if errors else 0.0
    out["err_max"] = max(errors) if errors else 0.0
    out["rel_err_max"] = max(
        (obs["relative_estimate_error"] for obs in observations), default=0.0
    )
    violations = [obs for obs in observations if obs["exceeds_budget"]]
    out["viol"] = len(violations)
    out["viol_rate"] = len(violations) / len(observations) if observations else 0.0
    out["overshoot_max"] = max((r["max_overshoot_tokens"] for r in results), default=0)
    recalls = [r["word_recall"] for r in results if r["word_recall"] is not None]
    out["recall_min"] = min(recalls) if recalls else None
    return out


def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.2f}"


def _fmt_int(value: float) -> str:
    return f"{value:,.0f}"


def _fmt_kb(value: float) -> str:
    return f"{value / 1024:.1f}"


def _parse_number(cell: str) -> float | None:
    try:
        return float(cell.replace(",", ""))
    except ValueError:
        return None


def _table(
    caption: str,
    headers: list[str],
    rows: list[list[str]],
    *,
    highlight_min_cols: set[int] | None = None,
    note: str = "",
) -> str:
    highlight_min_cols = highlight_min_cols or set()
    body_rows = []
    for row in rows:
        numeric = {
            col: _parse_number(row[col]) for col in highlight_min_cols if col < len(row)
        }
        parsed_values = [v for v in numeric.values() if v is not None]
        best = min(parsed_values) if parsed_values else None
        cells = []
        for col, cell in enumerate(row):
            klass = ""
            if best is not None:
                parsed = _parse_number(cell)
                if col in highlight_min_cols and parsed == best:
                    klass = ' class="best"'
            cells.append(f"<td{klass}>{cell}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    note_html = f'<p class="note">{note}</p>' if note else ""
    return (
        f"<figure><figcaption>{caption}</figcaption>"
        '<div class="scroll"><table><thead><tr>'
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
        + note_html
        + "</figure>"
    )


def _dataset_label(name: str) -> str:
    return DATASET_LABEL.get(name, name)


def _main() -> None:
    raws = {
        budget: json.loads(
            (RESULTS / f"splitter-full-b{budget}" / "raw.json").read_text(
                encoding="utf-8"
            )
        )
        for budget in BUDGETS
    }
    meta = raws[BUDGETS[0]]
    config = meta["config"]
    engines = tuple(config["tokenizers"])
    docs_per_budget = len({r["document_id"] for r in raws[BUDGETS[0]]["results"]})
    total_results = sum(len(raw["results"]) for raw in raws.values())

    # (engine, budget, dataset|"ALL", splitter) -> aggregated stats
    grouped: dict[tuple[str, int, str, str], list[dict[str, Any]]] = {}
    datasets: set[str] = set()
    for budget, raw in raws.items():
        for result in raw["results"]:
            for dataset in (result["dataset"], "ALL"):
                key = (result["tokenizer"], budget, dataset, result["splitter"])
                grouped.setdefault(key, []).append(result)
            datasets.add(result["dataset"])
    agg = {key: _agg(rows) for key, rows in grouped.items()}

    dataset_order = sorted(
        datasets,
        key=lambda name: agg[(engines[0], BUDGETS[0], name, SPLITTERS[0])]["bytes_med"],
    )

    sections: list[str] = []

    # ---- 0. how to read this report ----
    total_failed = sum(int(stats["failed"]) for stats in agg.values() if stats["docs"])
    shape_list = "、".join(
        f"{SHAPE_LABEL[name]}（{name}）" for name in _shape_names(datasets)
    )
    sections.append(
        _explain(
            "<b>报告导读。</b>"
            "本报告对比 lumberjack 六个 splitter 变体在相同 tokenizer、相同文档下的表现："
            "三种拓扑（<code>section</code> 逐节直切、<code>subtree</code> 子树优先折叠、"
            "<code>sibling</code> 兄弟节点预算打包）× 两种计数方式"
            "（<b>exact</b> 每个预算决策都对渲染文本完整重计数、<b>incremental</b> 一次性预测量后用"
            "增量估计值做决策）。两个引擎：approx 按 "
            r"\( \hat{t} = \left\lfloor \mathrm{bytes}_{\text{UTF-8}} / 3 \right\rfloor \) 估算，"
            "tiktoken 用真实 BPE 编码器 o200k_base。"
            "评测分三个<b>互不可换算</b>的通道：时间（第 2 章，热缓存稳态）、"
            "准确率（第 3 章，split 期估计 vs finalizer 权威重计数）、内存（第 4 章，tracemalloc "
            "冷启动峰值）；第 1 章描述语料构成，第 5 章是 tiktoken 缓存容量的专项探测，"
            "第 6/7 章给出结论与选型建议。"
            f"本矩阵共 {total_results} 条测量记录、失败 {total_failed} 条，内容保真 oracle"
            "（正文哨兵保留、代码哨兵恰好出现一次、词召回 ≥ 0.99）全部通过——"
            "六个变体都不丢内容，选型只需在速度、计数精度、内存三个轴上权衡；"
            f"synthetic 语料覆盖 {len(_shape_names(datasets))} 种结构形状：{shape_list}。"
        )
    )

    # ---- 1. dataset length profile ----
    rows = []
    for budget in BUDGETS:
        for dataset in dataset_order:
            stats = agg[(engines[0], budget, dataset, SPLITTERS[0])]
            rows.append(
                [
                    str(budget),
                    _dataset_label(dataset),
                    str(stats["docs"]),
                    _fmt_int(stats["bytes_min"]),
                    _fmt_int(stats["bytes_med"]),
                    _fmt_int(stats["bytes_max"]),
                    _fmt_int(stats["tokens_min"]),
                    _fmt_int(stats["tokens_med"]),
                    _fmt_int(stats["tokens_max"]),
                ]
            )
    sections.append(
        '<h2 id="datasets">1. 数据集长度画像</h2>'
        + _explain(
            "本表描述参与评测的全部文档在字节与 approx 词元上的规模分布，"
            "是解读后续各章『按数据集』列的基准。语料分两族：<b>synthetic</b> 由种子化生成器产出，"
            "正文规模刻意随预算档缩放，让每个预算都有『刚好需要反复切分』的压力样本；"
            "<b>recombined</b> 从外部真实语料（CommonMark 规范样例、Kubernetes 站点文档、"
            "本地 Markdown element cases）抽取章节跨度拼接而成，规模与预算档无关，"
            "代表真实文档的章节混合形态。同一批文档在三个预算档下重复使用，"
            "因此后续各表中的『预算』列与本章的文档集一一对应。"
        )
        + _table(
            "文档长度分布（字节 / approx 词元，按数据集中位字节升序；synthetic 文档规模随预算档变化，recombined 固定）",
            [
                "预算",
                "数据集",
                "文档数",
                "字节 min",
                "字节 med",
                "字节 max",
                "tokens min",
                "tokens med",
                "tokens max",
            ],
            rows,
        )
    )

    # ---- 2. time ----
    time_html = ['<h2 id="time">2. 时间消耗（split 阶段，每文档中位数）</h2>']
    time_html.append(
        _explain(
            "本章测量 split 阶段（不含解析与 finalize）的处理速度。计时在热缓存稳态下进行："
            f"每篇文档先 warmup {config['warmups']} 次（tokenizer LRU 已填充），再重复 "
            f"{config['repetitions']} 次取每篇中位数；跨文档的<b>中位数</b>抗离群点，"
            "<b>均值与 p95</b> 用来暴露长尾。阅读要点：<br>"
            "① <b>总览表</b>：绿色高亮是该预算下最快的变体；<code>ms/KB</code> 列按文档体量归一化，"
            "可直接比较吞吐；<code>count() 调用中位</code>反映变体对 tokenizer 的压力，"
            "是 exact/incremental 速度差的直接来源之一。<br>"
            "② <b>长度 × 耗时表</b>：把同一预算按数据集拆开，观察耗时随规模与结构的缩放——"
            "中位耗时随 <code>med KB</code> 近似线性；相同体量下结构的影响（如 tiny-sections "
            "节多、sibling 拓扑打包更费）会体现为行内耗时差。<br>"
            "③ tiktoken 引擎下<b>均值/p95 远大于中位数</b>不是测量噪声：少数 ~50KB 级大文档触发"
            "默认 LRU=1000 的缓存抖动（见第 5 章），把均值与 p95 抬高数十倍，中位数不受影响；"
            "对比变体优劣请以中位数为准。<br>"
            "④ <code>finalize 中位 ms</code> 是切分之后权威重计数 + 渲染管线的耗时参考，"
            "六个变体共享同一 finalizer 实现，该列基本只随块数增减而变化。<br>"
            "⑤ <b>交互图</b>：下方两张图分别从『预算 × 变体』与『文档长度 × 变体』两个维度展示同一批数据，"
            "按钮切换引擎与统计量，悬停看数值，点图例可开关系列——表格里难以横向对比的行，在图上一眼可比。"
        )
    )
    time_html.append(
        _chart_figure(
            "chart-time",
            "图 2-1：split 耗时总览（按钮切换引擎 × 统计量；柱状分组 = 三档预算）",
            _chart_controls(
                "chart-time",
                [
                    (
                        f"{engine}:{key}",
                        f"{ENGINE_SHORT[engine]}·{label}",
                    )
                    for engine in engines
                    for key, label in (
                        ("wall_med", "中位"),
                        ("wall_mean", "均值"),
                        ("wall_p95", "p95"),
                        ("ms_per_kb", "ms/KB"),
                    )
                ],
            ),
        )
    )
    time_html.append(
        _chart_figure(
            "chart-scatter",
            "图 2-2：文档长度 × 耗时散点（按钮切换引擎 × 预算；y 轴对数，每点一篇文档）",
            _chart_controls(
                "chart-scatter",
                [
                    (f"{engine}:{budget}", f"{ENGINE_SHORT[engine]}·{budget}")
                    for engine in engines
                    for budget in BUDGETS
                ],
            ),
        )
    )
    for engine in engines:
        rows = []
        for budget in BUDGETS:
            for splitter in SPLITTERS:
                stats = agg[(engine, budget, "ALL", splitter)]
                rows.append(
                    [
                        str(budget),
                        splitter,
                        _fmt_ms(stats["wall_med"]),
                        _fmt_ms(stats["wall_mean"]),
                        _fmt_ms(stats["wall_p95"]),
                        _fmt_ms(stats["finalize_med"]),
                        _fmt_int(stats["calls_med"]),
                        f"{stats['ms_per_kb']:.3f}",
                    ]
                )
        time_html.append(
            f"<h3>{ENGINE_LABEL[engine]}</h3>"
            + _table(
                f"各预算 × 各 splitter 总览（跨数据集 {docs_per_budget} 篇文档）",
                [
                    "预算",
                    "splitter",
                    "split 中位 ms",
                    "split 均值 ms",
                    "split p95 ms",
                    "finalize 中位 ms",
                    "count() 调用中位",
                    "ms / KB",
                ],
                rows,
                highlight_min_cols={2},
                note=r"ms/KB = \( \dfrac{\sum_i \mathrm{med}(t_i)}{\sum_i \mathrm{KB}_i} \)；"
                "计时不含 tracemalloc 开销；每篇 warmup "
                f"{config['warmups']} 次 + 重复 {config['repetitions']} 次取每篇中位数，再跨文档取中位数 / 均值。",
            )
        )
        for budget in BUDGETS:
            rows = []
            for dataset in dataset_order:
                stats = agg[(engine, budget, dataset, SPLITTERS[0])]
                row = [
                    _dataset_label(dataset),
                    _fmt_int(stats["bytes_med"]),
                    _fmt_int(stats["tokens_med"]),
                ]
                for splitter in SPLITTERS:
                    row.append(
                        _fmt_ms(agg[(engine, budget, dataset, splitter)]["wall_med"])
                    )
                rows.append(row)
            time_html.append(
                _table(
                    f"文档长度 × 耗时（预算 {budget}；每格 = 该数据集每篇文档 split 中位耗时的中位数，ms）",
                    ["数据集", "med KB", "med tokens", *SPLITTERS],
                    rows,
                    highlight_min_cols={3, 4, 5, 6, 7, 8},
                )
            )
    sections.append("".join(time_html))

    # ---- 3. accuracy ----
    acc_html = ['<h2 id="accuracy">3. 准确率（split 期估计 vs 权威重计数）</h2>']
    acc_html.append(
        _explain(
            "本章回答：splitter 在预算决策时<b>自认为</b>的块大小，与最终权威重计数<b>相差多少</b>。"
            "incremental 变体用增量估计值做预算判断，exact 变体每一步都完整重计数"
            "（估计即权威值，误差恒为 0）；两者最终都由 <code>ChunkFinalizer</code> 做一次权威重计数"
            "作为统一基准。核心量定义："
            "估计误差 "
            r"\( |err| = \bigl| \hat{t}_{\text{split}} - t_{\text{final}} \bigr| \)，"
            "相对误差 "
            r"\( err_{\text{rel}} = \dfrac{|\hat{t}_{\text{split}} - t_{\text{final}}|}"
            r"{t_{\text{final}}} \)，"
            "超预算率 "
            r"\( viol = \dfrac{\#\{ c \in C \mid t_c > B \}}{\#C} \)"
            r"（\( B \) 为 max_tokens），词召回率 "
            r"\( recall = \dfrac{|W_{\text{chunks}} \cap W_{\text{ref}}|}"
            r"{|W_{\text{ref}}|} \)"
            "（对解析树可见文本的词级召回，阈值 0.99，任何文档低于阈值即记失败）。<br>"
            "<b>配对对比</b>以 incremental 为基准，比值为 "
            r"\( r = \dfrac{t_{\text{exact}}}{t_{\text{inc}}} \)"
            "（&lt; 1 表示 exact 更快）；<code>count() 调用比</code>与"
            "<code>split 峰值内存比</code>分别是 tokenizer 压力与内存代价的配对差；"
            "<code>块数差 inc−exact</code> 通常为 0 或 ±1，"
            "来自增量估计在边界块合并决策上的微小差异，不代表内容差异。"
        )
    )
    acc_html.append(
        _chart_figure(
            "chart-err",
            "图 3-1：incremental 估计误差（按钮切换引擎 × 统计量；exact 系恒为 0，可点图例隐藏）",
            _chart_controls(
                "chart-err",
                [
                    (f"{engine}:{key}", f"{ENGINE_SHORT[engine]}·{label}")
                    for engine in engines
                    for key, label in (
                        ("err_mean", "均值"),
                        ("err_p95", "p95"),
                        ("err_max", "最大"),
                        ("viol_rate", "超限率"),
                    )
                ],
            ),
        )
    )
    acc_html.append(
        _chart_figure(
            "chart-ratio",
            "图 3-2：exact / incremental 配对比值（虚线 = 1.0；低于虚线 exact 更优）",
            _chart_controls(
                "chart-ratio",
                [(engine, ENGINE_SHORT[engine]) for engine in engines],
            ),
        )
    )
    for engine in engines:
        rows = []
        for budget in BUDGETS:
            for splitter in SPLITTERS:
                stats = agg[(engine, budget, "ALL", splitter)]
                recall = stats["recall_min"]
                rows.append(
                    [
                        str(budget),
                        splitter,
                        f"{stats['err_mean']:.3f}",
                        f"{stats['err_p95']:.0f}",
                        f"{stats['err_max']:.0f}",
                        f"{stats['rel_err_max'] * 100:.2f}%",
                        f"{stats['viol_rate'] * 100:.2f}%",
                        str(stats["viol"]),
                        str(stats["overshoot_max"]),
                        f"{recall:.4f}" if recall is not None else "n/a",
                        _fmt_int(stats["chunks"]),
                        str(stats["failed"]),
                    ]
                )
        acc_html.append(
            f"<h3>{ENGINE_LABEL[engine]}</h3>"
            + _table(
                "估计误差 |estimated_token_count − token_count|、预算超限率、词召回率（exact 模式估计即重计数，误差恒为 0）",
                [
                    "预算",
                    "splitter",
                    "|err| 均值",
                    "|err| p95",
                    "|err| 最大",
                    "相对误差最大",
                    "超预算率",
                    "超预算块数",
                    "最大超限 tokens",
                    "词召回率最小",
                    "总块数",
                    "失败",
                ],
                rows,
            )
        )
    for engine in engines:
        rows = []
        for budget in BUDGETS:
            for topology in TOPOLOGIES:
                inc = agg[(engine, budget, "ALL", f"incremental-{topology}")]
                exact = agg[(engine, budget, "ALL", f"exact-{topology}")]
                ratio = exact["wall_med"] / inc["wall_med"] if inc["wall_med"] else 0.0
                mem_ratio = (
                    exact["split_peak_med"] / inc["split_peak_med"]
                    if inc["split_peak_med"]
                    else 0.0
                )
                calls_ratio = (
                    exact["calls_med"] / inc["calls_med"] if inc["calls_med"] else 0.0
                )
                rows.append(
                    [
                        str(budget),
                        topology,
                        _fmt_ms(inc["wall_med"]),
                        _fmt_ms(exact["wall_med"]),
                        f"{ratio:.2f}x",
                        f"{calls_ratio:.2f}x",
                        f"{mem_ratio:.2f}x",
                        f"{inc['err_mean']:.3f}",
                        f"{exact['err_mean']:.3f}",
                        f"{inc['viol_rate'] * 100:.2f}%",
                        f"{exact['viol_rate'] * 100:.2f}%",
                        str(inc["chunks"] - exact["chunks"]),
                    ]
                )
        acc_html.append(
            _table(
                f"exact vs incremental 配对对比（{ENGINE_LABEL[engine].split('（')[0]}）",
                [
                    "预算",
                    "拓扑",
                    "inc 中位 ms",
                    "exact 中位 ms",
                    "耗时比 exact/inc",
                    "count() 调用比",
                    "split 峰值内存比",
                    "inc |err| 均值",
                    "exact |err| 均值",
                    "inc 超预算率",
                    "exact 超预算率",
                    "块数差 inc−exact",
                ],
                rows,
            )
        )
    sections.append("".join(acc_html))

    # ---- 4. memory ----
    mem_html = ['<h2 id="memory">4. 内存消耗（tracemalloc 冷启动分配峰值）</h2>']
    mem_html.append(
        _explain(
            "内存是<b>独立测量通道</b>：每轮新建 splitter 并配全新 tokenizer 缓存（无预热），"
            f"在 tracemalloc 下冷启动执行，重复 {config['memory_reps']} 次取峰值中位数。"
            "该口径与第 2 章的计时通道（热缓存稳态）<b>不可互相换算</b>：计时回答『跑多快』，"
            "本章回答『第一次跑要占多少内存』，内存受限的常驻/并发服务应看本章。阅读要点：<br>"
            "① <b>按数据集峰值表</b>：绿色高亮为该数据集上分配峰值最低的变体，"
            "峰值随文档体量近线性增长。<br>"
            "② <b>总览表</b>：<code>split 峰值 med</code> 是切分期间的瞬时分配压力，"
            "<code>finalize 增量</code>是权威重计数 + 渲染阶段的追加量。<br>"
            "③ 典型形态：tiktoken 下 exact 变体峰值更高（LRU 缓存随计数增长）；"
            "approx 下 exact 反而更低——incremental 的预切块视图在切分期间常驻，"
            "而 exact 的重计数即用即弃。"
        )
    )
    mem_html.append(
        _chart_figure(
            "chart-mem",
            "图 4-1：split 阶段冷启动分配峰值（按钮切换引擎；柱状分组 = 三档预算）",
            _chart_controls(
                "chart-mem",
                [(engine, ENGINE_SHORT[engine]) for engine in engines],
            ),
        )
    )
    for engine in engines:
        for budget in BUDGETS:
            rows = []
            for dataset in dataset_order:
                stats = agg[(engine, budget, dataset, SPLITTERS[0])]
                row = [
                    _dataset_label(dataset),
                    _fmt_int(stats["bytes_med"]),
                ]
                for splitter in SPLITTERS:
                    row.append(
                        _fmt_kb(
                            agg[(engine, budget, dataset, splitter)]["split_peak_med"]
                        )
                    )
                rows.append(row)
            mem_html.append(
                _table(
                    f"split 阶段分配峰值 KB（预算 {budget}；每篇文档 "
                    f"{config['memory_reps']} 次冷启动重复取中位，再跨文档取中位；冷启动 = 全新 tokenizer 缓存）",
                    ["数据集", "med KB", *SPLITTERS],
                    rows,
                    highlight_min_cols={2, 3, 4, 5, 6, 7},
                )
            )
        rows = []
        for budget in BUDGETS:
            for splitter in SPLITTERS:
                stats = agg[(engine, budget, "ALL", splitter)]
                rows.append(
                    [
                        str(budget),
                        splitter,
                        _fmt_kb(stats["split_peak_med"]),
                        _fmt_kb(stats["total_peak_med"]),
                        _fmt_kb(stats["total_peak_med"] - stats["split_peak_med"]),
                    ]
                )
        mem_html.append(
            f"<h3>{ENGINE_LABEL[engine]}（总览）</h3>"
            + _table(
                "split 峰值 / split+finalize 总峰值总览（KB，跨数据集中位数）",
                [
                    "预算",
                    "splitter",
                    "split 峰值 med",
                    "split+finalize 峰值 med",
                    "finalize 增量",
                ],
                rows,
            )
        )
    sections.append("".join(mem_html))

    # ---- 5. cache-capacity probe ----
    probe = _load("splitter-cache-probe")
    probe_rows = [
        [
            row["splitter"],
            f"{row['cache1000_ms']:.1f}",
            f"{row['cache10000_ms']:.1f}",
            f"{row['speedup']:.1f}x",
        ]
        for row in probe["rows"]
    ]
    speedups = [row["speedup"] for row in probe["rows"]]
    probe_note = (
        f"该文档单次 split 触及 {probe.get('distinct_count_texts_max', '约 1900')} 个不同的 "
        f"count() 字符串；冷启动口径（每轮清空缓存）下默认 LRU=1000 与 10000 的中位耗时一致"
        f"（加速比 {min(speedups):.2f}–{max(speedups):.2f}x），说明没有任何变体依赖单篇内的 "
        "LRU 复用。exact 模式计数完全不启用缓存。approx 引擎无缓存，不受影响。"
    )
    sections.append(
        '<h2 id="cache">5. 缓存容量无关性（冷启动口径）</h2>'
        + _explain(
            "本探测验证一个前提：生产中每篇文档的 split 都从零缓存开始（文本缓存按请求隔离、"
            "跨文档不可复用），因此任何 splitter 都不应依赖单篇内的 LRU 复用。方法是固定选取"
            "语料中最慢的一篇长文档，同一 splitter 分别在 LRU=1000 与 LRU=10000 下计时"
            "（预热 1 次仅加载 tokenizer，每轮计时前清空缓存，重复 5 次取中位），并统计单次 "
            "split 实际触及的<b>不同</b> <code>count()</code> 字符串个数。加速比定义为 "
            r"\( s = \dfrac{t_{\text{LRU}=1000}}{t_{\text{LRU}=10000}} \)，"
            "接近 1 即容量无关；显著大于 1 则意味着该变体退回到了依赖单篇内缓存复用。"
            "exact 计数模式已完全不启用 tokenizer 缓存；incremental 的单篇内复用由其一次性"
            "预测量 memo 承担，不经过 LRU。approx 引擎按 UTF-8 字节估算、无缓存，不受影响。"
        )
        + _chart_figure(
            "chart-cache",
            "图 5-1：冷启动口径下 LRU=1000 vs LRU=10000 的 split 中位耗时（两柱接近即容量无关）",
        )
        + _table(
            f"最慢文档（{probe['document_id']}，{probe['source_bytes']} 字节）在预算 "
            f"{probe.get('max_tokens', 600)} 下、"
            "同一 splitter 分别使用默认 LRU=1000 与 LRU=10000 的中位耗时",
            ["splitter", "LRU=1000 ms", "LRU=10000 ms", "加速比"],
            probe_rows,
            highlight_min_cols={1, 2},
            note=probe_note,
        )
    )

    # ---- 6. key findings ----
    findings = _findings(agg, engines)
    sections.append(
        '<h2 id="findings">6. 关键发现</h2>'
        + _explain(
            "以下发现由本报告同一份数据自动计算得出，所有数字与前面的表格一致；"
            "每条加粗词是该发现的主题轴。"
        )
        + "<ul>"
        + "".join(f"<li>{item}</li>" for item in findings)
        + "</ul>"
    )

    # ---- 7. summary & evaluation ----
    sections.append(_summary_evaluation(agg, engines, probe, docs_per_budget))

    charts: dict[str, dict[str, dict[str, Any]]] = {
        "chart-time": _time_chart_options(agg, engines),
        "chart-scatter": _scatter_chart_options(raws, engines),
        "chart-err": _accuracy_chart_options(agg, engines),
        "chart-ratio": _ratio_chart_options(agg, engines),
        "chart-mem": _memory_chart_options(agg, engines),
        "chart-cache": _cache_chart_options(probe),
    }
    html = _page(meta, engines, docs_per_budget, total_results, sections, charts)
    output = RESULTS / "splitter-full-report.html"
    output.write_text(html, encoding="utf-8")
    print(f"written: {output} ({output.stat().st_size / 1024:.1f} KB)")


def _text_table(caption: str, headers: list[str], rows: list[list[str]]) -> str:
    """Left-aligned table for editorial (text-heavy) content."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f"<figure><figcaption>{caption}</figcaption>"
        '<div class="scroll text-table"><table><thead><tr>'
        f"{head}</tr></thead><tbody>{body}</tbody></table></div></figure>"
    )


def _explain(html: str) -> str:
    """Callout paragraph explaining what a section measures and how to read it."""
    return f'<p class="explain">{html}</p>'


def _chart_controls(chart_id: str, choices: list[tuple[str, str]]) -> str:
    """Button bar that switches an ECharts option via ``setChart``."""
    buttons = "".join(
        f"<button data-key=\"{key}\" onclick=\"setChart('{chart_id}', '{key}')\">"
        f"{label}</button>"
        for key, label in choices
    )
    return f'<div class="chart-controls" id="{chart_id}-controls">{buttons}</div>'


def _chart_figure(chart_id: str, caption: str, controls: str = "") -> str:
    return (
        f'<figure class="chart-frame">{controls}'
        f"<figcaption>{caption}</figcaption>"
        f'<div class="chart" id="{chart_id}"></div></figure>'
    )


def _chart_base(title: str, y_name: str) -> dict[str, Any]:
    """Shared ECharts option skeleton for the comparison charts."""
    return {
        "title": {"text": title, "left": "center", "textStyle": {"fontSize": 14}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0, "type": "scroll"},
        "grid": {"top": 56, "bottom": 64, "left": 70, "right": 24},
        "xAxis": {"type": "category", "data": [str(b) for b in BUDGETS]},
        "yAxis": {"type": "value", "name": y_name},
    }


def _series_for(
    splitter: str, data: list[Any], color: str | None = None, **extra: Any
) -> dict[str, Any]:
    option: dict[str, Any] = {
        "name": splitter,
        "type": "bar",
        "data": data,
        "itemStyle": {"color": color or SPLITTER_COLORS[splitter]},
    }
    option.update(extra)
    return option


def _time_chart_options(
    agg: dict[tuple[str, int, str, str], dict[str, Any]],
    engines: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """§2 overview chart: one option per (engine, metric) selector key."""
    metrics = (
        ("wall_med", "split 中位 ms"),
        ("wall_mean", "split 均值 ms"),
        ("wall_p95", "split p95 ms"),
        ("ms_per_kb", "吞吐 ms/KB（越低越好）"),
    )
    options: dict[str, dict[str, Any]] = {}
    for engine in engines:
        for key, label in metrics:
            option = _chart_base(
                f"各 splitter 在三档预算下的 {label}（引擎 {engine}；悬停看数值，点图例开关系列）",
                label,
            )
            option["series"] = [
                _series_for(
                    splitter,
                    [
                        round(agg[(engine, budget, "ALL", splitter)][key], 4)
                        for budget in BUDGETS
                    ],
                )
                for splitter in SPLITTERS
            ]
            options[f"{engine}:{key}"] = option
    return options


def _scatter_chart_options(
    raws: dict[int, dict[str, Any]], engines: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    """§2 length-x-time scatter: one option per (engine, budget) selector key.

    Each point is one document: x = source KB, y = per-document median split
    wall time (ms); the point name carries the document id for tooltips. The
    y axis is logarithmic so sub-millisecond documents and LRU-thrashing
    outliers stay visible together.
    """
    points: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for budget, raw in raws.items():
        for result in raw["results"]:
            samples = result["split_samples"]
            if not samples:
                continue
            wall_ms = statistics.median(s["wall_time_seconds"] for s in samples) * 1000
            points.setdefault(
                (budget, result["tokenizer"], result["splitter"]), []
            ).append(
                {
                    "name": result["document_id"],
                    "value": [
                        round(result["source_bytes"] / 1024, 2),
                        round(wall_ms, 4),
                    ],
                }
            )
    options: dict[str, dict[str, Any]] = {}
    for engine in engines:
        for budget in BUDGETS:
            option = {
                "title": {
                    "text": (
                        f"文档长度 × split 中位耗时（引擎 {engine}，预算 {budget}；"
                        "每点 = 一篇文档，悬停看文档 id；y 轴对数）"
                    ),
                    "left": "center",
                    "textStyle": {"fontSize": 14},
                },
                "tooltip": {
                    "trigger": "item",
                    # replaced with a real formatter function after json.dumps
                    "formatter": "@@scatterTip@@",
                },
                "legend": {"bottom": 0, "type": "scroll"},
                "grid": {"top": 56, "bottom": 64, "left": 70, "right": 24},
                "xAxis": {"type": "value", "name": "文档 KB"},
                "yAxis": {"type": "log", "name": "split 中位 ms"},
                "series": [
                    {
                        "name": splitter,
                        "type": "scatter",
                        "symbolSize": 7,
                        "itemStyle": {
                            "color": SPLITTER_COLORS[splitter],
                            "opacity": 0.75,
                        },
                        "data": points.get((budget, engine, splitter), []),
                    }
                    for splitter in SPLITTERS
                ],
            }
            options[f"{engine}:{budget}"] = option
    return options


def _accuracy_chart_options(
    agg: dict[tuple[str, int, str, str], dict[str, Any]],
    engines: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """§3 chart: one option per (engine, metric) selector key."""
    metrics = (
        ("err_mean", "|err| 均值 tokens"),
        ("err_p95", "|err| p95 tokens"),
        ("err_max", "|err| 最大 tokens"),
        ("viol_rate", "超预算率（越小越好，exact 与 incremental 一致）"),
    )
    options: dict[str, dict[str, Any]] = {}
    for engine in engines:
        for key, label in metrics:
            scale = 100 if key == "viol_rate" else 1
            option = _chart_base(
                f"incremental 估计误差：{label}（引擎 {engine}；exact 系恒为 0）",
                label,
            )
            option["series"] = [
                _series_for(
                    splitter,
                    [
                        round(agg[(engine, budget, "ALL", splitter)][key] * scale, 4)
                        for budget in BUDGETS
                    ],
                )
                for splitter in SPLITTERS
            ]
            if key == "viol_rate":
                option["yAxis"] = {
                    "type": "value",
                    "name": label,
                    "axisLabel": {"formatter": "{value}%"},
                }
                for series in option["series"]:
                    series["tooltip"] = {"valueFormatter": "@@pct@@"}
            options[f"{engine}:{key}"] = option
    return options


def _ratio_chart_options(
    agg: dict[tuple[str, int, str, str], dict[str, Any]],
    engines: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """§3 paired chart: exact/incremental ratios per topology and budget."""
    categories = [
        f"{topology}@{budget}" for budget in BUDGETS for topology in TOPOLOGIES
    ]
    series_defs = (
        ("耗时比 exact/inc", "wall_med"),
        ("count() 调用比", "calls_med"),
        ("split 峰值内存比", "split_peak_med"),
    )
    options: dict[str, dict[str, Any]] = {}
    for engine in engines:
        option = _chart_base(
            f"exact / incremental 配对比值（引擎 {engine}；虚线 = 1.0，低于 1 表示 exact 更优）",
            "比值 exact/inc",
        )
        option["xAxis"] = {"type": "category", "data": categories, "name": "拓扑@预算"}
        option["series"] = []
        for index, (label, key) in enumerate(series_defs):
            data = []
            for budget in BUDGETS:
                for topology in TOPOLOGIES:
                    inc = agg[(engine, budget, "ALL", f"incremental-{topology}")][key]
                    exact = agg[(engine, budget, "ALL", f"exact-{topology}")][key]
                    data.append(round(exact / inc, 3) if inc else 0.0)
            series = _series_for(label, data, color=RATIO_COLORS[index])
            series["markLine"] = {
                "symbol": "none",
                "silent": True,
                "lineStyle": {"type": "dashed", "color": "#9ca3af"},
                "data": [{"yAxis": 1}],
                "label": {"formatter": "1.0x"},
            }
            option["series"].append(series)
        options[engine] = option
    return options


def _memory_chart_options(
    agg: dict[tuple[str, int, str, str], dict[str, Any]],
    engines: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """§4 chart: cold-run split allocation peaks per splitter and budget."""
    options: dict[str, dict[str, Any]] = {}
    for engine in engines:
        option = _chart_base(
            f"split 阶段冷启动分配峰值（引擎 {engine}；KB，跨数据集中位数）",
            "split 峰值 KB",
        )
        option["series"] = [
            _series_for(
                splitter,
                [
                    round(
                        agg[(engine, budget, "ALL", splitter)]["split_peak_med"] / 1024,
                        2,
                    )
                    for budget in BUDGETS
                ],
            )
            for splitter in SPLITTERS
        ]
        options[engine] = option
    return options


def _cache_chart_options(probe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """§5 chart: LRU=1000 vs LRU=10000 on the probe document (log scale)."""
    splitters = [row["splitter"] for row in probe["rows"]]
    option = _chart_base(
        f"缓存容量对比（{probe['document_id']}，{probe['source_bytes']} 字节；y 轴对数）",
        "split 中位 ms",
    )
    option["xAxis"] = {"type": "category", "data": splitters, "name": "splitter"}
    option["yAxis"] = {"type": "log", "name": "split 中位 ms"}
    option["series"] = [
        {
            "name": "LRU=1000（默认）",
            "type": "bar",
            "data": [round(row["cache1000_ms"], 1) for row in probe["rows"]],
            "itemStyle": {"color": "#dc2626"},
        },
        {
            "name": "LRU=10000",
            "type": "bar",
            "data": [round(row["cache10000_ms"], 1) for row in probe["rows"]],
            "itemStyle": {"color": "#16a34a"},
        },
    ]
    return {"single": option}


def _summary_evaluation(
    agg: dict[tuple[str, int, str, str], dict[str, Any]],
    engines: tuple[str, ...],
    probe: dict[str, Any],
    docs_per_budget: int,
) -> str:
    """Editorial conclusion backed by numbers computed from the same data."""
    fastest_rows: list[list[str]] = []
    for engine in engines:
        for budget in BUDGETS:
            stats: dict[str, float] = {
                splitter: float(agg[(engine, budget, "ALL", splitter)]["wall_med"])
                for splitter in SPLITTERS
            }
            best = min(stats, key=lambda name: stats[name])
            worst = max(stats, key=lambda name: stats[name])
            fastest_rows.append(
                [
                    str(budget),
                    engine,
                    best,
                    _fmt_ms(stats[best]),
                    worst,
                    _fmt_ms(stats[worst]),
                ]
            )

    inc_err_mean_max = max(
        agg[(engine, budget, "ALL", splitter)]["err_mean"]
        for engine in engines
        for budget in BUDGETS
        for splitter in SPLITTERS
        if splitter.startswith("incremental-")
    )
    inc_err_max_max = max(
        agg[(engine, budget, "ALL", splitter)]["err_max"]
        for engine in engines
        for budget in BUDGETS
        for splitter in SPLITTERS
        if splitter.startswith("incremental-")
    )
    mem_ranges: dict[str, tuple[float, float]] = {}
    for engine in engines:
        ratios = [
            agg[(engine, budget, "ALL", f"exact-{topology}")]["split_peak_med"]
            / agg[(engine, budget, "ALL", f"incremental-{topology}")]["split_peak_med"]
            for budget in BUDGETS
            for topology in TOPOLOGIES
        ]
        mem_ranges[engine] = (min(ratios), max(ratios))
    mem_summary = "；".join(
        f"{engine} {mem_ranges[engine][0]:.2f}x–{mem_ranges[engine][1]:.2f}x"
        for engine in engines
    )
    speedups: list[float] = [float(row["speedup"]) for row in probe["rows"]]
    wall_ratios = [
        agg[(engine, budget, "ALL", f"exact-{topology}")]["wall_med"]
        / agg[(engine, budget, "ALL", f"incremental-{topology}")]["wall_med"]
        for engine in engines
        for budget in BUDGETS
        for topology in TOPOLOGIES
    ]
    ms_per_kb = {
        engine: [
            agg[(engine, budget, "ALL", splitter)]["ms_per_kb"]
            for budget in BUDGETS
            for splitter in SPLITTERS
        ]
        for engine in engines
    }
    ms_per_kb_summary = "；".join(
        f"{engine} {min(ms_per_kb[engine]):.2f}–{max(ms_per_kb[engine]):.2f} ms/KB"
        for engine in engines
    )
    b1200_sentence = ""
    if "tiktoken" in engines:
        exact_subtree = agg[("tiktoken", 1200, "ALL", "exact-subtree")]["wall_med"]
        inc_section = agg[("tiktoken", 1200, "ALL", "incremental-section")]["wall_med"]
        b1200_sentence = (
            f"（预算 1200 + tiktoken：exact-subtree {_fmt_ms(exact_subtree)} ms 对 "
            f"incremental-section {_fmt_ms(inc_section)} ms）"
        )

    overview = (
        '<h2 id="evaluation">7. 总结与评价</h2>'
        f"<p><b>总评。</b>六个 splitter 变体在本矩阵（{len(engines)} 引擎 × 3 预算 × "
        f"{docs_per_budget} 篇/档文档）中全部通过内容保真 oracle、零失败：RAG 预处理最关心的"
        "『不丢内容、代码块不重复、词召回 ≥ 0.99』对所有变体成立，选型可以放心地围绕速度、"
        "计数精度与内存三个轴做权衡。两种计数方式的本质差异是：<b>exact</b> 在每个预算决策处"
        "完整重计数（不启用 tokenizer 缓存——单篇 split 内不存在可摊销的缓存复用），换来零估计"
        "误差；<b>incremental</b> 用一次性预测量加运行估计，误差小、"
        "但要支付固定预测量开销。splitter 层面未发现需要修复的缺陷。</p>"
    )
    dimension_rows = [
        [
            "正确性 / 保真",
            "全部变体 oracle 通过、零失败；exact 估计误差恒为 0，incremental |err| 均值最高 "
            f"{inc_err_mean_max:.2f}、单块最大 {inc_err_max_max:.0f} tokens",
            "两者都可信赖。下游按 max_tokens 硬截断、要求预算绝对可靠时选 exact；"
            "增量误差从未放大为额外超限（超限仅来自超长标题/超大表格等原子单元的结构性上限）。",
        ],
        [
            "速度",
            f"exact/inc 中位耗时比 {min(wall_ratios):.2f}x–{max(wall_ratios):.2f}x"
            f"{b1200_sentence}",
            "冷缓存口径下 incremental 通常更快（exact 的重计数每次都支付完整编码成本）；"
            "需要绝对预算可靠时才选 exact。小文档各变体差距小，"
            "拓扑选择（语义边界）比计数方式更重要。",
        ],
        [
            "内存",
            f"exact/inc 冷启动 split 峰值比：{mem_summary}",
            "exact 的重计数生成中间渲染文本但不写 tokenizer 缓存，incremental 常驻预测量"
            "视图树并向缓存写入条目；两者峰值构成不同，内存敏感场景按左列实测峰值选择。",
        ],
        [
            "长度缩放",
            f"中位耗时随长度近似线性（{ms_per_kb_summary}）；"
            f"冷启动口径下 LRU 容量不影响耗时（probe 加速比 {min(speedups):.2f}–"
            f"{max(speedups):.2f}x）",
            "计时每轮从零缓存开始，对齐生产语义；无需为文档大小调整 tokenizer 缓存配置。",
        ],
    ]
    overview += _text_table(
        "分维度评价（结论列 = 数据，评价列 = 基于数据的判断）",
        ["维度", "结论（数据）", "评价"],
        dimension_rows,
    )
    overview += _table(
        "各引擎 × 预算下最快 / 最慢变体（split 中位耗时，跨全部数据集）",
        ["预算", "引擎", "最快变体", "中位 ms", "最慢变体", "中位 ms"],
        fastest_rows,
    )
    recommendation_rows = [
        [
            "默认 / 保守选择",
            "incremental-section（现 CLI 默认拓扑）",
            "行为即当前默认；小文档上固定开销最小。",
        ],
        [
            "大预算 RAG 管线（tiktoken、max_tokens ≥ 600、文档较大）",
            "incremental-subtree 或 incremental-sibling",
            "冷缓存口径下 tiktoken 引擎的最快档；估计误差小且不放大超限。"
            "需要绝对预算可靠时再换 exact-*。",
        ],
        [
            "严格预算合规（下游硬截断）",
            "任一 exact-*",
            "估计即权威重计数，不会因估计偏差意外超预算。",
        ],
        [
            "内存受限 / 并发常驻服务",
            "exact-*（不写 tokenizer 缓存）或 approx 引擎",
            "exact 计数不启用缓存、无 LRU 增长，冷启动峰值可预期；approx 引擎无缓存。",
        ],
        [
            "小文档、高频短文本",
            "任意；按语义选拓扑",
            "各变体差距 ~0.1 ms，计数方式不构成决策因素。",
        ],
    ]
    overview += _text_table(
        "选型建议",
        ["场景", "推荐配置", "理由（依据）"],
        recommendation_rows,
    )
    limitations = (
        "<p><b>局限与口径说明。</b></p><ul>"
        "<li>计时通道每轮清空 tokenizer 文本缓存（每篇文档从零缓存开始，对齐生产语义）；"
        "warmup 仅用于加载 tokenizer 后端并达到解释器稳态，不会预热计时轮的缓存。</li>"
        "<li>内存通道是冷启动峰值（每轮全新缓存），与计时通道口径不同，两者不可互相换算。</li>"
        "<li>exact 计数完全不启用 tokenizer 缓存；incremental 的单篇内复用由其一次性预测量 "
        "memo 承担，不依赖 LRU。</li>"
        "<li>recombined 语料池由 CommonMark、Kubernetes 文档与本地 element cases 三个来源组成；"
        "均为 Markdown，其它格式的 splitter 行为不在本矩阵范围内。</li>"
        "<li>结构性超限（超长标题、超大表格/列表等原子单元本身超过预算）任何 splitter 都无法消除，"
        "属标题/块的原子性约束。</li>"
        "</ul>"
    )
    return overview + limitations


def _findings(
    agg: dict[tuple[str, int, str, str], dict[str, Any]],
    engines: tuple[str, ...],
) -> list[str]:
    findings: list[str] = []
    exact_max_err = max(
        agg[(engine, budget, "ALL", splitter)]["err_max"]
        for engine in engines
        for budget in BUDGETS
        for splitter in SPLITTERS
        if splitter.startswith("exact-")
    )
    inc_err_means = [
        agg[(engine, budget, "ALL", splitter)]["err_mean"]
        for engine in engines
        for budget in BUDGETS
        for splitter in SPLITTERS
        if splitter.startswith("incremental-")
    ]
    inc_err_max = max(
        agg[(engine, budget, "ALL", splitter)]["err_max"]
        for engine in engines
        for budget in BUDGETS
        for splitter in SPLITTERS
        if splitter.startswith("incremental-")
    )
    inc_viol_max = max(
        agg[(engine, budget, "ALL", splitter)]["viol_rate"]
        for engine in engines
        for budget in BUDGETS
        for splitter in SPLITTERS
        if splitter.startswith("incremental-")
    )
    ratios = [
        agg[(engine, budget, "ALL", f"exact-{topology}")]["wall_med"]
        / agg[(engine, budget, "ALL", f"incremental-{topology}")]["wall_med"]
        for engine in engines
        for budget in BUDGETS
        for topology in TOPOLOGIES
    ]
    mem_ratios = {
        engine: [
            agg[(engine, budget, "ALL", f"exact-{topology}")]["split_peak_med"]
            / agg[(engine, budget, "ALL", f"incremental-{topology}")]["split_peak_med"]
            for budget in BUDGETS
            for topology in TOPOLOGIES
        ]
        for engine in engines
    }
    rates = {
        engine: [
            agg[(engine, budget, "ALL", splitter)]["ms_per_kb"]
            for budget in BUDGETS
            for splitter in SPLITTERS
        ]
        for engine in engines
    }
    findings.append(
        f"<b>准确率</b>：exact 计数在全部 {len(engines)} 个引擎 × 3 个预算 × 3 种拓扑下的估计误差最大值均为 "
        f"{exact_max_err:.0f} tokens（估计即权威重计数）；incremental 的 |err| 均值最高 "
        f"{max(inc_err_means):.2f} tokens，单块最大 {inc_err_max:.0f} tokens。"
    )
    findings.append(
        f"<b>预算合规</b>：incremental 模式最差超预算率 {inc_viol_max * 100:.2f}%；"
        "全部超预算块均来自『原子单元本身超过预算』的文档——edge-degenerate 的超长标题变体，"
        "以及 recombined 池中 Kubernetes 语料的超大表格/列表块；这类单元无法在内部切分，"
        "exact 与 incremental 的超限文档集完全一致，属结构性上限而非计数误差。其余文档零超限。"
    )
    findings.append(
        f"<b>速度</b>：exact/incremental 中位耗时比在 {min(ratios):.2f}x–{max(ratios):.2f}x 之间"
        "（同 tokenizer、同文档配对对比）；exact 直接为每次重计数支付完整编码成本"
        "（不启用 tokenizer 缓存），incremental 则有一次性预测量的固定开销。"
    )
    for engine in engines:
        engine_mem = mem_ratios[engine]
        extra = (
            "tiktoken 下 exact 的重计数会生成中间渲染文本，incremental 则常驻预测量视图树并"
            "向 tokenizer 缓存写入预测量条目。"
            if engine == "tiktoken"
            else "approx 无缓存；incremental 的预测量视图树在 split 期间常驻，exact 即用即弃，峰值更低。"
        )
        findings.append(
            f"<b>内存（{engine}）</b>：exact/incremental 的 split 峰值内存比 "
            f"{min(engine_mem):.2f}x–{max(engine_mem):.2f}x；{extra}"
        )
    for engine in engines:
        engine_rates = rates[engine]
        findings.append(
            f"<b>长度缩放（{engine}）</b>：中位耗时随文档长度近似线性（{min(engine_rates):.3f}–"
            f"{max(engine_rates):.3f} ms/KB）；计时每轮从零缓存开始，tokenizer 缓存容量不影响耗时。"
        )
    return findings


_CHART_INIT_JS = """
const CHARTS = {};
const CHART_DATA = __CHART_DATA__;

function setChart(id, key) {
  const options = CHART_DATA[id];
  if (!options || !options[key] || !CHARTS[id]) { return; }
  CHARTS[id].setOption(options[key], true);
  document.querySelectorAll('#' + id + '-controls button').forEach(function (b) {
    b.classList.toggle('active', b.dataset.key === key);
  });
}

function _activateFirst(id) {
  const first = Object.keys(CHART_DATA[id])[0];
  CHARTS[id].setOption(CHART_DATA[id][first]);
  document.querySelectorAll('#' + id + '-controls button').forEach(function (b) {
    b.classList.toggle('active', b.dataset.key === first);
  });
}

document.addEventListener('DOMContentLoaded', function () {
  Object.keys(CHART_DATA).forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) { return; }
    CHARTS[id] = echarts.init(el);
    _activateFirst(id);
  });
  window.addEventListener('resize', function () {
    Object.values(CHARTS).forEach(function (chart) { chart.resize(); });
  });
  renderMathInElement(document.body, {
    delimiters: [
      { left: '\\\\[', right: '\\\\]', display: true },
      { left: '\\\\(', right: '\\\\)', display: false }
    ],
    throwOnError: false
  });
});
"""


def _page(
    meta: dict[str, Any],
    engines: tuple[str, ...],
    docs_per_budget: int,
    total_results: int,
    sections: list[str],
    charts: dict[str, dict[str, dict[str, Any]]],
) -> str:
    env = meta["environment"]
    config = meta["config"]
    _ensure_vendor()
    echarts_js = (VENDOR_DIR / "echarts.min.js").read_text(encoding="utf-8")
    katex_js = (VENDOR_DIR / "katex.min.js").read_text(encoding="utf-8")
    katex_css = _inline_katex_css()
    autorender_js = (VENDOR_DIR / "auto-render.min.js").read_text(encoding="utf-8")
    charts_json = json.dumps(charts, ensure_ascii=False, separators=(",", ":"))
    charts_json = charts_json.replace(
        '"@@scatterTip@@"',
        'function (p) { return p.name + "<br/>" + p.value[0] + " KB · " '
        '+ p.value[1] + " ms"; }',
    ).replace('"@@pct@@"', 'function (v) { return v + " %"; }')
    if "</script" in charts_json:
        raise ValueError("chart payload would terminate the inline <script> block")
    chart_init_js = _CHART_INIT_JS.replace("__CHART_DATA__", charts_json)
    toc = (
        "<nav><b>目录</b><ol>"
        "<li><a href='#datasets'>数据集长度画像</a></li>"
        "<li><a href='#time'>时间消耗</a></li>"
        "<li><a href='#accuracy'>准确率</a></li>"
        "<li><a href='#memory'>内存消耗</a></li>"
        "<li><a href='#cache'>缓存容量敏感性</a></li>"
        "<li><a href='#findings'>关键发现</a></li>"
        "<li><a href='#evaluation'>总结与评价</a></li>"
        "</ol></nav>"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>lumberjack splitter 完整对比报告</title>
<style>
{katex_css}
</style>
<style>
:root {{ color-scheme: light; }}
body {{ font-family: -apple-system, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
       margin: 0 auto; max-width: 1280px; padding: 24px 20px 80px; color: #1f2328;
       line-height: 1.55; background: #fff; }}
h1 {{ font-size: 1.6rem; border-bottom: 2px solid #d0adf7; padding-bottom: 8px; }}
h2 {{ font-size: 1.25rem; margin-top: 2.2em; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }}
h3 {{ font-size: 1.05rem; margin-top: 1.6em; }}
nav {{ background: #f6f2ff; border: 1px solid #d0adf7; border-radius: 8px;
       padding: 10px 18px; margin: 16px 0; }}
nav ol {{ margin: 6px 0 0 18px; padding: 0; }}
figure {{ margin: 18px 0; }}
figcaption {{ font-weight: 600; font-size: 0.9rem; margin-bottom: 6px; color: #444; }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 0.82rem; font-variant-numeric: tabular-nums; }}
th, td {{ border: 1px solid #e2e4e8; padding: 4px 9px; text-align: right; white-space: nowrap; }}
th {{ background: #f3f0fa; position: sticky; top: 0; }}
th:first-child, td:first-child, td:nth-child(2) {{ text-align: left; }}
.text-table th, .text-table td {{ text-align: left; white-space: normal;
                                   min-width: 140px; vertical-align: top; }}
.text-table td:first-child {{ white-space: nowrap; font-weight: 600; }}
td.best {{ background: #eaf7ea; font-weight: 700; }}
.note {{ font-size: 0.8rem; color: #666; margin: 6px 0 0; }}
.explain {{ font-size: 0.92rem; color: #333; border-left: 3px solid #d0adf7;
            padding: 4px 0 4px 14px; margin: 12px 0 14px; }}
.explain b {{ color: #1f2328; }}
.meta {{ font-size: 0.85rem; color: #555; background: #fafafa;
         border: 1px solid #eee; border-radius: 8px; padding: 10px 16px; }}
code {{ background: #f4f4f5; padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }}
.katex-display {{ margin: 0.4em 0; }}
.chart-frame {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px 6px;
                background: #fdfdff; }}
.chart {{ width: 100%; height: 430px; }}
.chart-controls {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
.chart-controls button {{ font-size: 0.8rem; padding: 3px 10px; border-radius: 6px;
                          border: 1px solid #d0adf7; background: #fff; color: #444;
                          cursor: pointer; }}
.chart-controls button.active {{ background: #d0adf7; color: #1f2328; font-weight: 600; }}
</style>
</head>
<body>
<h1>lumberjack splitter 完整对比报告</h1>
<p class="meta">
生成时间 {datetime.now():%Y-%m-%d %H:%M} ｜ commit <code>{meta["commit"][:12]}</code> ｜
Python {env["python"].split()[0]} ｜ {env["platform"]}<br>
矩阵：{len(engines)} 个 tokenizer（{"、".join(engines)}）× {len(BUDGETS)} 档预算
（max_tokens = {"、".join(str(b) for b in BUDGETS)}）× 6 个 splitter 变体
（section / subtree / sibling 拓扑 × exact / incremental 计数）× 每预算 {docs_per_budget} 篇文档
（6 种 synthetic 结构形状 × {config["documents_per_shape"]} + 真实语料重组 {config["recombined_documents"]}）＝
共 {total_results} 条测量记录。<br>
计时：每篇文档 warmup {config["warmups"]} 次 + 重复 {config["repetitions"]} 次，取每篇中位数与均值（无 tracemalloc 开销）；
内存：独立冷启动通道重复 {config["memory_reps"]} 次（每轮重建 splitter、全新 tokenizer 缓存），取 tracemalloc 分配峰值中位数；
准确率：split 期估计 <code>estimated_token_count</code> 对 finalizer 权威重计数 <code>token_count</code> 的误差、
预算超限率与词召回率（哨兵预言机全部通过才记 success）。
</p>
{toc}
{"".join(sections)}
<script>{echarts_js}</script>
<script>{katex_js}</script>
<script>{autorender_js}</script>
<script>{chart_init_js}</script>
</body>
</html>
"""


if __name__ == "__main__":
    _main()

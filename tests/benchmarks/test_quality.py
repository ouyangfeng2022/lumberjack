from benchmarks.contract import BenchmarkChunk
from benchmarks.metrics.quality import evaluate_quality


def test_quality_metrics_exclude_protected_oversized_chunk() -> None:
    report = evaluate_quality(
        [
            BenchmarkChunk(
                text="```python\n" + "x" * 100 + "\n```",
                token_count=101,
                protected=True,
                start_line=1,
                end_line=3,
            ),
            BenchmarkChunk(
                text="required text",
                token_count=5,
                estimated_token_count=6,
                start_line=5,
                end_line=5,
            ),
        ],
        max_tokens=10,
        required_content=("required text",),
        protected_content=("```python\n" + "x" * 100 + "\n```",),
    )

    assert report.values["content_recall"] == 1.0
    assert report.values["budget_violation_rate"] == 0.0
    assert report.values["block_break_rate"] == 0.0
    assert report.values["provenance_coverage"] == 1.0
    assert report.values["estimate_error"] == 0.2


def test_quality_metrics_report_specific_missing_content() -> None:
    report = evaluate_quality(
        [BenchmarkChunk(text="present", token_count=1)],
        max_tokens=10,
        required_content=("missing",),
    )

    assert report.values["content_recall"] == 0.0
    assert report.diagnostics == ["missing required content: 'missing'"]

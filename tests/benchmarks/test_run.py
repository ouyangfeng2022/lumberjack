from benchmarks.adapters.lumberjack import LumberjackAdapter
from benchmarks.contract import BenchmarkConfig
from benchmarks.run import run_benchmark


def test_native_benchmark_preserves_raw_samples_and_quality_results() -> None:
    report = run_benchmark(
        LumberjackAdapter(),
        BenchmarkConfig(max_tokens=30, warmups=0, repetitions=2),
    )

    assert report.schema_version == "1.0"
    assert report.dataset_version == "2026.08.27"
    assert len(report.results) == 36
    assert all(len(result.samples) == 2 for result in report.results)
    assert all("content_recall" in result.quality for result in report.results)
    assert all(result.quality["content_recall"] == 1.0 for result in report.results)
    assert any(
        sample.count_calls > 0 for result in report.results for sample in result.samples
    )

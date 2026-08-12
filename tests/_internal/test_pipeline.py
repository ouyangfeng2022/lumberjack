from lumberjack._internal.pipeline import split_source


def test_pipeline_applies_merge_below_ratio_to_section_splitter() -> None:
    source = "# A\n\n" + "x " * 200
    unmerged = split_source(
        source,
        splitter="exact-section",
        tokenizer="approx",
        max_tokens=40,
        ideal_max_tokens_ratio=0.5,
        merge_below_ratio=0.0,
    )
    merged = split_source(
        source,
        splitter="exact-section",
        tokenizer="approx",
        max_tokens=40,
        ideal_max_tokens_ratio=0.5,
        merge_below_ratio=0.5,
    )

    assert len(unmerged) == 7
    assert len(merged) == 6
    assert merged[-1].body == f"{unmerged[-2].body}\n\n{unmerged[-1].body}"

from nautilus_antlr_test import summarize, tool_failure


def _report(seeds=10, empty=0):
    return {"seeds": seeds, "empty_traces": empty, "timed_out_seeds": 0, "start_rule": "start"}


def test_all_empty_traces_are_a_tool_failure_not_zero_coverage():
    assert "no trace" in tool_failure(_report(seeds=10, empty=10))


def test_some_empty_traces_are_still_a_measurement():
    assert tool_failure(_report(seeds=10, empty=3)) is None


def test_summary_pools_rules_and_counts_tool_failures():
    results = [
        {"name": "a", "status": "ok", "coverage": 1.0, "visited_rules": 2, "total_rules": 2},
        {"name": "b", "status": "ok", "coverage": 0.5, "visited_rules": 6, "total_rules": 12},
        {"name": "c", "status": "error", "reason": "antlr4-parse produced no trace for any of the 5 seeds"},
        {"name": "d", "status": "error", "reason": "translation failed"},
        {"name": "e", "status": "skipped", "reason": "no parser rules found"},
    ]

    summary = summarize(results)

    assert summary["average_coverage"] == 0.75
    assert summary["rule_weighted_coverage"] == 8 / 14
    assert summary["grammars_antlr_tool_failed"] == 1
    assert summary["grammars_errored"] == 2
    assert summary["grammars_fully_covered"] == 1


def test_all_seeds_timing_out_is_a_tool_failure():
    report = {"seeds": 10, "empty_traces": 0, "timed_out_seeds": 10, "start_rule": "start"}
    assert "timed out on all" in tool_failure(report)


def test_some_timed_out_seeds_still_count_and_are_summarised():
    report = {"seeds": 10, "empty_traces": 0, "timed_out_seeds": 3, "start_rule": "start"}
    assert tool_failure(report) is None

    summary = summarize(
        [
            {"name": "a", "status": "ok", "coverage": 1.0, "visited_rules": 1, "total_rules": 1, "timed_out_seeds": 3},
            {"name": "b", "status": "ok", "coverage": 1.0, "visited_rules": 1, "total_rules": 1, "timed_out_seeds": 0},
        ]
    )
    assert summary["seeds_timed_out"] == 3
    assert summary["grammars_with_timed_out_seeds"] == 1

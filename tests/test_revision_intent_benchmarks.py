import pytest

from tests.revision_benchmark_cases import REVISION_BENCHMARK_CASES
from tests.revision_benchmark_runner import run_revision_intent_case


@pytest.mark.parametrize(
    "case",
    REVISION_BENCHMARK_CASES,
    ids=[case.name for case in REVISION_BENCHMARK_CASES],
)
def test_revision_intent_fallback_benchmark_cases(case):
    summary = run_revision_intent_case(case)

    assert summary["passed"] is True
    assert summary["detected_revision"] is case.expected_revision
    assert summary["detected_type"] == case.expected_type
    assert summary["detected_target"] == case.expected_target

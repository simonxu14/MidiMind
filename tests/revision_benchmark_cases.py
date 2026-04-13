from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RevisionBenchmarkCase:
    name: str
    message: str
    expected_revision: bool
    expected_type: Optional[str]
    expected_target: Optional[str]
    plan_variant: str = "default"
    workflow_stub: Optional[str] = None
    expected_part_ids: Optional[list[str]] = None
    expected_modified_parts: Optional[list[str]] = None


REVISION_BENCHMARK_CASES = [
    RevisionBenchmarkCase(
        name="add_horn",
        message="加一个圆号",
        expected_revision=True,
        expected_type="add",
        expected_target=None,
        workflow_stub="add_horn",
        expected_part_ids=["vn1", "piano", "vc", "hn"],
        expected_modified_parts=["hn"],
    ),
    RevisionBenchmarkCase(
        name="remove_cello",
        message="去掉大提琴",
        expected_revision=True,
        expected_type="remove",
        expected_target="vc",
        expected_part_ids=["vn1", "piano"],
        expected_modified_parts=["vc"],
    ),
    RevisionBenchmarkCase(
        name="modify_piano_density",
        message="把钢琴写密一点",
        expected_revision=True,
        expected_type="modify",
        expected_target="piano",
        workflow_stub="modify_piano_density",
        expected_part_ids=["vn1", "piano", "vc"],
        expected_modified_parts=["piano"],
    ),
    RevisionBenchmarkCase(
        name="modify_second_violin",
        message="把第二小提琴写密一点",
        expected_revision=True,
        expected_type="modify",
        expected_target="vn2",
        plan_variant="strings_duo",
        workflow_stub="modify_second_violin",
        expected_part_ids=["vn1", "vn2", "vc"],
        expected_modified_parts=["vn2"],
    ),
    RevisionBenchmarkCase(
        name="ambiguous_violin_without_ordinal",
        message="把小提琴写密一点",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
        plan_variant="strings_duo",
    ),
    RevisionBenchmarkCase(
        name="mixed_remove_then_add",
        message="把钢琴删掉换成圆号",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
    ),
    RevisionBenchmarkCase(
        name="ambiguous_multi_target_remove",
        message="把钢琴和大提琴都删掉",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
    ),
    RevisionBenchmarkCase(
        name="context_dependent_pronoun",
        message="继续让它更亮一点",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
    ),
    RevisionBenchmarkCase(
        name="group_level_strings",
        message="把弦乐更亮一点",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
        plan_variant="strings_duo",
    ),
    RevisionBenchmarkCase(
        name="modify_piano_with_constraint",
        message="钢琴再复杂一点，但别抢旋律",
        expected_revision=True,
        expected_type="modify",
        expected_target="piano",
        workflow_stub="modify_piano_density",
        expected_part_ids=["vn1", "piano", "vc"],
        expected_modified_parts=["piano"],
    ),
    RevisionBenchmarkCase(
        name="regenerate_new_style",
        message="换一个古典交响版本",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
    ),
    RevisionBenchmarkCase(
        name="regenerate_global_mood",
        message="整体更柔和一些",
        expected_revision=False,
        expected_type=None,
        expected_target=None,
    ),
]

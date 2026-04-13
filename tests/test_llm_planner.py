import pytest

from arranger.llm_planner import LLMPlanner


class TextBlock:
    def __init__(self, text, block_type="text"):
        self.text = text
        self.type = block_type


class Usage:
    def __init__(self, total_tokens=0, input_tokens=0, output_tokens=0):
        self.total_tokens = total_tokens
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class Response:
    def __init__(self, content=None, usage=None):
        self.content = content
        self.usage = usage


@pytest.fixture
def planner():
    return LLMPlanner(api_key="test-key")


def test_strip_json_fence_handles_plain_and_fenced_json(planner):
    assert planner._strip_json_fence('{"ok": true}') == '{"ok": true}'
    assert planner._strip_json_fence('```json\n{"ok": true}\n```') == '\n{"ok": true}\n'
    assert planner._strip_json_fence('```\n{"ok": true}\n```') == '\n{"ok": true}\n'


def test_extract_text_from_response_prefers_text_blocks(planner):
    response = Response(content=[TextBlock('{"plan": 1}')])
    assert planner._extract_text_from_response(response, 'parse failed') == '{"plan": 1}'


def test_parse_json_response_supports_fenced_payloads(planner):
    response = Response(content=[TextBlock('```json\n{"is_revision": true}\n```')])
    assert planner._parse_json_response(response, 'parse failed') == {"is_revision": True}


def test_response_tokens_used_falls_back_to_input_plus_output(planner):
    response = Response(content=[TextBlock('{"ok": true}')], usage=Usage(input_tokens=12, output_tokens=8))
    assert planner._response_tokens_used(response) == 20


def test_extract_text_from_response_raises_clear_error_on_bad_payload(planner):
    class BadResponse:
        @property
        def content(self):
            raise RuntimeError('boom')

    with pytest.raises(ValueError, match='parse failed'):
        planner._extract_text_from_response(BadResponse(), 'parse failed')


def test_call_llm_passes_expected_payload(planner, monkeypatch):
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return Response(content=[TextBlock('{"ok": true}')])

    class FakeClient:
        messages = FakeMessages()

    planner.client = FakeClient()

    response, duration_ms = planner._call_llm('system text', 'user text', 123)

    assert captured['model'] == 'MiniMax-M2.7'
    assert captured['max_tokens'] == 123
    assert captured['system'] == 'system text'
    assert captured['messages'] == [{'role': 'user', 'content': 'user text'}]
    assert isinstance(response, Response)
    assert duration_ms >= 0


from arranger.plan_schema import (
    Constraints,
    EnsembleConfig,
    HarmonyContext,
    MidiOutputConfig,
    MidiSpec,
    OutputConfig,
    PartSpec,
    TransformSpec,
    UnifiedPlan,
)


def make_plan(parts):
    return UnifiedPlan(
        schema_version="1.0",
        transform=TransformSpec(type="orchestration"),
        ensemble=EnsembleConfig(name="test", size="small", target_size=len(parts), parts=parts),
        harmony_context=HarmonyContext(),
        constraints=Constraints(),
        outputs=OutputConfig(midi=MidiOutputConfig(enabled=True, filename="test.mid")),
    )


def test_summarize_plan_parts_lists_each_part(planner):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
    ])

    summary = planner._summarize_plan_parts(plan)

    assert "- vn1: violin (melody)" in summary
    assert "- piano: piano (accompaniment)" in summary


def test_build_revision_analysis_prompt_includes_user_message_and_parts(planner):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
    ])

    prompt = planner._build_revision_analysis_prompt("加一个钢琴", plan)

    assert "加一个钢琴" in prompt
    assert "- vn1: violin (melody)" in prompt
    assert "请判断用户的意图是全新创作还是基于现有方案修改。" in prompt


def test_build_modify_part_prompt_contains_target_and_existing_plan_json(planner):
    plan = make_plan([
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
    ])

    prompt = planner._build_modify_part_prompt(plan, "piano", "把钢琴写得更密一些")

    assert '"id": "piano"' in prompt
    assert "需要修改的声部 ID: piano" in prompt
    assert "把钢琴写得更密一些" in prompt


class DummyAnalyzeResult:
    def __init__(self):
        self.tracks = []
        self.tempo = 120
        self.time_signature = "4/4"
        self.total_ticks = 1920
        self.ticks_per_beat = 480
        self.melody_candidates = []


def test_generate_plan_raises_instead_of_silent_fallback(planner, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(planner, "_call_llm", boom)

    with pytest.raises(Exception, match="LLM 编曲失败，请检查 API 配置或重试"):
        planner.generate_plan(DummyAnalyzeResult(), "写一个室内乐版本")


def test_raise_planner_error_preserves_context(planner):
    with pytest.raises(Exception, match="LLM 添加声部失败: bad input"):
        planner._raise_planner_error("LLM 添加声部失败", ValueError("bad input"))


def test_normalize_revision_intent_infers_target_part_from_instrument(planner):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
    ])

    intent = planner._normalize_revision_intent(
        {
            "is_revision": True,
            "revision_type": "modify",
            "instruction": "把钢琴写得更密一些",
        },
        "把钢琴写得更密一些",
        plan,
    )

    assert intent.is_revision is True
    assert intent.revision_type == "modify"
    assert intent.target_part_id == "piano"


def test_normalize_revision_intent_downgrades_modify_without_target(planner):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
    ])

    intent = planner._normalize_revision_intent(
        {
            "is_revision": True,
            "revision_type": "modify",
            "instruction": "整体更柔和一些",
        },
        "整体更柔和一些",
        plan,
    )

    assert intent.is_revision is False
    assert intent.revision_type is None
    assert intent.target_part_id is None


def test_analyze_revision_intent_fallback_uses_message_heuristics(planner, monkeypatch):
    plan = make_plan([
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
    ])

    monkeypatch.setattr(planner, "_call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm down")))

    intent = planner.analyze_revision_intent("把钢琴写密一点", plan)

    assert intent.is_revision is True
    assert intent.revision_type == "modify"
    assert intent.target_part_id == "piano"


def test_infer_revision_target_part_id_supports_ordinal_string_parts(planner):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="vn2", name="Violin II", role="inner_voice", instrument="violin", midi=MidiSpec(channel=1, program=40)),
    ])

    assert planner._infer_revision_target_part_id("把第二小提琴写密一点", plan) == "vn2"


def test_normalize_revision_intent_downgrades_mixed_actions(planner):
    plan = make_plan([
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
    ])

    intent = planner._normalize_revision_intent(
        {
            "is_revision": True,
            "revision_type": "remove",
            "instruction": "把钢琴删掉换成圆号",
        },
        "把钢琴删掉换成圆号",
        plan,
    )

    assert intent.is_revision is False
    assert intent.revision_type is None
    assert intent.target_part_id is None


def test_infer_candidate_target_part_ids_returns_multiple_matches_for_multi_target_message(planner):
    plan = make_plan([
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
        PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=2, program=42)),
    ])

    assert planner._infer_candidate_target_part_ids("把钢琴和大提琴都删掉", plan) == ["piano", "vc"]


def test_analyze_revision_intent_fallback_downgrades_multi_target_message(planner, monkeypatch):
    plan = make_plan([
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
        PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=2, program=42)),
    ])

    monkeypatch.setattr(planner, "_call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm down")))

    intent = planner.analyze_revision_intent("把钢琴和大提琴都删掉", plan)

    assert intent.is_revision is False
    assert intent.revision_type is None
    assert intent.target_part_id is None


def test_analyze_revision_intent_fallback_downgrades_same_instrument_without_ordinal(planner, monkeypatch):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="vn2", name="Violin II", role="inner_voice", instrument="violin", midi=MidiSpec(channel=1, program=40)),
    ])

    monkeypatch.setattr(planner, "_call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm down")))

    intent = planner.analyze_revision_intent("把小提琴写密一点", plan)

    assert intent.is_revision is False
    assert intent.revision_type is None
    assert intent.target_part_id is None


def test_analyze_revision_intent_fallback_keeps_single_target_with_extra_constraint(planner, monkeypatch):
    plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
    ])

    monkeypatch.setattr(planner, "_call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm down")))

    intent = planner.analyze_revision_intent("钢琴再复杂一点，但别抢旋律", plan)

    assert intent.is_revision is True
    assert intent.revision_type == "modify"
    assert intent.target_part_id == "piano"

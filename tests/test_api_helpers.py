from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from arranger.api import (
    _analyze_uploaded_midi,
    _build_analyze_payload,
    _build_analyze_response,
    _build_arrange_success_response,
    _coerce_analyze_response,
    _build_conversations_payload,
    _build_create_conversation_response,
    _build_feedback_recorded_response,
    _build_generated_plan_response,
    _build_history_payload,
    _build_lint_failure_response,
    _build_lint_warnings_payload,
    _build_midi_duration_payload,
    _build_plan_generation_response,
    _build_revision_response_payload,
    _build_session_log_payload,
    _build_session_versions_payload,
    _build_sessions_payload,
    _build_trace_payload,
    _build_execution_metadata,
    _collect_previous_feedback,
    _export_conversation_data,
    _finalize_generated_plan_response,
    _generate_or_revise_plan,
    _get_repo_commit_id,
    _load_saved_analyze_response,
    _parse_plan_json,
    _read_optional_midi_analysis,
    _record_user_message,
    _require_conversation,
    _require_midi_filename,
    _require_session_log,
    _resolve_regenerate_analyze_result,
    _resolve_melody_track_index,
    _run_difficulty_arrangement,
    _run_standard_arrangement,
    _start_conversation_trace,
    _sanitize_melody_track_index,
    _save_session_log_safe,
    _select_executor_and_run,
    _write_arranged_output,
)


class DummyConversationManager:
    def __init__(self, conversation=None):
        self._conversation = conversation

    def get_conversation(self, conversation_id):
        return self._conversation


class DummyTracer:
    def __init__(self):
        self.started = []
        self.logged = []

    def start_stage(self, name):
        self.started.append(name)

    def log_midi_analysis(self, payload):
        self.logged.append(payload)


MINIMAL_PLAN_DICT = {
    'transform': {'type': 'orchestration'},
    'ensemble': {'parts': []},
    'constraints': {},
    'outputs': {'midi': {}},
}


def test_require_midi_filename_accepts_mid_and_midi():
    _require_midi_filename('demo.mid')
    _require_midi_filename('demo.midi')


@pytest.mark.parametrize('filename', [None, '', 'demo.mp3', 'demo.MID'])
def test_require_midi_filename_rejects_non_midi(filename):
    with pytest.raises(HTTPException) as excinfo:
        _require_midi_filename(filename)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == 'Only MIDI files supported'


def test_build_analyze_response_maps_tracks_and_candidates():
    track_with_notes = SimpleNamespace(
        index=1,
        name='Lead',
        notes=[SimpleNamespace(pitch=72), SimpleNamespace(pitch=76)],
    )
    empty_track = SimpleNamespace(index=2, name='Empty', notes=[])
    candidate = SimpleNamespace(track_index=1, score=0.92, reason='highest register')
    result = SimpleNamespace(
        tracks=[track_with_notes, empty_track],
        melody_candidates=[candidate],
        total_ticks=1920,
        ticks_per_beat=480.0,
        tempo=120.8,
        time_signature=(4, 4),
    )

    response = _build_analyze_response(result)

    assert response.total_ticks == 1920
    assert response.ticks_per_beat == 480
    assert response.tempo == 120
    assert response.time_signature == '4/4'
    assert response.tracks[0].pitch_range == (72, 76)
    assert response.tracks[0].note_on_count == 2
    assert response.tracks[1].pitch_range == (0, 0)
    assert response.melody_candidates[0].track_index == 1
    assert response.melody_candidates[0].reason == 'highest register'


def test_require_conversation_returns_existing(monkeypatch):
    from arranger import api

    expected = {'id': 'conv-1'}
    monkeypatch.setattr(api, 'conversation_manager', DummyConversationManager(expected))

    assert _require_conversation('conv-1') == expected


def test_require_conversation_raises_404(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api, 'conversation_manager', DummyConversationManager(None))

    with pytest.raises(HTTPException) as excinfo:
        _require_conversation('missing')

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == 'Conversation not found'


def test_build_analyze_payload_preserves_public_response_shape():
    track = SimpleNamespace(
        index=1,
        name='Lead',
        notes=[SimpleNamespace(pitch=60), SimpleNamespace(pitch=67)],
    )
    candidate = SimpleNamespace(
        track_index=1,
        track_name='Lead',
        score=0.88,
        reason='melody-like contour',
    )
    result = SimpleNamespace(
        tracks=[track],
        melody_candidates=[candidate],
        total_ticks=960,
        ticks_per_beat=480.0,
        tempo=100.2,
        time_signature=(3, 4),
    )

    payload = _build_analyze_payload(result)

    assert payload == {
        'tracks': [
            {
                'index': 1,
                'name': 'Lead',
                'note_on_count': 2,
                'pitch_range': (60, 67),
                'max_polyphony': 0,
            }
        ],
        'melody_candidates': [
            {
                'track_index': 1,
                'track_name': 'Lead',
                'score': 0.88,
                'reason': 'melody-like contour',
            }
        ],
        'total_ticks': 960,
        'ticks_per_beat': 480,
        'tempo': 100,
        'time_signature': '3/4',
    }


def test_collect_previous_feedback_formats_versions():
    conversation = {
        'arrangement_versions': [
            {'version_id': '1', 'user_feedback': 'more strings'},
            {'version_id': '2'},
            {'version_id': '3', 'user_feedback': 'lighter piano'},
        ]
    }

    assert _collect_previous_feedback(conversation) == 'v1: more strings\nv3: lighter piano'


def test_collect_previous_feedback_returns_none_when_empty():
    assert _collect_previous_feedback({'arrangement_versions': []}) is None


def test_generate_or_revise_plan_generates_new_plan_without_history(monkeypatch):
    from arranger import api

    tracer = DummyTracer()
    analyze_result = SimpleNamespace(tempo=120)
    generated_plan = SimpleNamespace(model_dump=lambda: MINIMAL_PLAN_DICT)
    calls = {}

    class DummyPlanner:
        def __init__(self, conversation_id):
            calls['conversation_id'] = conversation_id

        def generate_plan(self, analyze_result, user_intent, previous_feedback):
            calls['generate_plan'] = {
                'analyze_result': analyze_result,
                'user_intent': user_intent,
                'previous_feedback': previous_feedback,
            }
            return generated_plan

    monkeypatch.setattr(api, 'LLMPlanner', DummyPlanner)

    plan, revision_result, revision_intent, previous_feedback = _generate_or_revise_plan(
        conversation={'arrangement_versions': []},
        conversation_id='conv-1',
        message='make it warmer',
        analyze_result=analyze_result,
        tracer=tracer,
    )

    assert plan is generated_plan
    assert revision_result is None
    assert revision_intent is None
    assert previous_feedback is None
    assert tracer.started == ['plan_generation']
    assert calls == {
        'conversation_id': 'conv-1',
        'generate_plan': {
            'analyze_result': analyze_result,
            'user_intent': 'make it warmer',
            'previous_feedback': None,
        },
    }


def test_generate_or_revise_plan_uses_revision_result_when_successful(monkeypatch):
    from arranger import api

    tracer = DummyTracer()
    revised_plan = SimpleNamespace(model_dump=lambda: MINIMAL_PLAN_DICT)
    revision_intent = SimpleNamespace(
        is_revision=True,
        revision_type='modify_part',
        target_part_id='piano',
        instruction='thin the voicing',
    )
    revision_result = SimpleNamespace(
        success=True,
        revised_plan=revised_plan,
        message='updated',
    )
    calls = {}

    class DummyPlanner:
        def __init__(self, conversation_id):
            calls['conversation_id'] = conversation_id

        def analyze_revision_intent(self, user_message, current_plan):
            calls['analyze_revision_intent'] = {
                'user_message': user_message,
                'transform_type': current_plan.transform.type,
            }
            return revision_intent

        def generate_plan(self, analyze_result, user_intent, previous_feedback):
            raise AssertionError('generate_plan should not be called on successful revision')

    class DummyRevisionExecutor:
        def apply_revision(self, base_plan, revision_intent, user_instruction, llm_planner, analyze_result):
            calls['apply_revision'] = {
                'transform_type': base_plan.transform.type,
                'revision_intent': revision_intent,
                'user_instruction': user_instruction,
                'llm_planner_class': llm_planner.__class__.__name__,
                'analyze_result': analyze_result,
            }
            return revision_result

    monkeypatch.setattr(api, 'LLMPlanner', DummyPlanner)
    monkeypatch.setattr(api, 'RevisionExecutor', DummyRevisionExecutor)

    plan, returned_revision_result, returned_revision_intent, previous_feedback = _generate_or_revise_plan(
        conversation={'arrangement_versions': [{'version_id': 'v1', 'plan': MINIMAL_PLAN_DICT}]},
        conversation_id='conv-1',
        message='make the piano lighter',
        analyze_result=None,
        tracer=tracer,
    )

    assert plan is revised_plan
    assert returned_revision_result is revision_result
    assert returned_revision_intent is revision_intent
    assert previous_feedback is None
    assert tracer.started == ['plan_generation', 'revision_analysis']
    assert calls['conversation_id'] == 'conv-1'
    assert calls['analyze_revision_intent'] == {
        'user_message': 'make the piano lighter',
        'transform_type': 'orchestration',
    }
    assert calls['apply_revision'] == {
        'transform_type': 'orchestration',
        'revision_intent': revision_intent,
        'user_instruction': 'thin the voicing',
        'llm_planner_class': 'DummyPlanner',
        'analyze_result': None,
    }


def test_generate_or_revise_plan_falls_back_to_generation_after_failed_revision(monkeypatch):
    from arranger import api

    tracer = DummyTracer()
    revision_intent = SimpleNamespace(
        is_revision=True,
        revision_type='modify_part',
        target_part_id='violin',
        instruction='less vibrato',
    )
    revision_result = SimpleNamespace(
        success=False,
        revised_plan=None,
        message='cannot revise',
    )
    generated_plan = SimpleNamespace(model_dump=lambda: MINIMAL_PLAN_DICT)
    calls = {}

    class DummyPlanner:
        def __init__(self, conversation_id):
            calls['conversation_id'] = conversation_id

        def analyze_revision_intent(self, user_message, current_plan):
            calls['analyze_revision_intent'] = user_message
            return revision_intent

        def generate_plan(self, analyze_result, user_intent, previous_feedback):
            calls['generate_plan'] = {
                'analyze_result': analyze_result,
                'user_intent': user_intent,
                'previous_feedback': previous_feedback,
            }
            return generated_plan

    class DummyRevisionExecutor:
        def apply_revision(self, base_plan, revision_intent, user_instruction, llm_planner, analyze_result):
            calls['apply_revision'] = user_instruction
            return revision_result

    monkeypatch.setattr(api, 'LLMPlanner', DummyPlanner)
    monkeypatch.setattr(api, 'RevisionExecutor', DummyRevisionExecutor)

    conversation = {
        'arrangement_versions': [
            {'version_id': '1', 'plan': MINIMAL_PLAN_DICT, 'user_feedback': 'more strings'}
        ]
    }

    plan, returned_revision_result, returned_revision_intent, previous_feedback = _generate_or_revise_plan(
        conversation=conversation,
        conversation_id='conv-1',
        message='make it brighter',
        analyze_result=None,
        tracer=tracer,
    )

    assert plan is generated_plan
    assert returned_revision_result is revision_result
    assert returned_revision_intent is revision_intent
    assert previous_feedback == 'v1: more strings'
    assert tracer.started == ['plan_generation', 'revision_analysis']
    assert calls['apply_revision'] == 'less vibrato'
    assert calls['generate_plan'] == {
        'analyze_result': None,
        'user_intent': 'make it brighter',
        'previous_feedback': 'v1: more strings',
    }


def test_start_conversation_trace_starts_requested_stage(monkeypatch):
    from arranger import api

    tracer = DummyTracer()
    monkeypatch.setattr(api, 'get_tracer', lambda conversation_id: tracer)

    result = _start_conversation_trace('conv-1', 'user_message')

    assert result is tracer
    assert tracer.started == ['user_message']


def test_record_user_message_delegates_to_conversation_manager(monkeypatch):
    from arranger import api

    calls = {}
    monkeypatch.setattr(
        api.conversation_manager,
        'add_message',
        lambda **kwargs: calls.setdefault('add_message', kwargs),
    )

    _record_user_message('conv-1', 'hello there')

    assert calls['add_message'] == {
        'conversation_id': 'conv-1',
        'role': 'user',
        'content': 'hello there',
    }


def test_read_optional_midi_analysis_returns_none_without_upload():
    tracer = DummyTracer()

    import asyncio

    assert asyncio.run(_read_optional_midi_analysis(None, tracer)) is None


def test_read_optional_midi_analysis_reads_and_analyzes_upload(monkeypatch):
    from arranger import api
    import asyncio

    tracer = DummyTracer()
    calls = {}

    class DummyUpload:
        async def read(self):
            calls['read'] = True
            return b'midi-bytes'

    monkeypatch.setattr(
        api,
        '_analyze_uploaded_midi',
        lambda midi_bytes, tracer_arg: (
            calls.setdefault('analyze', (midi_bytes, tracer_arg)) or None,
            None,
        ) and 'analyzed',
    )

    result = asyncio.run(_read_optional_midi_analysis(DummyUpload(), tracer))

    assert calls == {
        'read': True,
        'analyze': (b'midi-bytes', tracer),
    }
    assert result == 'analyzed'


def test_coerce_analyze_response_restores_saved_payload():
    restored = _coerce_analyze_response(
        {
            'tracks': [
                {
                    'index': 0,
                    'name': 'Lead',
                    'note_on_count': 4,
                    'pitch_range': [60, 72],
                    'max_polyphony': 1,
                }
            ],
            'melody_candidates': [
                {'track_index': 0, 'score': 0.9, 'reason': 'melody'}
            ],
            'total_ticks': 960,
            'ticks_per_beat': 480,
            'tempo': 120,
            'time_signature': '4/4',
        }
    )

    assert restored.tempo == 120
    assert restored.tracks[0].pitch_range == (60, 72)
    assert restored.melody_candidates[0].track_index == 0


def test_load_saved_analyze_response_prefers_metadata(monkeypatch):
    from arranger import api

    conversation = {
        'metadata': {
            'last_midi_analysis': {
                'tracks': [
                    {
                        'index': 0,
                        'name': 'Lead',
                        'note_on_count': 4,
                        'pitch_range': [60, 72],
                        'max_polyphony': 1,
                    }
                ],
                'melody_candidates': [
                    {'track_index': 0, 'score': 0.9, 'reason': 'melody'}
                ],
                'total_ticks': 960,
                'ticks_per_beat': 480,
                'tempo': 120,
                'time_signature': '4/4',
            }
        }
    }
    monkeypatch.setattr(api.session_logger, 'get_session_logs', lambda conversation_id: (_ for _ in ()).throw(AssertionError('session logs should not be used')))

    restored = _load_saved_analyze_response('conv-1', conversation)

    assert restored.tempo == 120
    assert restored.time_signature == '4/4'


def test_load_saved_analyze_response_falls_back_to_session_logs(monkeypatch):
    from arranger import api

    monkeypatch.setattr(
        api.session_logger,
        'get_session_logs',
        lambda conversation_id: [
            SimpleNamespace(midi_analysis={}),
            SimpleNamespace(
                midi_analysis={
                    'tracks': [
                        {
                            'index': 1,
                            'name': 'Piano',
                            'note_on_count': 8,
                            'pitch_range': [48, 79],
                            'max_polyphony': 3,
                        }
                    ],
                    'melody_candidates': [
                        {'track_index': 1, 'score': 0.75, 'reason': 'range'}
                    ],
                    'total_ticks': 1920,
                    'ticks_per_beat': 480,
                    'tempo': 96,
                    'time_signature': '3/4',
                }
            ),
        ],
    )

    restored = _load_saved_analyze_response('conv-1', {'metadata': {}})

    assert restored.tempo == 96
    assert restored.tracks[0].name == 'Piano'


def test_resolve_regenerate_analyze_result_uses_saved_analysis_without_upload(monkeypatch):
    from arranger import api
    import asyncio

    saved_analysis = SimpleNamespace(tempo=88)

    async def fake_read_optional_midi_analysis(midi_file, tracer):
        return None

    monkeypatch.setattr(api, '_read_optional_midi_analysis', fake_read_optional_midi_analysis)
    monkeypatch.setattr(api, '_load_saved_analyze_response', lambda conversation_id, conversation: saved_analysis)

    result = asyncio.run(
        _resolve_regenerate_analyze_result('conv-1', {'metadata': {}}, None, DummyTracer())
    )

    assert result is saved_analysis


def test_resolve_regenerate_analyze_result_rejects_missing_saved_analysis(monkeypatch):
    from arranger import api
    import asyncio

    async def fake_read_optional_midi_analysis(midi_file, tracer):
        return None

    monkeypatch.setattr(api, '_read_optional_midi_analysis', fake_read_optional_midi_analysis)
    monkeypatch.setattr(api, '_load_saved_analyze_response', lambda conversation_id, conversation: None)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            _resolve_regenerate_analyze_result('conv-1', {'metadata': {}}, None, DummyTracer())
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == 'No MIDI analysis available for regeneration; upload a MIDI file first'


def test_build_feedback_recorded_response_returns_stable_shape():
    assert _build_feedback_recorded_response('conv-1', 'v2') == {
        'conversation_id': 'conv-1',
        'version_id': 'v2',
        'status': 'feedback_recorded',
    }


def test_build_history_payload_formats_public_history_view():
    payload = _build_history_payload(
        'conv-1',
        {
            'initial_intent': 'original',
            'current_intent': 'updated',
            'messages': [{'role': 'user', 'content': 'hello'}],
            'llm_thoughts': [{'stage': 'plan_generation'}],
            'processing_steps': [{'step_name': 'midi_analysis'}],
            'arrangement_versions': [
                {
                    'version_id': 'v1',
                    'status': 'generated',
                    'created_at': '2026-04-09T00:00:00',
                    'user_feedback': '',
                },
                {
                    'version_id': 'v2',
                    'status': 'reviewed',
                    'created_at': '2026-04-09T01:00:00',
                    'user_feedback': 'more strings',
                },
            ],
        },
    )

    assert payload == {
        'conversation_id': 'conv-1',
        'initial_intent': 'original',
        'current_intent': 'updated',
        'messages': [{'role': 'user', 'content': 'hello'}],
        'llm_thoughts': [{'stage': 'plan_generation'}],
        'processing_steps': [{'step_name': 'midi_analysis'}],
        'arrangement_versions': [
            {
                'version_id': 'v1',
                'status': 'generated',
                'created_at': '2026-04-09T00:00:00',
                'has_feedback': False,
            },
            {
                'version_id': 'v2',
                'status': 'reviewed',
                'created_at': '2026-04-09T01:00:00',
                'has_feedback': True,
            },
        ],
    }


def test_export_conversation_data_writes_file_and_returns_counts(monkeypatch, tmp_path):
    from arranger import api

    export_data = {
        'messages': [{'role': 'user'}],
        'llm_thoughts': [{'stage': 'plan_generation'}, {'stage': 'revision'}],
        'arrangement_versions': [{'version_id': 'v1'}],
    }

    class FakeDateTime:
        @classmethod
        def now(cls):
            return SimpleNamespace(strftime=lambda fmt: '20260409_120000')

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(api.conversation_manager, 'export_conversation', lambda conversation_id: export_data)
    monkeypatch.setattr(api, 'datetime', FakeDateTime)

    response = _export_conversation_data('conv-1')

    expected_path = tmp_path / 'conversation_conv-1_20260409_120000.json'
    assert response == {
        'conversation_id': 'conv-1',
        'export_path': str(expected_path),
        'versions_count': 1,
        'messages_count': 1,
        'llm_thoughts_count': 2,
    }
    assert expected_path.exists()
    assert expected_path.read_text(encoding='utf-8') == (
        '{\n'
        '  "messages": [\n'
        '    {\n'
        '      "role": "user"\n'
        '    }\n'
        '  ],\n'
        '  "llm_thoughts": [\n'
        '    {\n'
        '      "stage": "plan_generation"\n'
        '    },\n'
        '    {\n'
        '      "stage": "revision"\n'
        '    }\n'
        '  ],\n'
        '  "arrangement_versions": [\n'
        '    {\n'
        '      "version_id": "v1"\n'
        '    }\n'
        '  ]\n'
        '}'
    )


def test_require_session_log_returns_log(monkeypatch):
    from arranger import api

    log = SimpleNamespace(version_id='v1')
    monkeypatch.setattr(api.session_logger, 'get_session_log', lambda conversation_id, version_id: log)

    assert _require_session_log('conv-1', 'v1') is log


def test_require_session_log_raises_404_when_missing(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.session_logger, 'get_session_log', lambda conversation_id, version_id: None)

    with pytest.raises(HTTPException) as excinfo:
        _require_session_log('conv-1', 'v1')

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == 'Session log not found'


def test_build_trace_payload_returns_trace_data():
    payload = {'events': [{'stage': 'plan_generation'}]}

    assert _build_trace_payload(payload) is payload


def test_build_session_log_payload_uses_asdict():
    log = SimpleNamespace(foo='bar')

    from arranger import api

    original_asdict = api.asdict
    api.asdict = lambda value: {'wrapped': value.foo}
    try:
        assert _build_session_log_payload(log) == {'wrapped': 'bar'}
    finally:
        api.asdict = original_asdict


def test_build_session_versions_payload_formats_versions():
    logs = [
        SimpleNamespace(
            version_id='v1',
            created_at='2026-04-09T00:00:00',
            status='generated',
            plan={'ensemble': {'parts': [{}, {}]}},
            user_intent='a' * 120,
        ),
        SimpleNamespace(
            version_id='v2',
            created_at='2026-04-09T01:00:00',
            status='reviewed',
            plan={},
            user_intent='short',
        ),
    ]

    assert _build_session_versions_payload('conv-1', logs) == {
        'conversation_id': 'conv-1',
        'versions': [
            {
                'version_id': 'v1',
                'created_at': '2026-04-09T00:00:00',
                'status': 'generated',
                'plan_parts_count': 2,
                'user_intent_preview': 'a' * 100,
            },
            {
                'version_id': 'v2',
                'created_at': '2026-04-09T01:00:00',
                'status': 'reviewed',
                'plan_parts_count': 0,
                'user_intent_preview': 'short',
            },
        ],
    }


def test_build_sessions_payload_wraps_sessions():
    assert _build_sessions_payload([{'conversation_id': 'conv-1'}]) == {
        'sessions': [{'conversation_id': 'conv-1'}]
    }


def test_build_conversations_payload_wraps_conversations():
    assert _build_conversations_payload([{'id': 'conv-1'}]) == {
        'conversations': [{'id': 'conv-1'}]
    }


def test_build_create_conversation_response_returns_active_payload():
    from arranger import api

    class FakeDateTime:
        @classmethod
        def now(cls):
            return SimpleNamespace(isoformat=lambda: '2026-04-09T12:00:00')

    original_datetime = api.datetime
    api.datetime = FakeDateTime
    try:
        assert _build_create_conversation_response('conv-1') == {
            'conversation_id': 'conv-1',
            'created_at': '2026-04-09T12:00:00',
            'status': 'active',
        }
    finally:
        api.datetime = original_datetime


def test_build_midi_duration_payload_computes_seconds():
    analysis = SimpleNamespace(total_ticks=960, ticks_per_beat=480, tempo=120)

    assert _build_midi_duration_payload(analysis) == {
        'duration_sec': 1.0,
        'total_ticks': 960,
        'ticks_per_beat': 480,
        'tempo': 120,
    }


def test_build_plan_generation_response_formats_plan_and_summary():
    plan = SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})
    analyze_response = SimpleNamespace(
        tracks=[SimpleNamespace(), SimpleNamespace()],
        tempo=120,
        time_signature='4/4',
        melody_candidates=[
            SimpleNamespace(track_index=1, score=0.9),
            SimpleNamespace(track_index=2, score=0.5),
        ],
    )

    assert _build_plan_generation_response(plan, analyze_response) == {
        'plan': {'transform': {'type': 'orchestration'}},
        'analyze': {
            'tracks_count': 2,
            'tempo': 120,
            'time_signature': '4/4',
            'melody_candidates': [
                {'track_index': 1, 'score': 0.9},
                {'track_index': 2, 'score': 0.5},
            ],
        },
    }


def test_analyze_uploaded_midi_runs_analysis_and_logs(monkeypatch):
    from arranger import api

    result = SimpleNamespace(
        tracks=[SimpleNamespace(index=0, name='Lead', notes=[SimpleNamespace(pitch=64)])],
        melody_candidates=[
            SimpleNamespace(track_index=0, track_name='Lead', score=0.95, reason='clear melody')
        ],
        total_ticks=480,
        ticks_per_beat=480.0,
        tempo=90.1,
        time_signature=(4, 4),
    )

    class DummyMidiAnalysisService:
        def analyze(self, midi_bytes):
            assert midi_bytes == b'midi-bytes'
            return result

    monkeypatch.setattr(api, 'MidiAnalysisService', DummyMidiAnalysisService)
    tracer = DummyTracer()

    response = _analyze_uploaded_midi(b'midi-bytes', tracer)

    assert tracer.started == ['midi_analysis']
    assert tracer.logged == [{
        'tracks_count': 1,
        'tempo': 90.1,
        'time_signature': '(4, 4)',
        'total_ticks': 480,
        'melody_candidates': [{'track_index': 0, 'score': 0.95}],
    }]
    assert response.time_signature == '4/4'
    assert response.tempo == 90


def test_build_lint_failure_response_returns_stable_payload():
    issue = SimpleNamespace(
        code='missing_part',
        message='part missing',
        location='ensemble.parts',
        suggestion='add a part',
    )
    lint_result = SimpleNamespace(
        errors=[issue],
        warnings=[issue],
        get_summary=lambda: '1 error, 1 warning',
    )

    response = _build_lint_failure_response(lint_result, 'conv-1')

    assert response.status_code == 400
    assert response.body.decode('utf-8') == (
        '{"error":"plan_validation_failed","summary":"Plan Lint: 1 error, 1 warning",'
        '"errors":[{"code":"missing_part","message":"part missing","location":"ensemble.parts",'
        '"suggestion":"add a part"}],"warnings":[{"code":"missing_part","message":"part missing",'
        '"location":"ensemble.parts","suggestion":"add a part"}],"conversation_id":"conv-1"}'
    )


def test_build_lint_warnings_payload_returns_none_without_warnings():
    lint_result = SimpleNamespace(warnings=[])

    assert _build_lint_warnings_payload(lint_result) is None


def test_build_lint_warnings_payload_formats_warning_list():
    warning = SimpleNamespace(
        code='soft_limit',
        message='too dense',
        location='ensemble.parts[0]',
        suggestion='reduce notes',
    )
    lint_result = SimpleNamespace(warnings=[warning])

    assert _build_lint_warnings_payload(lint_result) == {
        'passed': True,
        'warnings': [
            {
                'code': 'soft_limit',
                'message': 'too dense',
                'location': 'ensemble.parts[0]',
                'suggestion': 'reduce notes',
            }
        ],
    }


def test_build_revision_response_payload_returns_none_for_non_revision():
    revision_intent = SimpleNamespace(is_revision=False)

    assert _build_revision_response_payload(revision_intent, None) is None
    assert _build_revision_response_payload(None, None) is None


def test_build_revision_response_payload_formats_revision_metadata():
    revision_intent = SimpleNamespace(
        is_revision=True,
        revision_type='modify_part',
        target_part_id='piano',
    )
    revision_result = SimpleNamespace(
        message='updated piano voicing',
        modified_parts=['piano'],
    )

    assert _build_revision_response_payload(revision_intent, revision_result) == {
        'is_revision': True,
        'revision_type': 'modify_part',
        'target_part_id': 'piano',
        'message': 'updated piano voicing',
        'modified_parts': ['piano'],
    }


def test_build_generated_plan_response_includes_optional_sections():
    plan = SimpleNamespace(model_dump=lambda: {'ensemble': {'parts': []}})

    response = _build_generated_plan_response(
        conversation_id='conv-1',
        version_id='v1',
        plan=plan,
        lint_payload={'passed': True, 'warnings': []},
        revision_payload={'is_revision': True},
        trace_summary={'events': 3},
        feedback_used='v1: more piano',
    )

    assert response == {
        'conversation_id': 'conv-1',
        'version_id': 'v1',
        'plan': {'ensemble': {'parts': []}},
        'status': 'generated',
        'lint': {'passed': True, 'warnings': []},
        'revision': {'is_revision': True},
        'trace': {'events': 3},
        'feedback_used': 'v1: more piano',
    }


def test_build_generated_plan_response_omits_empty_optional_sections():
    plan = SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})

    response = _build_generated_plan_response('conv-1', 'v1', plan)

    assert response == {
        'conversation_id': 'conv-1',
        'version_id': 'v1',
        'plan': {'transform': {'type': 'orchestration'}},
        'status': 'generated',
    }


def test_save_session_log_safe_persists_session(monkeypatch):
    from arranger import api

    saved = {}

    monkeypatch.setattr(api.conversation_manager, 'get_llm_thoughts', lambda conversation_id: [{
        'prompt': 'prompt',
        'response': 'response',
        'model': 'model-x',
        'tokens_used': 42,
        'duration_ms': 120,
    }])

    class DummySessionLogger:
        def save_session_log(self, session_log):
            saved['log'] = session_log

    monkeypatch.setattr(api, 'session_logger', DummySessionLogger())

    tracer = SimpleNamespace(export=lambda: {'events': [{'name': 'stage'}]})
    analyze_result = SimpleNamespace(model_dump=lambda: {'tempo': 120})
    plan = SimpleNamespace(model_dump=lambda: {'plan': True})

    _save_session_log_safe(
        conversation_id='conv-1',
        version_id='v1',
        user_intent='make it brighter',
        midi_filename='demo.mid',
        analyze_result=analyze_result,
        plan=plan,
        tracer=tracer,
        include_trace=True,
    )

    log = saved['log']
    assert log.conversation_id == 'conv-1'
    assert log.version_id == 'v1'
    assert log.user_intent == 'make it brighter'
    assert log.midi_filename == 'demo.mid'
    assert log.midi_analysis == {'tempo': 120}
    assert log.llm_prompt == 'prompt'
    assert log.llm_response == 'response'
    assert log.llm_model == 'model-x'
    assert log.llm_tokens_used == 42
    assert log.llm_duration_ms == 120
    assert log.plan == {'plan': True}
    assert log.trace_events == [{'name': 'stage'}]
    assert log.status == 'generated'


def test_save_session_log_safe_swallows_logger_failures(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.conversation_manager, 'get_llm_thoughts', lambda conversation_id: [])

    class FailingSessionLogger:
        def save_session_log(self, session_log):
            raise RuntimeError('disk full')

    monkeypatch.setattr(api, 'session_logger', FailingSessionLogger())

    _save_session_log_safe(
        conversation_id='conv-1',
        version_id='v1',
        user_intent='make it brighter',
        midi_filename='demo.mid',
        analyze_result=None,
        plan=SimpleNamespace(model_dump=lambda: {'plan': True}),
        tracer=SimpleNamespace(export=lambda: {'events': []}),
        include_trace=False,
    )


def test_finalize_generated_plan_response_persists_log_and_updates_intent(monkeypatch):
    from arranger import api

    plan = SimpleNamespace(model_dump=lambda: MINIMAL_PLAN_DICT)
    tracer = SimpleNamespace(get_summary=lambda: {'events': 3})
    calls = {}

    def fake_add_arrangement_version(conversation_id, plan, generation_intent=None):
        calls['add_arrangement_version'] = {
            'conversation_id': conversation_id,
            'plan': plan,
            'generation_intent': generation_intent,
        }
        return 'v1'

    monkeypatch.setattr(
        api.conversation_manager,
        'add_arrangement_version',
        fake_add_arrangement_version,
    )
    monkeypatch.setattr(
        api,
        '_save_session_log_safe',
        lambda **kwargs: calls.setdefault('save_session_log', kwargs),
    )
    monkeypatch.setattr(
        api.conversation_manager,
        'update_metadata',
        lambda conversation_id, metadata_updates: calls.setdefault(
            'update_metadata',
            {'conversation_id': conversation_id, 'metadata_updates': metadata_updates},
        ),
    )
    monkeypatch.setattr(
        api.conversation_manager,
        'update_intent',
        lambda conversation_id, new_intent: calls.setdefault(
            'update_intent',
            {'conversation_id': conversation_id, 'new_intent': new_intent},
        ),
    )

    response = _finalize_generated_plan_response(
        conversation_id='conv-1',
        plan=plan,
        tracer=tracer,
        include_trace=True,
        user_intent='make it brighter',
        midi_filename='demo.mid',
        analyze_result=SimpleNamespace(model_dump=lambda: {'tempo': 120}),
        lint_payload={'passed': True, 'warnings': []},
        revision_payload={'is_revision': True},
        update_intent_to='make it brighter',
        generation_intent='make it brighter',
    )

    assert calls['add_arrangement_version'] == {
        'conversation_id': 'conv-1',
        'plan': MINIMAL_PLAN_DICT,
        'generation_intent': 'make it brighter',
    }
    assert calls['save_session_log']['conversation_id'] == 'conv-1'
    assert calls['save_session_log']['version_id'] == 'v1'
    assert calls['save_session_log']['user_intent'] == 'make it brighter'
    assert calls['save_session_log']['midi_filename'] == 'demo.mid'
    assert calls['save_session_log']['include_trace'] is True
    assert calls['update_metadata'] == {
        'conversation_id': 'conv-1',
        'metadata_updates': {'last_midi_analysis': {'tempo': 120}},
    }
    assert calls['update_intent'] == {
        'conversation_id': 'conv-1',
        'new_intent': 'make it brighter',
    }
    assert response.body.decode('utf-8') == (
        '{"conversation_id":"conv-1","version_id":"v1","plan":'
        '{"transform":{"type":"orchestration"},"ensemble":{"parts":[]},'
        '"constraints":{},"outputs":{"midi":{}}},"status":"generated",'
        '"lint":{"passed":true,"warnings":[]},"revision":{"is_revision":true},'
        '"trace":{"events":3}}'
    )


def test_finalize_generated_plan_response_supports_feedback_only_response(monkeypatch):
    from arranger import api

    plan = SimpleNamespace(model_dump=lambda: MINIMAL_PLAN_DICT)
    tracer = SimpleNamespace(get_summary=lambda: {'ignored': True})
    calls = {}

    def fake_add_arrangement_version(conversation_id, plan, generation_intent=None):
        calls['add_arrangement_version'] = {
            'conversation_id': conversation_id,
            'plan': plan,
            'generation_intent': generation_intent,
        }
        return 'v2'

    monkeypatch.setattr(
        api.conversation_manager,
        'add_arrangement_version',
        fake_add_arrangement_version,
    )
    monkeypatch.setattr(
        api,
        '_save_session_log_safe',
        lambda **kwargs: (_ for _ in ()).throw(AssertionError('session log should not be saved')),
    )
    monkeypatch.setattr(
        api.conversation_manager,
        'update_metadata',
        lambda conversation_id, metadata_updates: (_ for _ in ()).throw(AssertionError('metadata should not be updated')),
    )
    monkeypatch.setattr(
        api.conversation_manager,
        'update_intent',
        lambda conversation_id, new_intent: (_ for _ in ()).throw(AssertionError('intent should not be updated')),
    )

    response = _finalize_generated_plan_response(
        conversation_id='conv-1',
        plan=plan,
        tracer=tracer,
        include_trace=False,
        feedback_used='v1: more strings',
    )

    assert calls['add_arrangement_version'] == {
        'conversation_id': 'conv-1',
        'plan': MINIMAL_PLAN_DICT,
        'generation_intent': None,
    }
    assert response.body.decode('utf-8') == (
        '{"conversation_id":"conv-1","version_id":"v2","plan":'
        '{"transform":{"type":"orchestration"},"ensemble":{"parts":[]},'
        '"constraints":{},"outputs":{"midi":{}}},"status":"generated",'
        '"feedback_used":"v1: more strings"}'
    )


def test_parse_plan_json_returns_valid_unified_plan():
    plan = _parse_plan_json(
        '{"transform":{"type":"orchestration"},"ensemble":{"parts":[]},"constraints":{},"outputs":{"midi":{}}}'
    )

    assert plan.transform.type == 'orchestration'
    assert plan.ensemble.parts == []


def test_parse_plan_json_rejects_invalid_json():
    with pytest.raises(HTTPException) as excinfo:
        _parse_plan_json('{bad json')

    assert excinfo.value.status_code == 400
    assert 'Invalid JSON:' in excinfo.value.detail


def test_resolve_melody_track_index_prefers_request_value():
    plan = SimpleNamespace(constraints=SimpleNamespace(lock_melody_events=SimpleNamespace(source_track_ref='4')))

    assert _resolve_melody_track_index(plan, '2') == 2


def test_resolve_melody_track_index_uses_plan_source_ref():
    plan = SimpleNamespace(constraints=SimpleNamespace(lock_melody_events=SimpleNamespace(source_track_ref='3')))

    assert _resolve_melody_track_index(plan, None) == 3


def test_resolve_melody_track_index_falls_back_to_zero_on_invalid_input():
    plan = SimpleNamespace(constraints=SimpleNamespace(lock_melody_events=SimpleNamespace(source_track_ref='abc')))

    assert _resolve_melody_track_index(plan, None) == 0
    assert _resolve_melody_track_index(plan, 'xyz') == 0


def test_sanitize_melody_track_index_clamps_out_of_range(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.MidiReader, 'read_midi', lambda midi_data: 'midi')
    monkeypatch.setattr(api.MidiReader, 'extract_track_messages', lambda midi: [[], []])

    assert _sanitize_melody_track_index(b'midi', 5) == 0


def test_sanitize_melody_track_index_keeps_valid_index(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.MidiReader, 'read_midi', lambda midi_data: 'midi')
    monkeypatch.setattr(api.MidiReader, 'extract_track_messages', lambda midi: [[], [], []])

    assert _sanitize_melody_track_index(b'midi', 2) == 2


def test_sanitize_melody_track_index_returns_original_on_reader_error(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.MidiReader, 'read_midi', lambda midi_data: (_ for _ in ()).throw(RuntimeError('bad midi')))

    assert _sanitize_melody_track_index(b'midi', 4) == 4


def test_select_executor_and_run_uses_orchestrate_executor(monkeypatch):
    from arranger import api

    class DummyExecutor:
        def __init__(self, plan):
            self.plan = plan

        def execute(self, input_midi, melody_track_index):
            assert input_midi == b'midi'
            assert melody_track_index == 2
            return ['track'], {'kind': 'orch'}

    monkeypatch.setattr(api, 'OrchestrateExecutor', DummyExecutor)
    plan = SimpleNamespace(transform=SimpleNamespace(type='orchestration'))

    assert _select_executor_and_run(plan, b'midi', 2) == (['track'], {'kind': 'orch'})


def test_select_executor_and_run_uses_creative_executor(monkeypatch):
    from arranger import api

    class DummyExecutor:
        def __init__(self, plan):
            self.plan = plan

        def execute(self, midi_data):
            assert midi_data == b'midi'
            return ['track'], {'kind': 'creative'}

    monkeypatch.setattr(api, 'CreativeExecutor', DummyExecutor)
    plan = SimpleNamespace(transform=SimpleNamespace(type='creative'))

    assert _select_executor_and_run(plan, b'midi', 0) == (['track'], {'kind': 'creative'})


def test_build_arrange_success_response_encodes_midi():
    validation_result = SimpleNamespace(to_dict=lambda: {'ok': True}, all_passed=True)

    response = _build_arrange_success_response(
        output_path=Path('/tmp/unique.mid'),
        output_data=b'abc',
        validation_result=validation_result,
        stats={'kind': 'orch'},
    )

    assert response.status_code == 200
    assert response.body.decode('utf-8') == (
        '{"output_path":"/tmp/unique.mid","unique_path":"/tmp/unique.mid",'
        '"status":"validated","validation_passed":true,'
        '"midi_data":"YWJj","checks":{"ok":true},"stats":{"kind":"orch"}}'
    )


def test_build_arrange_success_response_marks_validation_failure():
    validation_result = SimpleNamespace(
        to_dict=lambda: {'all_passed': False, 'errors': ['instrumentation mismatch']},
        all_passed=False,
    )

    response = _build_arrange_success_response(
        output_path=Path('/tmp/unique.mid'),
        output_data=b'abc',
        validation_result=validation_result,
        stats={'kind': 'orch'},
    )

    assert response.status_code == 200
    assert response.body.decode('utf-8') == (
        '{"output_path":"/tmp/unique.mid","unique_path":"/tmp/unique.mid",'
        '"status":"validation_failed","validation_passed":false,'
        '"midi_data":"YWJj","checks":{"all_passed":false,"errors":["instrumentation mismatch"]},"stats":{"kind":"orch"}}'
    )


def test_write_arranged_output_writes_unique_file_only(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(api.uuid, 'uuid4', lambda: SimpleNamespace(hex='abcdef1234567890'))
    monkeypatch.setattr(api.MidiReader, 'read_midi', lambda midi_data: 'midi')
    monkeypatch.setattr(api.MidiWriter, 'write_midi', lambda **kwargs: b'written-midi')
    monkeypatch.setattr(
        api,
        'MidiAnalyzer',
        lambda midi: SimpleNamespace(analyze=lambda: SimpleNamespace(tempo=120, time_signature=(4, 4), total_ticks=960)),
    )

    result = _write_arranged_output(b'input-midi', ['track'])

    assert result['output_data'] == b'written-midi'
    assert result['output_path'].name == 'arranged_abcdef12.mid'
    assert result['output_path'].read_bytes() == b'written-midi'
    assert not (tmp_path / 'arranged.mid').exists()


def test_run_difficulty_arrangement_uses_simplify_executor(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)

    class DummySimplifyExecutor:
        def __init__(self, plan):
            self.plan = plan

        def execute(self, midi_data):
            assert midi_data == b'midi'
            return b'simplified'

    monkeypatch.setattr(api, 'SimplifyExecutor', DummySimplifyExecutor)
    monkeypatch.setattr(api.uuid, 'uuid4', lambda: SimpleNamespace(hex='abcdef1234567890'))

    plan = SimpleNamespace(transform=SimpleNamespace(direction='down'))
    response = _run_difficulty_arrangement(plan, b'midi')

    assert response.status_code == 200
    assert response.body.decode('utf-8') == (
        '{"output_path":"' + str(tmp_path / 'output_abcdef1234567890.mid') + '",'
        '"checks":{},"stats":{"type":"difficulty"}}'
    )
    assert (tmp_path / 'output_abcdef1234567890.mid').read_bytes() == b'simplified'


def test_run_standard_arrangement_uses_shared_helpers_and_persists_result(monkeypatch, tmp_path):
    from arranger import api

    calls = {}
    plan = SimpleNamespace(transform=SimpleNamespace(type='orchestration'))
    validation_result = SimpleNamespace(to_dict=lambda: {'ok': True}, all_passed=True)

    monkeypatch.setattr(
        api,
        '_select_executor_and_run',
        lambda plan_arg, midi_data, melody_track_index: (
            calls.setdefault('select', (plan_arg, midi_data, melody_track_index)) or None,
            None,
        ) and ([('track', {})], {'kind': 'orch'}),
    )
    monkeypatch.setattr(
        api,
        '_write_arranged_output',
        lambda midi_data, output_tracks: (
            calls.setdefault('write', (midi_data, output_tracks)) or None,
            None,
        ) and {
            'output_data': b'abc',
            'output_path': tmp_path / 'unique.mid',
        },
    )
    monkeypatch.setattr(
        api,
        'Validator',
        lambda plan_arg: SimpleNamespace(
            validate=lambda midi_data, output_tracks: (
                calls.setdefault('validate', (plan_arg, midi_data, output_tracks)) or None,
                None,
            ) and validation_result
        ),
    )
    monkeypatch.setattr(
        api,
        '_build_execution_metadata',
        lambda output_data, execution_start_time: (
            calls.setdefault('metadata', (output_data, execution_start_time)) or None,
            None,
        ) and {
            'execution_duration_ms': 250,
            'output_midi_hash': 'hash-123',
        },
    )
    monkeypatch.setattr(
        api,
        '_update_arrangement_version_result_safe',
        lambda **kwargs: calls.setdefault('update', kwargs),
    )

    response = _run_standard_arrangement(
        plan=plan,
        midi_data=b'midi',
        melody_track_index=3,
        execution_start_time=10.0,
        conversation_id='conv-1',
        version_id='v1',
        commit_id='abc123',
    )

    assert calls['select'] == (plan, b'midi', 3)
    assert calls['write'] == (b'midi', [('track', {})])
    assert calls['validate'] == (plan, b'midi', [('track', {})])
    assert calls['metadata'] == (b'abc', 10.0)
    assert calls['update'] == {
        'conversation_id': 'conv-1',
        'version_id': 'v1',
        'stats': {'kind': 'orch'},
        'validation_result': validation_result,
        'output_path': tmp_path / 'unique.mid',
        'output_midi_hash': 'hash-123',
        'commit_id': 'abc123',
        'execution_duration_ms': 250,
    }
    assert response.body.decode('utf-8') == (
        '{"output_path":"' + str(tmp_path / 'unique.mid') + '",'
        '"unique_path":"' + str(tmp_path / 'unique.mid') + '",'
        '"status":"validated","validation_passed":true,'
        '"midi_data":"YWJj","checks":{"ok":true},"stats":{"kind":"orch"}}'
    )


def test_get_repo_commit_id_returns_short_hash(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.subprocess, 'check_output', lambda *args, **kwargs: 'abc123\n')

    assert _get_repo_commit_id() == 'abc123'


def test_get_repo_commit_id_returns_none_on_failure(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.subprocess, 'check_output', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('git failed')))

    assert _get_repo_commit_id() is None


def test_build_execution_metadata_returns_hash_and_duration(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.time, 'time', lambda: 10.25)

    metadata = _build_execution_metadata(b'abc', 10.0)

    assert metadata['execution_duration_ms'] == 250
    assert metadata['output_midi_hash'] == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

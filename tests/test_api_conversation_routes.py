from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from arranger.api import app


client = TestClient(app)


def _uploaded_midi():
    return ('demo.mid', BytesIO(b'midi-bytes'), 'audio/midi')


def test_health_route_reports_healthy_status():
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}


def test_list_samples_filters_internal_mid_files_and_formats_display_names(monkeypatch, tmp_path):
    from arranger import api

    for filename in [
        'simple_melody.mid',
        'piano_chords.mid',
        'full_band.mid',
        'orch-demo.midi',
    ]:
        (tmp_path / filename).write_bytes(b'midi')

    monkeypatch.setattr(api, 'SAMPLES_DIR', Path(tmp_path))

    response = client.get('/samples')

    assert response.status_code == 200
    assert sorted(response.json()['samples'], key=lambda sample: sample['filename']) == [
        {
            'name': 'full_band',
            'filename': 'full_band.mid',
            'display_name': 'full band',
        },
        {
            'name': 'orch-demo',
            'filename': 'orch-demo.midi',
            'display_name': 'orch demo',
        },
    ]


def test_download_sample_returns_midi_file(monkeypatch, tmp_path):
    from arranger import api

    sample_path = tmp_path / 'demo.mid'
    sample_path.write_bytes(b'sample-midi')
    monkeypatch.setattr(api, 'SAMPLES_DIR', Path(tmp_path))

    response = client.get('/samples/demo.mid')

    assert response.status_code == 200
    assert response.content == b'sample-midi'
    assert response.headers['content-type'] == 'audio/midi'
    assert 'filename="demo.mid"' in response.headers['content-disposition']


def test_download_sample_returns_404_for_missing_file(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'SAMPLES_DIR', Path(tmp_path))

    response = client.get('/samples/missing.mid')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Sample not found'}


def test_download_file_returns_generated_midi(monkeypatch, tmp_path):
    from arranger import api

    output_path = tmp_path / 'arranged.mid'
    output_path.write_bytes(b'arranged-midi')
    monkeypatch.setattr(api, 'STORAGE_DIR', Path(tmp_path))

    response = client.get('/files/arranged.mid')

    assert response.status_code == 200
    assert response.content == b'arranged-midi'
    assert response.headers['content-type'] == 'audio/midi'
    assert 'filename="arranged.mid"' in response.headers['content-disposition']


def test_download_file_returns_404_for_missing_output(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', Path(tmp_path))

    response = client.get('/files/missing.mid')

    assert response.status_code == 404
    assert response.json() == {'detail': 'File not found'}


def test_analyze_midi_returns_built_payload(monkeypatch):
    from arranger import api

    analyzed_result = SimpleNamespace(tracks=[SimpleNamespace(index=0, name='Lead')])
    calls = {}

    class DummyMidiAnalysisService:
        def analyze(self, midi_data):
            calls['analyze'] = midi_data
            return analyzed_result

    monkeypatch.setattr(api, 'MidiAnalysisService', DummyMidiAnalysisService)
    monkeypatch.setattr(
        api,
        '_build_analyze_payload',
        lambda result: (
            calls.setdefault('build_analyze_payload', result) or None,
            {'tracks_count': len(result.tracks)},
        )[1],
    )

    response = client.post('/analyze_midi', files={'file': _uploaded_midi()})

    assert response.status_code == 200
    assert response.json() == {'tracks_count': 1}
    assert calls['analyze'] == b'midi-bytes'
    assert calls['build_analyze_payload'] is analyzed_result


def test_revise_section_revision_returns_not_implemented(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'id': conversation_id})

    response = client.post(
        '/revise',
        data={
            'conversation_id': 'conv-1',
            'revision_json': '{"type":"section","section_id":"verse","instruction":"more strings"}',
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'status': 'not_implemented',
        'message': 'Section revision requires LLM interpretation',
    }


def test_revise_global_revision_updates_plan(monkeypatch):
    from arranger import api

    calls = {}
    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'id': conversation_id})
    monkeypatch.setattr(
        api.conversation_manager,
        'update_latest_plan',
        lambda conversation_id, plan: calls.setdefault(
            'update_latest_plan',
            {'conversation_id': conversation_id, 'plan': plan},
        ),
    )

    response = client.post(
        '/revise',
        data={
            'conversation_id': 'conv-1',
            'revision_json': '{"type":"global","plan":{"after":true}}',
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'status': 'updated',
        'plan': {'after': True},
    }
    assert calls['update_latest_plan'] == {
        'conversation_id': 'conv-1',
        'plan': {'after': True},
    }


def test_revise_rejects_invalid_json(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'id': conversation_id})

    response = client.post(
        '/revise',
        data={'conversation_id': 'conv-1', 'revision_json': '{bad json'},
    )

    assert response.status_code == 400
    assert response.json() == {'detail': 'Invalid JSON'}


def test_revise_rejects_unknown_conversation(monkeypatch):
    from arranger import api

    monkeypatch.setattr(
        api.conversation_manager,
        'get_conversation',
        lambda conversation_id: None,
    )

    response = client.post(
        '/revise',
        data={
            'conversation_id': 'missing',
            'revision_json': '{"type":"global","plan":{"after":true}}',
        },
    )

    assert response.status_code == 404
    assert response.json() == {'detail': 'Conversation not found'}


def test_render_rejects_invalid_format():
    response = client.post(
        '/render',
        files={'file': _uploaded_midi(), 'format': (None, 'wav')},
    )

    assert response.status_code == 400
    assert response.json() == {'detail': "Format must be 'pdf' or 'mp3'"}


def test_render_pdf_returns_not_implemented_payload(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.uuid, 'uuid4', lambda: SimpleNamespace(hex='pdf123'))

    response = client.post(
        '/render',
        files={'file': _uploaded_midi(), 'format': (None, 'pdf')},
    )

    assert response.status_code == 200
    assert response.json() == {
        'status': 'not_implemented',
        'message': 'PDF rendering requires MuseScore integration',
    }


def test_render_mp3_returns_not_implemented_payload(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.uuid, 'uuid4', lambda: SimpleNamespace(hex='mp3123'))

    response = client.post(
        '/render',
        files={'file': _uploaded_midi(), 'format': (None, 'mp3')},
    )

    assert response.status_code == 200
    assert response.json() == {
        'status': 'not_implemented',
        'message': 'MP3 rendering requires FluidSynth integration',
    }


def test_get_conversation_prefers_conversation_manager(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.conversation_manager, 'get_conversation', lambda conversation_id: {'id': conversation_id, 'source': 'manager'})

    response = client.get('/conversation/conv-1')

    assert response.status_code == 200
    assert response.json() == {'id': 'conv-1', 'source': 'manager'}


def test_get_conversation_returns_404_when_missing(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.conversation_manager, 'get_conversation', lambda conversation_id: None)

    response = client.get('/conversation/missing')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Conversation not found'}


def test_send_message_happy_path_uses_shared_helpers(monkeypatch):
    from arranger import api

    tracer = SimpleNamespace()
    plan = SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})
    calls = {'require_conversation': 0}

    async def fake_read_optional_midi_analysis(midi_file, tracer_arg):
        calls['read_optional_midi_analysis'] = {
            'filename': midi_file.filename if midi_file else None,
            'tracer': tracer_arg,
        }
        return {'analysis': True}

    def fake_lint_plan(plan_dict):
        calls['lint_plan'] = plan_dict
        return SimpleNamespace(
            passed=True,
            warnings=[],
            get_summary=lambda: 'ok',
        )

    monkeypatch.setattr(
        api,
        '_require_conversation',
        lambda conversation_id: calls.__setitem__('require_conversation', calls['require_conversation'] + 1) or {
            'id': conversation_id,
            'arrangement_versions': [],
        },
    )
    monkeypatch.setattr(api, '_start_conversation_trace', lambda conversation_id, stage_name: tracer)
    monkeypatch.setattr(
        api,
        '_record_user_message',
        lambda conversation_id, message: calls.setdefault(
            'record_user_message',
            {'conversation_id': conversation_id, 'message': message},
        ),
    )
    monkeypatch.setattr(api, '_read_optional_midi_analysis', fake_read_optional_midi_analysis)
    monkeypatch.setattr(
        api,
        '_generate_or_revise_plan',
        lambda **kwargs: (
            calls.setdefault('generate_or_revise_plan', kwargs) or None,
            None,
        ) and (
            plan,
            SimpleNamespace(message='updated'),
            SimpleNamespace(is_revision=True),
            None,
        ),
    )
    monkeypatch.setattr(api, 'lint_plan', fake_lint_plan)
    monkeypatch.setattr(api, '_build_lint_warnings_payload', lambda lint_result: {'passed': True, 'warnings': []})
    monkeypatch.setattr(api, '_build_revision_response_payload', lambda revision_intent, revision_result: {'is_revision': True})
    monkeypatch.setattr(
        api,
        '_finalize_generated_plan_response',
        lambda **kwargs: (
            calls.setdefault('finalize_generated_plan_response', kwargs) or None,
            JSONResponse(content={'status': 'generated', 'route': 'message'}),
        )[1],
    )

    response = client.post(
        '/conversation/conv-1/message',
        files={
            'message': (None, 'make it brighter'),
            'include_trace': (None, 'true'),
            'midi_file': _uploaded_midi(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {'status': 'generated', 'route': 'message'}
    assert calls['require_conversation'] == 2
    assert calls['record_user_message'] == {
        'conversation_id': 'conv-1',
        'message': 'make it brighter',
    }
    assert calls['read_optional_midi_analysis'] == {
        'filename': 'demo.mid',
        'tracer': tracer,
    }
    assert calls['generate_or_revise_plan'] == {
        'conversation': {'id': 'conv-1', 'arrangement_versions': []},
        'conversation_id': 'conv-1',
        'message': 'make it brighter',
        'analyze_result': {'analysis': True},
        'tracer': tracer,
    }
    assert calls['lint_plan'] == {'transform': {'type': 'orchestration'}}
    assert calls['finalize_generated_plan_response'] == {
        'conversation_id': 'conv-1',
        'plan': plan,
        'tracer': tracer,
        'include_trace': True,
        'user_intent': 'make it brighter',
        'midi_filename': 'demo.mid',
        'analyze_result': {'analysis': True},
        'lint_payload': {'passed': True, 'warnings': []},
        'revision_payload': {'is_revision': True},
        'update_intent_to': 'make it brighter',
        'generation_intent': 'make it brighter',
    }


def test_send_message_returns_lint_failure_without_finalizing(monkeypatch):
    from arranger import api

    plan = SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})
    calls = {}

    async def fake_read_optional_midi_analysis(midi_file, tracer):
        return None

    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'arrangement_versions': []})
    monkeypatch.setattr(api, '_start_conversation_trace', lambda conversation_id, stage_name: SimpleNamespace())
    monkeypatch.setattr(api, '_record_user_message', lambda conversation_id, message: None)
    monkeypatch.setattr(api, '_read_optional_midi_analysis', fake_read_optional_midi_analysis)
    monkeypatch.setattr(
        api,
        '_generate_or_revise_plan',
        lambda **kwargs: (plan, None, None, None),
    )
    monkeypatch.setattr(
        api,
        'lint_plan',
        lambda plan_dict: SimpleNamespace(
            passed=False,
            warnings=[],
            get_summary=lambda: '1 error',
        ),
    )
    monkeypatch.setattr(
        api,
        '_build_lint_failure_response',
        lambda lint_result, conversation_id: (
            calls.setdefault(
                'build_lint_failure_response',
                {'lint_result': lint_result, 'conversation_id': conversation_id},
            ) or None,
            JSONResponse(status_code=400, content={'error': 'lint_failed'}),
        )[1],
    )
    monkeypatch.setattr(
        api,
        '_finalize_generated_plan_response',
        lambda **kwargs: (_ for _ in ()).throw(AssertionError('finalize should not be called')),
    )

    response = client.post(
        '/conversation/conv-1/message',
        files={'message': (None, 'make it brighter')},
    )

    assert response.status_code == 400
    assert response.json() == {'error': 'lint_failed'}
    assert calls['build_lint_failure_response']['conversation_id'] == 'conv-1'


def test_regenerate_from_feedback_rejects_missing_feedback(monkeypatch):
    from arranger import api

    monkeypatch.setattr(
        api,
        '_require_conversation',
        lambda conversation_id: {
            'initial_intent': 'original intent',
            'arrangement_versions': [],
        },
    )
    monkeypatch.setattr(api, '_start_conversation_trace', lambda conversation_id, stage_name: SimpleNamespace())

    response = client.post(
        '/conversation/conv-1/regenerate',
        files={'include_trace': (None, 'true')},
    )

    assert response.status_code == 400
    assert response.json() == {'detail': 'No feedback available for regeneration'}


def test_regenerate_from_feedback_happy_path_uses_finalize_helper(monkeypatch):
    from arranger import api

    tracer = SimpleNamespace(start_stage=lambda stage_name: None)
    plan = SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})
    calls = {}

    monkeypatch.setattr(
        api,
        '_require_conversation',
        lambda conversation_id: {
            'initial_intent': 'original intent',
            'current_intent': 'refined intent',
            'arrangement_versions': [{'version_id': '1', 'user_feedback': 'more strings'}],
        },
    )
    monkeypatch.setattr(api, '_start_conversation_trace', lambda conversation_id, stage_name: tracer)

    async def fake_resolve_regenerate_analyze_result(conversation_id, conversation, midi_file, tracer_arg):
        calls['resolve_regenerate_analyze_result'] = {
            'conversation_id': conversation_id,
            'conversation': conversation,
            'filename': midi_file.filename if midi_file else None,
            'tracer': tracer_arg,
        }
        return {'analysis': True}

    monkeypatch.setattr(api, '_resolve_regenerate_analyze_result', fake_resolve_regenerate_analyze_result)

    class DummyPlanner:
        def __init__(self, conversation_id):
            calls['planner_conversation_id'] = conversation_id

        def generate_plan(self, analyze_result, user_intent, previous_feedback):
            calls['generate_plan'] = {
                'analyze_result': analyze_result,
                'user_intent': user_intent,
                'previous_feedback': previous_feedback,
            }
            return plan

    monkeypatch.setattr(api, 'LLMPlanner', DummyPlanner)
    monkeypatch.setattr(
        api,
        '_finalize_generated_plan_response',
        lambda **kwargs: (
            calls.setdefault('finalize_generated_plan_response', kwargs) or None,
            JSONResponse(content={'status': 'generated', 'route': 'regenerate'}),
        )[1],
    )

    response = client.post(
        '/conversation/conv-1/regenerate',
        files={
            'include_trace': (None, 'true'),
            'midi_file': _uploaded_midi(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {'status': 'generated', 'route': 'regenerate'}
    assert calls['resolve_regenerate_analyze_result'] == {
        'conversation_id': 'conv-1',
        'conversation': {
            'initial_intent': 'original intent',
            'current_intent': 'refined intent',
            'arrangement_versions': [{'version_id': '1', 'user_feedback': 'more strings'}],
        },
        'filename': 'demo.mid',
        'tracer': tracer,
    }
    assert calls['planner_conversation_id'] == 'conv-1'
    assert calls['generate_plan'] == {
        'analyze_result': {'analysis': True},
        'user_intent': 'refined intent',
        'previous_feedback': 'v1: more strings',
    }
    assert calls['finalize_generated_plan_response'] == {
        'conversation_id': 'conv-1',
        'plan': plan,
        'tracer': tracer,
        'include_trace': True,
        'feedback_used': 'v1: more strings',
        'generation_intent': 'refined intent',
    }


def test_regenerate_from_feedback_uses_saved_analysis_without_upload(monkeypatch):
    from arranger import api

    tracer = SimpleNamespace(start_stage=lambda stage_name: None)
    calls = {}

    monkeypatch.setattr(
        api,
        '_require_conversation',
        lambda conversation_id: {
            'initial_intent': 'original intent',
            'current_intent': 'updated intent',
            'arrangement_versions': [{'version_id': '1', 'user_feedback': 'more strings'}],
            'metadata': {'last_midi_analysis': {'tempo': 120}},
        },
    )
    monkeypatch.setattr(api, '_start_conversation_trace', lambda conversation_id, stage_name: tracer)

    async def fake_resolve_regenerate_analyze_result(conversation_id, conversation, midi_file, tracer_arg):
        calls['resolve_called'] = midi_file is None
        return {'analysis': 'saved'}

    monkeypatch.setattr(api, '_resolve_regenerate_analyze_result', fake_resolve_regenerate_analyze_result)

    class DummyPlanner:
        def __init__(self, conversation_id):
            pass

        def generate_plan(self, analyze_result, user_intent, previous_feedback):
            calls['generate_plan'] = {
                'analyze_result': analyze_result,
                'user_intent': user_intent,
                'previous_feedback': previous_feedback,
            }
            return SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})

    monkeypatch.setattr(api, 'LLMPlanner', DummyPlanner)
    monkeypatch.setattr(
        api,
        '_finalize_generated_plan_response',
        lambda **kwargs: JSONResponse(content={'ok': True}),
    )

    response = client.post('/conversation/conv-1/regenerate')

    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert calls['resolve_called'] is True
    assert calls['generate_plan'] == {
        'analyze_result': {'analysis': 'saved'},
        'user_intent': 'updated intent',
        'previous_feedback': 'v1: more strings',
    }


def test_submit_feedback_records_feedback_and_message(monkeypatch):
    from arranger import api

    calls = {}
    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'id': conversation_id})
    monkeypatch.setattr(
        api.conversation_manager,
        'update_version_feedback',
        lambda **kwargs: calls.setdefault('update_version_feedback', kwargs),
    )
    monkeypatch.setattr(
        api,
        '_record_user_message',
        lambda conversation_id, message: calls.setdefault(
            'record_user_message',
            {'conversation_id': conversation_id, 'message': message},
        ),
    )

    response = client.post(
        '/conversation/conv-1/feedback',
        data={'version_id': 'v2', 'feedback': 'more strings'},
    )

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'version_id': 'v2',
        'status': 'feedback_recorded',
    }
    assert calls['update_version_feedback'] == {
        'conversation_id': 'conv-1',
        'version_id': 'v2',
        'feedback': 'more strings',
    }
    assert calls['record_user_message'] == {
        'conversation_id': 'conv-1',
        'message': '[反馈 vv2]: more strings',
    }


def test_get_history_uses_public_history_payload(monkeypatch):
    from arranger import api

    conversation = {
        'initial_intent': 'start',
        'current_intent': 'now',
        'messages': [{'role': 'user'}],
        'llm_thoughts': [],
        'processing_steps': [],
        'arrangement_versions': [{'version_id': 'v1', 'status': 'generated', 'created_at': 'now'}],
    }
    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: conversation)

    response = client.get('/conversation/conv-1/history')

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'initial_intent': 'start',
        'current_intent': 'now',
        'messages': [{'role': 'user'}],
        'llm_thoughts': [],
        'processing_steps': [],
        'arrangement_versions': [
            {
                'version_id': 'v1',
                'status': 'generated',
                'created_at': 'now',
                'has_feedback': False,
            }
        ],
    }


def test_export_conversation_route_returns_export_summary(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'id': conversation_id})
    monkeypatch.setattr(
        api,
        '_export_conversation_data',
        lambda conversation_id: {
            'conversation_id': conversation_id,
            'export_path': '/tmp/export.json',
            'versions_count': 2,
            'messages_count': 3,
            'llm_thoughts_count': 4,
        },
    )

    response = client.get('/conversation/conv-1/export')

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'export_path': '/tmp/export.json',
        'versions_count': 2,
        'messages_count': 3,
        'llm_thoughts_count': 4,
    }


def test_get_trace_returns_exported_trace(monkeypatch):
    from arranger import api

    tracer = SimpleNamespace(export=lambda: {'events': [{'stage': 'plan_generation'}]})
    monkeypatch.setattr(api, '_require_conversation', lambda conversation_id: {'id': conversation_id})
    monkeypatch.setattr(api, 'get_tracer', lambda conversation_id: tracer)

    response = client.get('/conversation/conv-1/trace')

    assert response.status_code == 200
    assert response.json() == {'events': [{'stage': 'plan_generation'}]}


def test_get_session_log_returns_serialized_log(monkeypatch):
    from arranger import api

    monkeypatch.setattr(
        api,
        '_require_session_log',
        lambda conversation_id, version_id: SimpleNamespace(version_id=version_id, status='generated'),
    )
    monkeypatch.setattr(api, '_build_session_log_payload', lambda log: {'version_id': log.version_id, 'status': log.status})

    response = client.get('/session/conv-1/v1')

    assert response.status_code == 200
    assert response.json() == {'version_id': 'v1', 'status': 'generated'}


def test_get_session_versions_returns_wrapped_versions(monkeypatch):
    from arranger import api

    logs = [
        SimpleNamespace(
            version_id='v1',
            created_at='2026-04-09T00:00:00',
            status='generated',
            plan={'ensemble': {'parts': [{}]}},
            user_intent='hello',
        )
    ]
    monkeypatch.setattr(api.session_logger, 'get_session_logs', lambda conversation_id: logs)

    response = client.get('/session/conv-1/versions')

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'versions': [
            {
                'version_id': 'v1',
                'created_at': '2026-04-09T00:00:00',
                'status': 'generated',
                'plan_parts_count': 1,
                'user_intent_preview': 'hello',
            }
        ],
    }


def test_list_conversations_returns_wrapped_payload(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.conversation_manager, 'list_conversations', lambda: [{'id': 'conv-1'}])

    response = client.get('/conversations')

    assert response.status_code == 200
    assert response.json() == {'conversations': [{'id': 'conv-1'}]}


def test_list_sessions_returns_wrapped_payload(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.session_logger, 'list_sessions', lambda: [{'conversation_id': 'conv-1'}])

    response = client.get('/sessions')

    assert response.status_code == 200
    assert response.json() == {'sessions': [{'conversation_id': 'conv-1'}]}


def test_create_conversation_returns_created_payload(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.conversation_manager, 'create_conversation', lambda user_intent, metadata: 'conv-1')
    monkeypatch.setattr(
        api,
        '_build_create_conversation_response',
        lambda conversation_id: {
            'conversation_id': conversation_id,
            'created_at': '2026-04-09T12:00:00',
            'status': 'active',
        },
    )

    response = client.post('/conversation', data={'user_intent': 'make it brighter'})

    assert response.status_code == 200
    assert response.json() == {
        'conversation_id': 'conv-1',
        'created_at': '2026-04-09T12:00:00',
        'status': 'active',
    }


def test_midi_duration_returns_computed_payload(monkeypatch):
    from arranger import api

    monkeypatch.setattr(api.MidiReader, 'read_midi', lambda midi_data: 'midi')
    monkeypatch.setattr(
        api,
        'MidiAnalyzer',
        lambda midi: SimpleNamespace(analyze=lambda: SimpleNamespace(total_ticks=960, ticks_per_beat=480, tempo=120)),
    )

    response = client.post(
        '/midi_duration',
        files={'file': _uploaded_midi()},
    )

    assert response.status_code == 200
    assert response.json() == {
        'duration_sec': 1.0,
        'total_ticks': 960,
        'ticks_per_beat': 480,
        'tempo': 120,
    }


def test_plan_route_returns_generated_plan_payload(monkeypatch):
    from arranger import api

    analyzed_result = SimpleNamespace(
        tracks=[SimpleNamespace(index=0, name='Lead', notes=[SimpleNamespace(pitch=64)])],
        melody_candidates=[SimpleNamespace(track_index=0, score=0.9, reason='clear melody')],
        total_ticks=480,
        ticks_per_beat=480.0,
        tempo=120.0,
        time_signature=(4, 4),
    )
    generated_plan = SimpleNamespace(model_dump=lambda: {'transform': {'type': 'orchestration'}})
    tracer = SimpleNamespace(start_stage=lambda stage_name: None, log_midi_analysis=lambda payload: None)

    class DummyMidiAnalysisService:
        def analyze(self, midi_data):
            return analyzed_result

    class DummyPlanner:
        def generate_plan(self, analyze_result, user_intent, target_size):
            return generated_plan

    monkeypatch.setattr(api, 'MidiAnalysisService', DummyMidiAnalysisService)
    monkeypatch.setattr(api, 'LLMPlanner', lambda: DummyPlanner())
    monkeypatch.setattr(api, 'get_tracer', lambda conversation_id: tracer)

    response = client.post(
        '/plan',
        files={'file': _uploaded_midi(), 'user_intent': (None, 'make it brighter')},
    )

    assert response.status_code == 200
    assert response.json() == {
        'plan': {'transform': {'type': 'orchestration'}},
        'analyze': {
            'tracks_count': 1,
            'tempo': 120,
            'time_signature': '4/4',
            'melody_candidates': [{'track_index': 0, 'score': 0.9}],
        },
    }

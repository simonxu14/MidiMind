from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient

from arranger.api import app


client = TestClient(app)


PLAN_JSON = '{"transform":{"type":"orchestration"},"ensemble":{"parts":[]},"constraints":{},"outputs":{"midi":{}}}'
DIFFICULTY_PLAN_JSON = '{"transform":{"type":"difficulty","direction":"down"},"ensemble":{"parts":[]},"constraints":{},"outputs":{"midi":{}}}'
CREATIVE_PLAN_JSON = '{"transform":{"type":"creative"},"ensemble":{"parts":[]},"constraints":{},"outputs":{"midi":{}}}'


def _upload_fields(plan_json):
    return {
        'plan_json': (None, plan_json),
        'melody_track': (None, '0'),
    }


def _midi_file():
    return ('demo.mid', BytesIO(b'midi-bytes'), 'audio/midi')


def test_arrange_orchestration_path_returns_base64_and_paths(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(api, '_parse_plan_json', lambda _: SimpleNamespace(transform=SimpleNamespace(type='orchestration')))
    monkeypatch.setattr(api, '_resolve_melody_track_index', lambda plan, melody_track: 2)
    monkeypatch.setattr(api, '_sanitize_melody_track_index', lambda midi_data, index: index)
    monkeypatch.setattr(api, '_select_executor_and_run', lambda plan, midi_data, melody_track_index: ([('track', {})], {'kind': 'orch'}))
    monkeypatch.setattr(
        api,
        '_write_arranged_output',
        lambda midi_data, output_tracks: {
            'output_data': b'abc',
            'output_path': tmp_path / 'arranged_unique.mid',
        },
    )
    monkeypatch.setattr(
        api,
        'Validator',
        lambda plan: SimpleNamespace(
            validate=lambda midi_data, output_tracks: SimpleNamespace(to_dict=lambda: {'ok': True}, all_passed=True)
        ),
    )
    monkeypatch.setattr(api, '_update_arrangement_version_result_safe', lambda **kwargs: None)

    response = client.post(
        '/arrange',
        files={
            'file': _midi_file(),
            **_upload_fields(PLAN_JSON),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'output_path': str(tmp_path / 'arranged_unique.mid'),
        'unique_path': str(tmp_path / 'arranged_unique.mid'),
        'status': 'validated',
        'validation_passed': True,
        'midi_data': 'YWJj',
        'checks': {'ok': True},
        'stats': {'kind': 'orch'},
    }


def test_arrange_difficulty_path_returns_simple_output(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(api, '_parse_plan_json', lambda _: SimpleNamespace(transform=SimpleNamespace(type='difficulty', direction='down')))
    monkeypatch.setattr(api, '_resolve_melody_track_index', lambda plan, melody_track: 0)
    monkeypatch.setattr(api, '_sanitize_melody_track_index', lambda midi_data, index: index)

    class DummySimplifyExecutor:
        def __init__(self, plan):
            self.plan = plan

        def execute(self, midi_data):
            assert midi_data == b'midi-bytes'
            return b'simplified-midi'

    monkeypatch.setattr(api, 'SimplifyExecutor', DummySimplifyExecutor)
    monkeypatch.setattr(api.uuid, 'uuid4', lambda: SimpleNamespace(hex='abcdef1234567890'))

    response = client.post(
        '/arrange',
        files={
            'file': _midi_file(),
            **_upload_fields(DIFFICULTY_PLAN_JSON),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'output_path': str(tmp_path / 'output_abcdef1234567890.mid'),
        'checks': {},
        'stats': {'type': 'difficulty'},
    }
    assert (tmp_path / 'output_abcdef1234567890.mid').read_bytes() == b'simplified-midi'


def test_arrange_creative_path_uses_shared_helpers(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(api, '_parse_plan_json', lambda _: SimpleNamespace(transform=SimpleNamespace(type='creative')))
    monkeypatch.setattr(api, '_resolve_melody_track_index', lambda plan, melody_track: 0)
    monkeypatch.setattr(api, '_sanitize_melody_track_index', lambda midi_data, index: index)

    called = {}

    def fake_select(plan, midi_data, melody_track_index):
        called['select'] = (midi_data, melody_track_index)
        return ([('creative-track', {})], {'kind': 'creative'})

    def fake_write(midi_data, output_tracks):
        called['write'] = (midi_data, output_tracks)
        return {
            'output_data': b'xyz',
            'output_path': tmp_path / 'creative_unique.mid',
        }

    monkeypatch.setattr(api, '_select_executor_and_run', fake_select)
    monkeypatch.setattr(api, '_write_arranged_output', fake_write)
    monkeypatch.setattr(
        api,
        'Validator',
        lambda plan: SimpleNamespace(
            validate=lambda midi_data, output_tracks: SimpleNamespace(to_dict=lambda: {'valid': True}, all_passed=True)
        ),
    )
    monkeypatch.setattr(api, '_update_arrangement_version_result_safe', lambda **kwargs: None)

    response = client.post(
        '/arrange',
        files={
            'file': _midi_file(),
            **_upload_fields(CREATIVE_PLAN_JSON),
        },
    )

    assert response.status_code == 200
    assert called['select'] == (b'midi-bytes', 0)
    assert called['write'] == (b'midi-bytes', [('creative-track', {})])
    assert response.json() == {
        'output_path': str(tmp_path / 'creative_unique.mid'),
        'unique_path': str(tmp_path / 'creative_unique.mid'),
        'status': 'validated',
        'validation_passed': True,
        'midi_data': 'eHl6',
        'checks': {'valid': True},
        'stats': {'kind': 'creative'},
    }


def test_arrange_orchestration_returns_validation_failed_status_when_checks_fail(monkeypatch, tmp_path):
    from arranger import api

    monkeypatch.setattr(api, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(api, '_parse_plan_json', lambda _: SimpleNamespace(transform=SimpleNamespace(type='orchestration')))
    monkeypatch.setattr(api, '_resolve_melody_track_index', lambda plan, melody_track: 0)
    monkeypatch.setattr(api, '_sanitize_melody_track_index', lambda midi_data, index: index)
    monkeypatch.setattr(api, '_select_executor_and_run', lambda plan, midi_data, melody_track_index: ([('track', {})], {'kind': 'orch'}))
    monkeypatch.setattr(
        api,
        '_write_arranged_output',
        lambda midi_data, output_tracks: {
            'output_data': b'abc',
            'output_path': tmp_path / 'arranged_unique.mid',
        },
    )
    monkeypatch.setattr(
        api,
        'Validator',
        lambda plan: SimpleNamespace(
            validate=lambda midi_data, output_tracks: SimpleNamespace(
                to_dict=lambda: {'all_passed': False, 'errors': ['instrumentation mismatch']},
                all_passed=False,
            )
        ),
    )
    monkeypatch.setattr(api, '_update_arrangement_version_result_safe', lambda **kwargs: None)

    response = client.post(
        '/arrange',
        files={
            'file': _midi_file(),
            **_upload_fields(PLAN_JSON),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'output_path': str(tmp_path / 'arranged_unique.mid'),
        'unique_path': str(tmp_path / 'arranged_unique.mid'),
        'status': 'validation_failed',
        'validation_passed': False,
        'midi_data': 'YWJj',
        'checks': {'all_passed': False, 'errors': ['instrumentation mismatch']},
        'stats': {'kind': 'orch'},
    }

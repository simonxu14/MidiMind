# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

MidiMind is an AI-driven MIDI arrangement assistant that transforms simple melodies into professional ensemble scores. The system uses an LLM as "arrangement director" to plan strategy, while deterministic Python scripts handle actual MIDI event manipulation.

## Architecture

```
MIDI Input → LLM Planner → UnifiedPlan JSON → OrchestrateExecutor → Validator → MIDI Output
                                              ↓
                              Templates + Guards + AutoFixer
```

### Core Data Flow (orchestrate_executor.py)

1. **Parse MIDI** → extract tracks, tempo, time_signature
2. **Lock melody** → copy melody track note-for-note
3. **Analyze harmony** → per-measure chord extraction using `choose_triadish()`
4. **Build ArrangementContext** → includes meter_grid, section_modes, melody_onsets
5. **Generate parts via templates** → piano, strings, winds, brass, percussion
6. **Apply Guards** → onset_avoidance (scale/delay/drop), velocity_caps, register_separation
7. **AutoFixer** → fix out_of_range, octave_jumps, voice_crossing, parallel_fifths
8. **Validate & Output**

### Key Files

| File | Purpose |
|------|---------|
| `src/arranger/api.py` | FastAPI service, all HTTP endpoints |
| `src/arranger/plan_schema.py` | Pydantic models: UnifiedPlan, GuardsConfig, ArrangementConfig, ChordInfo, NoteEvent |
| `src/arranger/orchestrate_executor.py` | Main编排执行器, template selection, guards, stats |
| `src/arranger/auto_fixer.py` | Fixes: out_of_range, octave_jumps(>19 semitones), voice_crossing, parallel_fifths |
| `src/arranger/harmony_analyzer.py` | `choose_triadish()`, `analyze_chord_quality()`, `estimate_section_modes()` |
| `src/arranger/timebase.py` | `beats_per_measure()`, `meter_grid()` for compound meters (6/8, 9/8) |
| `src/arranger/midi_io.py` | MidiReader, MidiWriter, MidiAnalyzer |
| `src/arranger/templates/registry.py` | TemplateRegistry with auto-discovery |
| `src/arranger/templates/base.py` | BaseTemplate ABC with `per_measure_select` flag |

### NoteEvent Format

```python
NoteEvent = Tuple[int, int, int, int, int]  # (start_tick, end_tick, pitch, velocity, channel)
```

### Guards System

- **onset_avoidance_action**: `scale_velocity` (default, 0.6 ratio) | `delay` (15-30 ticks) | `drop`
- Per-part priority: `part.id` → `instrument` → `default`
- **velocity_caps_by_mode**: A/B/C/D mode-specific caps per instrument
- **register_separation**: min 5 semitones from melody, strategies: octave_shift → chord_tone → skip

### AutoFixer Channel Handling

```python
# AutoFixer uses int keys for channel lookup (line 124-129):
if channel in instrument_ranges:
    range_min, range_max = instrument_ranges[channel]
elif str(channel) in instrument_ranges:  # fallback to string
    range_min, range_max = instrument_ranges[str(channel)]
else:
    range_min, range_max = (21, 108)  # piano fallback
```

Percussion (channel 9) is skipped in voice_crossing fixes.

## Commands

### Run the service
```bash
cd /opt/midimind/src
export PYTHONPATH=/opt/midimind/src
export ANTHROPIC_API_KEY=...
export ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
python3 -m arranger.api --host 0.0.0.0 --port 8000
```

### Run tests
```bash
cd /opt/midimind
pytest tests/ -v
pytest tests/test_integration.py -v -k "test_name"  # single test
```

### Template discovery
Templates are auto-discovered via `TemplateRegistry.discover_templates()`. Each template in `templates/*/` is a class inheriting `BaseTemplate` with:
- `name`: unique identifier
- `applicable_instruments`, `applicable_roles`: matching criteria
- `per_measure_select`: True if template handles per-measure iteration internally
- `generate(context, params) -> List[NoteEvent]`

## Important Patterns

### Per-measure vs Per-context template generation
- `per_measure_select=True` templates (e.g., `adaptive_accompaniment`): receive full context, iterate internally
- `per_measure_select=False` templates (e.g., `alberti_8ths`): external loop in `_generate_part_per_measure()` creates sub_context per measure

### Section Modes
Four modes (A/B/C/D) determined by 8-bar blocks based on:
- D (高潮): avg_velocity >= 85
- B (流动): note_density > 80
- C (明亮): avg_pitch > 72
- A (透明): otherwise

### Instrument Ranges
```python
INSTRUMENT_RANGES = {
    "violin": (55, 96), "viola": (48, 81), "cello": (36, 72),
    "flute": (60, 96), "clarinet": (50, 99), "trumpet": (52, 84),
    "timpani": (45, 53), "piano": (21, 108),
}
```

### Percussion
- Timpani: GM channel 11, pitch 45-53, triggers at phrase_end_beat4
- Triangle: GM channel 9, note 81, triggers at phrase_start_beat1
- Auto-generated in `_auto_add_percussion()`, skips if percussion parts already exist in plan

## Common Issues & Fixes

1. **Channel key type bug**: AutoFixer uses `channel` (int) directly, not string
2. **Flute min_rest_beats**: Set to 0.5 (not 1.0) to allow consecutive melody
3. **onset_avoidance per-part**: `part.id` > `instrument` > `default` priority lookup
4. **total_ticks clipping**: P0-1 fix ensures notes beyond input MIDI total_ticks are clipped

## Environment Variables

- `PYTHONPATH`: Must include `/opt/midimind/src` when running from outside src/
- `ANTHROPIC_API_KEY`: API key for LLM planning
- `ANTHROPIC_BASE_URL`: LLM endpoint (default: https://api.minimaxi.com/anthropic)

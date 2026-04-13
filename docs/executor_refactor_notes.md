# Executor Refactor Notes

## Overview

As of April 3, 2026, `src/arranger/orchestrate_executor.py` has been reduced to a pipeline coordinator. Most concrete generation, post-processing, reporting, and output-building logic now lives in focused service modules under `src/arranger/services/`.

This split was done to improve:

- maintainability
- testability
- clarity of execution stages
- safety for future behavior-preserving refactors

## Current execution pipeline

The executor now mainly performs these steps:

1. Parse MIDI input.
2. Lock melody events to the configured melody part.
3. Analyze harmony.
4. Build `ArrangementContext`.
5. Generate non-melody parts.
6. Apply guards and optional humanization.
7. Run AutoFixer integration.
8. Apply per-measure mode velocity adjustments.
9. Auto-add percussion when configured.
10. Clip note events to input total ticks.
11. Build output MIDI tracks.
12. Generate arrangement report and top-level stats.

## Service map

### Core musical preparation

- `melody.py`
  - `lock_melody()`
- `harmony.py`
  - `analyze_harmony()`
  - `default_harmony()`
- `context_builder.py`
  - `build_arrangement_context()`
  - `build_register_targets()`

### Generation and guards

- `generation.py`
  - template selection
  - per-measure template generation
  - default accompaniment fallback
- `guards.py`
  - onset avoidance
  - velocity caps
  - range clipping
- `postprocess.py`
  - humanize
  - per-measure mode adjustments

### Repair, percussion, reporting, output

- `autofix_pipeline.py`
  - channel range building
  - AutoFixer application
  - regrouping fixed notes back to parts
- `percussion.py`
  - auto timpani generation
  - auto triangle generation
- `reporting.py`
  - arrangement report assembly
  - track-to-instrument-key mapping
- `output_builder.py`
  - CC insertion
  - MIDI output track construction
- `executor_state.py`
  - executor report-stats initialization

## Behavior fix kept during refactor

One real bug fix was intentionally preserved while extracting logic:

- Parts without explicit `template_name` should still auto-select templates through the registry even when piano template pool logic is not active.
- Before the fix, such parts could incorrectly fall back to sparse default accompaniment.

## Tests added during this refactor

A dedicated service test file was added:

- `tests/test_services.py`

It covers:

- generation fallback and auto-selection behavior
- percussion auto-generation
- arrangement reporting
- CC injection and output track building
- autofix pipeline helpers
- executor report-state initialization
- AutoFixer note-shape preservation (duration and velocity must survive regrouping)

## Post-refactor regression caught and fixed

During validation of the refactor, the 6/8 integration regression test exposed a subtle AutoFixer issue:

- notes were regrouped through `VoiceLine` structures
- the regroup/flatten path accidentally rebuilt note events with `end_tick=0` and `velocity=0`
- as a result, accompaniment tracks appeared present but produced silent `note_on velocity=0` events

The fix was to make `VoiceInfo` preserve full note shape (`tick`, `end_tick`, `pitch`, `velocity`, `channel`) and keep that data intact through octave-jump and voice-crossing processing.

This regression is now covered by service-level tests plus the existing 6/8 integration test.

The 6/8 regression test was also corrected so that it validates generated parts that actually exist in the test ensemble.

## Recommended next cleanup

If refactoring continues, the next low-risk targets are:

- moving velocity-cap lookup into a config/helper layer
- moving CC-mode lookup into a config/helper layer
- consolidating top-level stats assembly near reporting code

## Suggested commit boundary

To keep history clean, stage only files directly related to this refactor slice:

- `src/arranger/orchestrate_executor.py`
- `src/arranger/services/*`
- `tests/test_services.py`
- `tests/test_integration.py`
- optional docs such as this file

Avoid bundling unrelated local workspace changes in the same commit.

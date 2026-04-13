from __future__ import annotations

from typing import Dict, List, Tuple

from ..plan_schema import ArrangementContext, NoteEvent


def get_instrument_key_for_track(track_id: str, ensemble) -> str:
    if ensemble and ensemble.parts:
        for part in ensemble.parts:
            if part.id == track_id:
                instr = part.instrument.lower() if part.instrument else ""
                if "piano" in instr or "harp" in instr:
                    return "pf"
                if "viola" in instr:
                    return "va"
                if "cello" in instr or "violoncello" in instr:
                    return "vc"
                if "flute" in instr or "oboe" in instr or "clarinet" in instr:
                    return "winds"
                if "horn" in instr or "french_horn" in instr:
                    return "hn"

    lowered = track_id.lower()
    if "piano" in lowered or "pf" in lowered:
        return "pf"
    if "viola" in lowered or "va" in lowered:
        return "va"
    if "cello" in lowered or "vc" in lowered:
        return "vc"
    if "wind" in lowered:
        return "winds"
    if "horn" in lowered or "hn" in lowered:
        return "hn"
    return "pf"


def generate_arrangement_report(
    arrangement_context: ArrangementContext,
    accompaniment_tracks: Dict[str, List[NoteEvent]],
    output_tracks: List[List[Tuple[str, Dict]]],
    ensemble,
    report_stats: Dict,
) -> Dict[str, object]:
    report = {
        "section_modes": {},
        "piano_template_per_measure": {},
        "template_per_measure": report_stats["template_per_measure"].copy(),
        "guards_stats": {
            "onset_avoidance_hits": report_stats["onset_avoidance_hits"],
            "onset_scale_velocity_hits": report_stats["onset_scale_velocity_hits"],
            "onset_delay_hits": report_stats["onset_delay_hits"],
            "onset_drop_hits": report_stats["onset_drop_hits"],
            "exact_onset_collisions_by_part": report_stats["exact_onset_collisions_by_part"].copy(),
            "velocity_cap_hits": report_stats["velocity_cap_hits"],
        },
        "percussion_hits": report_stats["percussion_hits"],
        "template_usage": report_stats["template_per_part"].copy(),
        "fixes_applied": report_stats["fixes_applied"].copy(),
    }

    blocks = {}
    for measure_idx, mode in arrangement_context.section_modes.items():
        block_idx = measure_idx // 8
        blocks.setdefault(block_idx, {"mode": mode, "measures": []})["measures"].append(measure_idx)
    report["section_modes"] = {
        f"block_{k}": {"mode": v["mode"], "measures": v["measures"]}
        for k, v in blocks.items()
    }

    piano_part_id = None
    for part in ensemble.parts:
        if part.instrument and "piano" in part.instrument.lower():
            piano_part_id = part.id
            break

    if piano_part_id and piano_part_id in accompaniment_tracks:
        piano_notes = accompaniment_tracks[piano_part_id]
        measure_len = arrangement_context.measure_len
        for measure_idx, chord_info in arrangement_context.chord_per_measure.items():
            measure_start = measure_idx * measure_len
            notes_in_measure = [n for n in piano_notes if measure_start <= n[0] < measure_start + measure_len]
            template_name = report_stats["template_per_measure"].get(f"{piano_part_id}#m{measure_idx}", "unknown")
            report["piano_template_per_measure"][f"measure_{measure_idx}"] = {
                "template": template_name,
                "note_count": len(notes_in_measure),
                "chord_root": chord_info.root,
                "chord_quality": chord_info.quality,
            }

    for track_data in output_tracks:
        track_name = None
        note_count = 0
        for msg_type, params in track_data:
            if msg_type == "track_name":
                track_name = params.get("name", "")
            elif msg_type in ("note_on", "note_off"):
                note_count += 1
        if track_name in ("auto_timpani", "auto_triangle", "timpani", "triangle"):
            perc_type = "timpani" if "timpani" in track_name else "triangle"
            report["percussion_hits"][perc_type] = note_count

    return report

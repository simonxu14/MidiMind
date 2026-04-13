from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..plan_schema import ArrangementContext, NoteEvent, PartSpec, UnifiedPlan
from ..templates import BaseTemplate, TemplateRegistry

logger = logging.getLogger(__name__)


def select_template_for_part(
    part: PartSpec,
    context: ArrangementContext,
    plan: UnifiedPlan,
    template_registry: TemplateRegistry,
    report_stats: Dict,
    measure_idx: Optional[int] = None,
    template_window_cache: Optional[Dict] = None,
):
    import random

    instrument = part.instrument.lower() if part.instrument else ""
    role = part.role

    pool_enabled = (
        plan.arrangement and
        plan.arrangement.piano_template_pool is not None and
        instrument in ("piano", "harp") and
        role in ("accompaniment", "inner_voice")
    )

    if pool_enabled:
        current_mode = context.current_mode
        template_pool = plan.arrangement.piano_template_pool
        mode_templates = getattr(template_pool, current_mode, None)

        if mode_templates:
            variation_window = 4
            if hasattr(plan.arrangement, 'variation_window'):
                variation_window = plan.arrangement.variation_window

            variation_strength = plan.arrangement.variation_strength if plan.arrangement else 0.8
            window_idx = measure_idx // variation_window if measure_idx is not None else 0
            window_key = (part.id, current_mode, window_idx)
            cache = template_window_cache if template_window_cache is not None else {}

            if window_key in cache:
                chosen_name = cache[window_key]
            else:
                if len(mode_templates) > 1:
                    if random.random() < variation_strength:
                        chosen_name = random.choice(mode_templates)
                    else:
                        prev_window_key = (part.id, current_mode, window_idx - 1)
                        if prev_window_key in cache:
                            chosen_name = cache[prev_window_key]
                        else:
                            chosen_name = mode_templates[0]
                else:
                    chosen_name = mode_templates[0]
                cache[window_key] = chosen_name

            report_stats["template_per_part"][part.id] = chosen_name
            if measure_idx is not None:
                report_stats["template_per_measure"][f"{part.id}#m{measure_idx}"] = chosen_name

            template = template_registry.get(chosen_name)
            if template:
                return template

    candidates = template_registry.get_for_instrument_and_role(part.instrument, part.role)
    if candidates:
        for candidate in candidates:
            if "adaptive" in candidate.name:
                return candidate
        return candidates[0]

    return None


def generate_default_accompaniment(
    part: PartSpec,
    context: ArrangementContext,
) -> List[NoteEvent]:
    notes: List[NoteEvent] = []
    channel = part.midi.channel

    if part.role == "bass":
        for measure, chord in context.chord_per_measure.items():
            measure_start = measure * context.measure_len
            duration = context.measure_len
            pitch = chord.root
            while pitch > 55:
                pitch -= 12
            notes.append((measure_start, measure_start + duration, pitch, 60, channel))
    else:
        for measure, chord in context.chord_per_measure.items():
            measure_start = measure * context.measure_len
            duration = context.measure_len
            for pitch in [chord.root, chord.third, chord.fifth]:
                notes.append((measure_start, measure_start + duration, pitch, 55, channel))

    return notes


def generate_part_per_measure(
    part: PartSpec,
    context: ArrangementContext,
    template: BaseTemplate,
    template_params: Dict[str, Any],
    plan: UnifiedPlan,
    template_registry: TemplateRegistry,
    report_stats: Dict,
    template_window_cache: Optional[Dict] = None,
) -> List[NoteEvent]:
    all_notes: List[NoteEvent] = []
    sorted_measures = sorted(context.chord_per_measure.keys())

    for i, measure_idx in enumerate(sorted_measures):
        mode = context.section_modes.get(measure_idx, 'A')
        sub_context = context.model_copy(deep=True)
        chord_info = context.chord_per_measure[measure_idx]
        sub_context.chord_per_measure = {measure_idx: chord_info}
        sub_context.current_mode = mode
        sub_context.prev_chord_root = context.chord_per_measure[sorted_measures[i - 1]].root if i > 0 else None

        measure_template = select_template_for_part(
            part,
            sub_context,
            plan,
            template_registry,
            report_stats,
            measure_idx=measure_idx,
            template_window_cache=template_window_cache,
        )
        if measure_template is None:
            continue
        all_notes.extend(measure_template.generate(sub_context, template_params))

    return all_notes


def generate_part_notes(
    part: PartSpec,
    context: ArrangementContext,
    plan: UnifiedPlan,
    template_registry: TemplateRegistry,
    report_stats: Dict,
) -> List[NoteEvent]:
    instrument = part.instrument.lower() if part.instrument else ""
    role = part.role
    pool_enabled = (
        plan.arrangement and
        plan.arrangement.piano_template_pool is not None and
        instrument in ("piano", "harp") and
        role in ("accompaniment", "inner_voice")
    )

    template_window_cache: Dict = {}
    template = None
    if part.template_name:
        report_stats["template_per_part"][part.id] = part.template_name
        template = template_registry.get(part.template_name)
        if template is None:
            logger.warning(
                f"Template '{part.template_name}' not found for part '{part.id}' "
                f"(instrument={part.instrument}, role={part.role}). "
                f"Falling back to auto-selection."
            )
    else:
        if pool_enabled:
            template = select_template_for_part(
                part,
                context,
                plan,
                template_registry,
                report_stats,
                measure_idx=0,
                template_window_cache=template_window_cache,
            )
        else:
            template = select_template_for_part(
                part,
                context,
                plan,
                template_registry,
                report_stats,
                template_window_cache=template_window_cache,
            )

    if template:
        template_params = dict(part.template_params or {})
        template_params.setdefault("style", getattr(context, 'style', 'general'))
        template_params.setdefault("tempo", getattr(context, 'tempo', 120))
        template_params.setdefault("instrument", part.instrument)

        current_mode = context.current_mode
        if "syncopation" not in template_params:
            if current_mode == "B":
                template_params["syncopation"] = 0.3
            elif current_mode == "C":
                template_params["density"] = template_params.get("density", 0.7) * 1.2
            elif current_mode == "D":
                template_params["density"] = template_params.get("density", 0.7) * 1.4

        if pool_enabled and not part.template_name and getattr(template, 'per_measure_select', False):
            template_name = getattr(template, 'name', 'unknown')
            for measure_idx in context.chord_per_measure.keys():
                report_stats["template_per_measure"][f"{part.id}#m{measure_idx}"] = template_name
            return template.generate(context, template_params)
        if pool_enabled and not part.template_name:
            return generate_part_per_measure(
                part,
                context,
                template,
                template_params,
                plan,
                template_registry,
                report_stats,
                template_window_cache=template_window_cache,
            )

        template_name = getattr(template, 'name', 'unknown')
        for measure_idx in context.chord_per_measure.keys():
            report_stats["template_per_measure"][f"{part.id}#m{measure_idx}"] = template_name
        return template.generate(context, template_params)

    logger.warning(
        f"No template found for part '{part.id}' "
        f"(instrument={part.instrument}, role={part.role}). "
        f"Using sparse default accompaniment. This part may sound empty!"
    )
    return generate_default_accompaniment(part, context)

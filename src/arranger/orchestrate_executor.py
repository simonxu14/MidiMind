"""
OrchestrateExecutor - 乐队编曲执行器

负责：
1. 主旋律锁定
2. 模板填充生成伴奏
3. 应用护栏策略
4. Auto-fixer 自动修复
"""

from __future__ import annotations

import copy
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

from .midi_io import MidiReader, MidiWriter, MidiFile, TrackInfo, ParsedNote, MidiAnalyzer
from .plan_schema import (
    UnifiedPlan,
    EnsembleConfig,
    PartSpec,
    Constraints,
    LockMelodyConfig,
    HarmonyContext,
    GuardsConfig,
    ChordInfo,
    ArrangementContext,
    NoteEvent,
)
from .templates import get_registry, BaseTemplate
from .auto_fixer import AutoFixer
from .harmony_analyzer import estimate_section_modes


# ============ 乐器音域表 ============

INSTRUMENT_RANGES = {
    "violin": (55, 96),
    "viola": (48, 81),
    "cello": (36, 72),
    "double_bass": (28, 52),
    "harp": (23, 103),
    "flute": (60, 96),
    "oboe": (58, 89),
    "clarinet": (50, 99),
    "bassoon": (34, 64),
    "horn": (40, 65),
    "french_horn": (40, 65),
    "trumpet": (52, 84),
    "trombone": (40, 72),
    "tuba": (27, 53),
    "piano": (21, 108),
    "timpani": (45, 53),
}


class OrchestrateExecutor:
    """
    乐队编曲执行器

    核心逻辑：
    1. 提取并锁定主旋律
    2. 分析和声上下文
    3. 使用模板生成各声部伴奏
    4. 应用护栏（guards）
    5. Auto-fixer 修复问题
    """

    def __init__(self, plan: UnifiedPlan):
        self.plan = plan
        self.constraints = plan.constraints
        self.ensemble = plan.ensemble
        self.harmony_context = plan.harmony_context or HarmonyContext()
        self.guards = plan.constraints.guards or GuardsConfig()
        self.template_registry = get_registry()
        self.melody_onsets: List[int] = []  # 存储旋律 onset 供 _generate_part 使用

    def execute(
        self,
        input_midi: bytes,
        melody_track_index: int
    ) -> Tuple[List[List[Tuple[str, Dict]]], Dict[str, any]]:
        """
        执行编曲

        Args:
            input_midi: 输入 MIDI 二进制数据
            melody_track_index: 旋律轨索引

        Returns:
            (tracks_data, stats) - 轨道数据和统计信息
        """
        # 1. 解析 MIDI
        midi = MidiReader.read_midi(input_midi)
        tracks = MidiReader.extract_track_messages(midi)

        # 提取 tempo
        analyzer = MidiAnalyzer(midi)
        midi_analysis = analyzer.analyze()
        tempo = midi_analysis.tempo

        # 2. 提取并锁定主旋律
        if melody_track_index >= len(tracks):
            logger.warning(f"melody_track_index {melody_track_index} out of range, using 0. Available tracks: {len(tracks)}")
            melody_track_index = 0
        melody_track = tracks[melody_track_index]
        locked_melody_notes = self._lock_melody(melody_track)

        # 3. 分析和声上下文
        harmony_analysis = self._analyze_harmony(
            tracks,
            melody_track_index,
            self.harmony_context,
            midi.ticks_per_beat
        )

        # 4. 构建 ArrangementContext
        arrangement_context = self._build_arrangement_context(
            midi,
            tracks,
            harmony_analysis,
            tempo,
            melody_track_index,
            midi_analysis.time_signature if hasattr(midi_analysis, 'time_signature') else (4, 4)
        )

        # 存储 melody_onsets 供 _generate_part 使用
        self.melody_onsets = arrangement_context.melody_onsets

        # 5. 生成各声部
        accompaniment_tracks: Dict[str, List[NoteEvent]] = {}  # part.id -> notes
        instrument_list = []

        for part in self.ensemble.parts:
            if part.role == "melody":
                continue

            track_notes = self._generate_part(
                part,
                arrangement_context,
                locked_melody_notes
            )

            # 应用护栏
            track_notes = self._apply_guards(track_notes, part)

            # 应用人性化处理（可选）
            if self.plan.arrangement and self.plan.arrangement.humanize:
                humanize_config = self.plan.arrangement.humanize
                if humanize_config.enabled and part.role != "melody":
                    track_notes = self._apply_humanize(
                        track_notes,
                        part,
                        timing_jitter=humanize_config.timing_jitter_ticks,
                        velocity_jitter=humanize_config.velocity_jitter
                    )

            # 替换 channel 为 Plan 中指定的 channel（模板使用硬编码默认值）
            target_channel = part.midi.channel
            track_notes = [
                (start, end, pitch, velocity, target_channel)
                for start, end, pitch, velocity, _ in track_notes
            ]

            accompaniment_tracks[part.id] = track_notes
            instrument_list.append(part.name)

        # 6. 应用 AutoFixer 修复和声问题
        # 将所有伴奏轨道扁平化后修复，再按 channel 分组

        # 构建 channel -> 音域 的映射
        channel_ranges: Dict[int, Tuple[int, int]] = {}
        for part in self.ensemble.parts:
            if part.role == "melody":
                continue
            instr = part.instrument.lower() if part.instrument else "piano"
            if instr in INSTRUMENT_RANGES:
                channel_ranges[part.midi.channel] = INSTRUMENT_RANGES[instr]
            else:
                # 未知乐器使用钢琴范围
                channel_ranges[part.midi.channel] = INSTRUMENT_RANGES.get("piano", (21, 108))

        all_accompaniment_notes: List[NoteEvent] = []
        for notes in accompaniment_tracks.values():
            all_accompaniment_notes.extend(notes)

        if all_accompaniment_notes:
            fixer = AutoFixer()
            fixed_notes = fixer.fix_all(all_accompaniment_notes, channel_ranges)

            # 按 channel 分组回各声部
            channel_to_notes: Dict[int, List[NoteEvent]] = {}
            for note in fixed_notes:
                channel = note[4]
                if channel not in channel_to_notes:
                    channel_to_notes[channel] = []
                channel_to_notes[channel].append(note)

            # 更新 accompaniment_tracks
            for part in self.ensemble.parts:
                if part.role == "melody":
                    continue
                fixed_for_part = channel_to_notes.get(part.midi.channel, [])
                accompaniment_tracks[part.id] = fixed_for_part

        # 6.5 按小节模式调整力度
        accompaniment_tracks = self._apply_per_measure_mode_adjustments(
            accompaniment_tracks, arrangement_context
        )

        # 6.6 自动添加打击乐
        accompaniment_tracks = self._auto_add_percussion(
            accompaniment_tracks, arrangement_context
        )

        # 7. 构建输出轨道
        output_tracks = []

        # 获取当前模式的 CC 配置
        current_mode = arrangement_context.current_mode
        melody_cc_config = self._get_cc_config_for_mode(current_mode, is_melody=True)
        other_cc_config = self._get_cc_config_for_mode(current_mode, is_melody=False)

        # Conductor track (tempo, time signature)
        # MIDI writer 会自动创建

        # Melody track - 找到 role="melody" 的声部，使用其 program/channel
        melody_part = None
        for part in self.ensemble.parts:
            if part.role == "melody":
                melody_part = part
                break

        melody_program = melody_part.midi.program if melody_part else 0
        melody_channel = melody_part.midi.channel if melody_part else 0

        melody_track_data = MidiWriter.create_track_from_note_events(
            track_name="Melody",  # Use fixed name for melody track
            note_events=locked_melody_notes,
            program=melody_program,
            channel=melody_channel
        )
        # 添加主旋律 CC 消息
        melody_track_data = self._add_cc_messages_to_track(
            melody_track_data, melody_cc_config, melody_channel
        )
        output_tracks.append(melody_track_data)

        # Accompaniment tracks - use part.id for track name (ASCII, no collisions)
        for part in self.ensemble.parts:
            if part.role == "melody":
                continue

            part_track_data = MidiWriter.create_track_from_note_events(
                track_name=part.id,  # Use ID instead of name to avoid ASCII encoding collisions
                note_events=accompaniment_tracks.get(part.id, []),
                program=part.midi.program,
                channel=part.midi.channel
            )
            # 添加伴奏 CC 消息
            part_track_data = self._add_cc_messages_to_track(
                part_track_data, other_cc_config, part.midi.channel
            )
            output_tracks.append(part_track_data)

        # 自动生成的打击乐轨道
        percussion_channel_map = {
            "auto_timpani": (11, 47),  # channel, program
            "auto_triangle": (12, 81),  # channel, program (gunshot/synth)
        }
        for track_id, (channel, program) in percussion_channel_map.items():
            if track_id in accompaniment_tracks:
                perc_track_data = MidiWriter.create_track_from_note_events(
                    track_name=track_id,
                    note_events=accompaniment_tracks[track_id],
                    program=program,
                    channel=channel
                )
                # 添加伴奏 CC 消息（打击乐不用 CC11）
                perc_cc_config = self._get_cc_config_for_mode(current_mode, is_melody=False)
                perc_cc_config.cc11 = None  # 打击乐不用 expression
                perc_track_data = self._add_cc_messages_to_track(
                    perc_track_data, perc_cc_config, channel
                )
                output_tracks.append(perc_track_data)

        # 8. 统计信息
        total_notes = sum(len(t) for t in output_tracks if t)

        stats = {
            "track_count": len(output_tracks),
            "parts_count": len([p for p in self.ensemble.parts if p.role != "melody"]),
            "instrument_list": instrument_list,
            "total_notes": total_notes,
        }

        return output_tracks, stats

    def _lock_melody(self, melody_track: TrackInfo) -> List[NoteEvent]:
        """
        锁定主旋律

        将旋律轨的音符逐事件复制到输出
        """
        locked: List[NoteEvent] = []

        for note in melody_track.notes:
            locked.append((
                note.start_tick,
                note.end_tick,
                note.pitch,
                note.velocity,
                0  # melody 固定在 channel 0
            ))

        return locked

    def _analyze_harmony(
        self,
        tracks: List[TrackInfo],
        melody_track_index: int,
        harmony_ctx: HarmonyContext,
        ticks_per_beat: int = 480
    ) -> Dict[int, ChordInfo]:
        """
        分析和声上下文

        使用 measure_pitchset_triadish 方法
        """
        # 获取分析源轨道（排除旋律轨）
        source_indices = [
            i for i in harmony_ctx.source_track_indices
            if i != melody_track_index
        ]

        if not source_indices:
            # 如果没有指定，使用所有非旋律轨
            source_indices = [
                i for i in range(len(tracks))
                if i != melody_track_index
            ]

        # 合并所有源轨道的音符
        all_notes: List[ParsedNote] = []
        for idx in source_indices:
            if idx < len(tracks):
                all_notes.extend(tracks[idx].notes)

        if not all_notes:
            # 如果没有伴奏轨，返回默认和弦
            return self._default_harmony(tracks[melody_track_index], time_signature_den=harmony_ctx.time_signature_den if hasattr(harmony_ctx, 'time_signature_den') else 4)

        # 按小节分组
        measure_notes: Dict[int, List[ParsedNote]] = {}

        for note in all_notes:
            ts_den = harmony_ctx.time_signature_den if hasattr(harmony_ctx, 'time_signature_den') else 4
            beats_per_measure = ticks_per_beat * ts_den
            measure = note.start_tick // beats_per_measure
            if measure not in measure_notes:
                measure_notes[measure] = []
            measure_notes[measure].append(note)

        # 提取每个小节的和弦
        harmony: Dict[int, ChordInfo] = {}

        for measure, notes in measure_notes.items():
            if not notes:
                continue

            pitches = sorted(set(n.pitch for n in notes))

            if len(pitches) < 3:
                # 音符太少，使用默认
                root = pitches[0] if pitches else 60
                third = root + 4
                fifth = root + 7
            else:
                # 简单和弦分析：取最低音为根音，然后找三音和五音
                root = pitches[0]
                # 找最接近的三音（根音+3或+4）
                third_candidates = [p for p in pitches if 3 <= p - root <= 5]
                third = third_candidates[0] if third_candidates else root + 4
                # 找最接近的五音（根音+6-8）
                fifth_candidates = [p for p in pitches if 6 <= p - root <= 8]
                fifth = fifth_candidates[0] if fifth_candidates else root + 7

            # 判断和弦性质
            third_interval = third - root
            fifth_interval = fifth - root

            # 规范化到 0-11 范围（处理八度移动后的音程）
            third_norm = third_interval % 12
            fifth_norm = fifth_interval % 12

            # 判断和弦性质
            if fifth_norm == 7:
                if third_norm == 4:
                    quality = "major"
                elif third_norm == 3:
                    quality = "minor"
                else:
                    quality = "unknown"
            elif fifth_norm == 6 and third_norm == 3:
                # 减三和弦：根音+小三度+减五度
                quality = "diminished"
            elif fifth_norm == 8 and third_norm == 4:
                # 增三和弦：根音+大三度+增五度
                quality = "augmented"
            else:
                quality = "unknown"

            harmony[measure] = ChordInfo(
                root=root,
                third=third,
                fifth=fifth,
                quality=quality
            )

        return harmony

    def _default_harmony(self, melody_track: TrackInfo, tempo: int = 120, time_signature_den: int = 4) -> Dict[int, ChordInfo]:
        """
        默认和声分析（基于旋律轨）

        从旋律轨提取和弦，检测七音和和弦性质
        """
        if not melody_track.notes:
            return {0: ChordInfo(root=60, third=64, fifth=67, quality="major")}

        ticks_per_beat = 480
        measure_notes: Dict[int, List[ParsedNote]] = {}

        for note in melody_track.notes:
            measure = note.start_tick // (ticks_per_beat * time_signature_den)
            if measure not in measure_notes:
                measure_notes[measure] = []
            measure_notes[measure].append(note)

        harmony: Dict[int, ChordInfo] = {}

        for measure, notes in measure_notes.items():
            pitches = sorted(set(n.pitch for n in notes))

            if len(pitches) < 2:
                root = pitches[0] if pitches else 60
                harmony[measure] = ChordInfo(
                    root=root,
                    third=root + 4,
                    fifth=root + 7,
                    quality="major"
                )
                continue

            # 分析和弦：找根音、三音、五音、七音
            root = pitches[0]

            # 找三音
            third_candidates = [p for p in pitches if 3 <= (p - root) % 12 <= 4]
            third = third_candidates[0] if third_candidates else root + 4

            # 找五音
            fifth_candidates = [p for p in pitches if 6 <= (p - root) % 12 <= 8]
            fifth = fifth_candidates[0] if fifth_candidates else root + 7

            # 找七音
            seventh_candidates = [p for p in pitches if 10 <= (p - root) % 12 <= 12]
            seventh = seventh_candidates[0] if seventh_candidates else None

            # 判断和弦性质
            third_interval = (third - root) % 12
            fifth_interval = (fifth - root) % 12
            quality = "unknown"

            if seventh is not None:
                seventh_interval = (seventh - root) % 12
                if seventh_interval == 11:  # B7 = minor 7th
                    if third_interval == 4:
                        quality = "dominant7"
                    elif third_interval == 3:
                        quality = "minor7"
                elif seventh_interval == 10:  # Bb7 = major 7th
                    if third_interval == 4:
                        quality = "major7"
            else:
                if fifth_interval == 7:
                    if third_interval == 4:
                        quality = "major"
                    elif third_interval == 3:
                        quality = "minor"
                elif fifth_interval == 6 and third_interval == 3:
                    quality = "diminished"
                elif fifth_interval == 8 and third_interval == 4:
                    quality = "augmented"

            harmony[measure] = ChordInfo(
                root=root,
                third=third,
                fifth=fifth,
                seventh=seventh,
                quality=quality
            )

        return harmony

    def _build_register_targets(self) -> Dict[str, str]:
        """
        根据乐团配置构建乐器音区目标

        基于旋律音域和乐器特性确定各声部的目标音区
        """
        if not self.ensemble or not self.ensemble.parts:
            return {}

        register_targets = {}

        # 乐器标准音区分组
        instrument_ranges = {
            'violin': 'high',
            'viola': 'middle',
            'cello': 'low_middle',
            'double_bass': 'low',
            'flute': 'high',
            'oboe': 'high_middle',
            'clarinet': 'high_middle',
            'bassoon': 'low',
            'horn': 'middle',
            'trumpet': 'high',
            'trombone': 'middle_low',
            'tuba': 'low',
            'piano': 'full',
            'timpani': 'low',
        }

        # 根据角色调整音区
        role_adjustments = {
            'melody': 'high',
            'counter_melody': 'high_middle',
            'inner_voice': 'middle',
            'bass': 'low',
            'bass_rhythm': 'low',
            'anchor': 'low',
            'accompaniment': 'middle',
            'sustain_support': 'middle_low',
            'accent': 'high',
            'fanfare': 'high',
            'percussion': 'low',
            'tutti': 'full',
        }

        for part in self.ensemble.parts:
            instrument = part.instrument
            role = part.role

            # 确定基础音区
            base_register = instrument_ranges.get(instrument, 'middle')

            # 根据角色调整
            if role in role_adjustments:
                register_targets[part.id] = role_adjustments[role]
            else:
                register_targets[part.id] = base_register

        return register_targets

    def _build_arrangement_context(
        self,
        midi: MidiFile,
        tracks: List[TrackInfo],
        harmony: Dict[int, ChordInfo],
        tempo: int = 120,
        melody_track_index: Optional[int] = None,
        time_signature: Tuple[int, int] = (4, 4)
    ) -> ArrangementContext:
        """构建编排上下文"""
        # 计算总 tick 数
        total_ticks = 0
        for track in tracks:
            if track.notes:
                track_end = max(n.end_tick for n in track.notes)
                total_ticks = max(total_ticks, track_end)

        # 找到旋律轨道 - 使用传入的 melody_track_index（更可靠）
        melody_notes = []
        if melody_track_index is not None and melody_track_index < len(tracks):
            melody_notes = tracks[melody_track_index].notes
        else:
            # Fallback: 选择音符最多且音域较高的轨道
            best_track = None
            best_score = 0
            for track in tracks:
                if track.notes:
                    # 评分：音符数量 * 平均音高
                    avg_pitch = sum(n.pitch for n in track.notes) / len(track.notes)
                    score = len(track.notes) * avg_pitch
                    if score > best_score:
                        best_score = score
                        best_track = track
            if best_track:
                melody_notes = best_track.notes

        # 提取旋律 onset
        melody_onsets = sorted(set(n.start_tick for n in melody_notes)) if melody_notes else []

        # 旋律音域
        if melody_notes:
            melody_range = (
                min(n.pitch for n in melody_notes),
                max(n.pitch for n in melody_notes)
            )
        else:
            melody_range = (60, 72)

        # 推断音乐风格
        if tempo < 80:
            style = "ballad"
        elif tempo < 110:
            style = "general"
        elif tempo < 140:
            style = "upbeat"
        else:
            style = "dance"

        # 计算上一小节根音（用于声部连接）
        prev_chord_root = None
        sorted_measures = sorted(harmony.keys())
        if len(sorted_measures) > 1:
            prev_chord_root = harmony[sorted_measures[0]].root

        # 构建音区目标
        register_targets = self._build_register_targets()

        # 估计段落模式
        measure_len = int(midi.ticks_per_beat * time_signature[1])
        total_measures = total_ticks // measure_len if total_ticks > 0 else 1

        # 将 melody_notes 转换为 NoteEvent 格式
        melody_note_events: List[NoteEvent] = [
            (n.start_tick, n.end_tick, n.pitch, n.velocity, 0)
            for n in melody_notes
        ]

        section_modes = estimate_section_modes(
            melody_note_events,
            total_measures,
            measure_len,
            section_block=8,
            D_av=85,
            B_nn=80,
            C_ap=72
        )

        # 获取第一小节的模式作为当前模式
        current_mode = section_modes.get(0, "A")

        # 获取当前模式的力度上限
        velocity_caps = self._get_velocity_caps_for_mode(current_mode)

        return ArrangementContext(
            measure_len=measure_len,
            ticks_per_beat=int(midi.ticks_per_beat),
            time_signature_num=time_signature[0],
            time_signature_den=time_signature[1],
            chord_per_measure=harmony,
            section_modes=section_modes,
            current_mode=current_mode,
            melody_onsets=melody_onsets,
            melody_range=melody_range,
            tempo=int(tempo),
            style=style,
            register_targets=register_targets,
            prev_chord_root=prev_chord_root,
            velocity_caps=velocity_caps
        )

    def _select_template_for_part(
        self,
        part: PartSpec,
        context: ArrangementContext
    ):
        """
        根据当前模式选择模板

        使用 PianoTemplatePool 按模式选择模板
        """
        import random

        instrument = part.instrument.lower() if part.instrument else ""
        role = part.role

        # 只有钢琴和角色为 accompaniment/inner_voice 时使用 PianoTemplatePool
        pool_enabled = (
            self.plan.arrangement and
            self.plan.arrangement.piano_template_pool is not None and
            instrument in ("piano", "harp") and
            role in ("accompaniment", "inner_voice")
        )

        if pool_enabled:
            current_mode = context.current_mode
            template_pool = self.plan.arrangement.piano_template_pool
            mode_templates = getattr(template_pool, current_mode, None)

            if mode_templates:
                # 使用 variation_strength 决定是否随机选择
                variation_strength = self.plan.arrangement.variation_strength if self.plan.arrangement else 0.8

                if random.random() < variation_strength and len(mode_templates) > 1:
                    # 随机选择一个模板
                    chosen_name = random.choice(mode_templates)
                else:
                    # 使用第一个模板
                    chosen_name = mode_templates[0]

                template = self.template_registry.get(chosen_name)
                if template:
                    return template

        # Fallback: 使用原有逻辑
        candidates = self.template_registry.get_for_instrument_and_role(
            part.instrument,
            part.role
        )

        if candidates:
            # 优先选择自适应模板
            for c in candidates:
                if "adaptive" in c.name:
                    return c
            # 如果没有自适应模板，选择第一个
            return candidates[0]

        return None

    def _generate_part(
        self,
        part: PartSpec,
        context: ArrangementContext,
        melody_notes: List[NoteEvent]
    ) -> List[NoteEvent]:
        """
        为指定声部生成音符

        使用模板或默认逻辑
        """
        import random

        # 获取模板
        template = None
        if part.template_name:
            template = self.template_registry.get(part.template_name)
            if template is None:
                logger.warning(
                    f"Template '{part.template_name}' not found for part '{part.id}' "
                    f"(instrument={part.instrument}, role={part.role}). "
                    f"Falling back to auto-selection."
                )
        else:
            # 自动选择模板：使用 PianoTemplatePool 按模式选择
            template = self._select_template_for_part(part, context)

        if template:
            # 构建模板参数字典，包含上下文信息
            template_params = dict(part.template_params or {})
            # 传递风格信息给模板
            if "style" not in template_params:
                template_params["style"] = getattr(context, 'style', 'general')
            if "tempo" not in template_params:
                template_params["tempo"] = getattr(context, 'tempo', 120)
            if "instrument" not in template_params:
                template_params["instrument"] = part.instrument

            # 根据模式调整模板参数
            current_mode = context.current_mode
            if "syncopation" not in template_params:
                # B 段增加切分，C/D 段增加密度
                if current_mode == "B":
                    template_params["syncopation"] = 0.3
                elif current_mode == "C":
                    template_params["density"] = template_params.get("density", 0.7) * 1.2
                elif current_mode == "D":
                    template_params["density"] = template_params.get("density", 0.7) * 1.4

            return template.generate(context, template_params)

        # 默认：生成简单的和弦持续音（警告：这会导致稀疏的编曲）
        logger.warning(
            f"No template found for part '{part.id}' "
            f"(instrument={part.instrument}, role={part.role}). "
            f"Using sparse default accompaniment. This part may sound empty!"
        )
        return self._generate_default_accompaniment(part, context)

    def _generate_default_accompaniment(
        self,
        part: PartSpec,
        context: ArrangementContext
    ) -> List[NoteEvent]:
        """
        生成默认伴奏

        对于 bass 角色：根音持续
        对于其他角色：简单的柱式和弦
        """
        notes: List[NoteEvent] = []
        channel = part.midi.channel

        if part.role == "bass":
            # 根音持续
            for measure, chord in context.chord_per_measure.items():
                measure_start = measure * context.measure_len
                duration = context.measure_len

                pitch = chord.root
                # 调整到低音区
                while pitch > 55:
                    pitch -= 12

                notes.append((
                    measure_start,
                    measure_start + duration,
                    pitch,
                    60,
                    channel
                ))

        else:
            # 柱式和弦
            for measure, chord in context.chord_per_measure.items():
                measure_start = measure * context.measure_len
                duration = context.measure_len

                pitches = [chord.root, chord.third, chord.fifth]

                for pitch in pitches:
                    notes.append((
                        measure_start,
                        measure_start + duration,
                        pitch,
                        55,
                        channel
                    ))

        return notes

    def _apply_guards(
        self,
        notes: List[NoteEvent],
        part: PartSpec
    ) -> List[NoteEvent]:
        """
        应用护栏策略

        1. Velocity cap
        2. 旋律 onset 避让
        3. 音域裁剪
        """
        if not notes:
            return notes

        instrument = part.instrument

        # 1. Velocity cap
        velocity_caps = self.guards.velocity_caps or {}
        max_velocity = velocity_caps.get(instrument, velocity_caps.get(part.id, 127))

        # 2. 旋律 onset 避让
        avoid_onsets = self.guards.avoid_melody_onsets
        onset_window = self.guards.onset_window_ticks

        # 获取旋律 onset
        melody_onsets = self._get_melody_onsets()

        # 3. 音域裁剪
        range_min, range_max = INSTRUMENT_RANGES.get(instrument, (21, 108))

        guarded_notes: List[NoteEvent] = []

        for start, end, pitch, velocity, channel in notes:
            # Velocity cap
            velocity = min(velocity, max_velocity)

            # 旋律 onset 避让（减少力度）
            if avoid_onsets:
                for onset in melody_onsets:
                    if abs(start - onset) < onset_window:
                        velocity = int(velocity * 0.5)
                        break

            # 音域裁剪
            if pitch < range_min:
                pitch = range_min
            elif pitch > range_max:
                pitch = range_max

            guarded_notes.append((start, end, pitch, velocity, channel))

        return guarded_notes

    def _get_melody_onsets(self) -> List[int]:
        """获取旋律 onset 列表"""
        return self.melody_onsets

    def _get_melody_track_name(self) -> str:
        """获取旋律轨道名称"""
        return self.constraints.lock_melody_events.target_track_name or "Melody"

    def _get_velocity_caps_for_mode(self, mode: str) -> Dict[str, int]:
        """
        获取指定模式的力度上限

        Args:
            mode: 段落模式 (A/B/C/D)

        Returns:
            力度上限字典 {instrument_id: cap}
        """
        # 从 arrangement 配置获取，默认使用钢琴的力度上限
        default_caps = {
            "pf": 52, "va": 56, "vc": 62, "winds": 58, "hn": 56
        }

        if self.plan.arrangement and self.plan.arrangement.velocity_caps_by_mode:
            caps_by_mode = self.plan.arrangement.velocity_caps_by_mode
            mode_caps = getattr(caps_by_mode, mode, None)
            if mode_caps:
                return mode_caps

        # 默认值按模式调整
        defaults_by_mode = {
            "A": {"pf": 52, "va": 56, "vc": 62, "winds": 58, "hn": 56},
            "B": {"pf": 56, "va": 60, "vc": 66, "winds": 60, "hn": 58},
            "C": {"pf": 58, "va": 62, "vc": 70, "winds": 62, "hn": 60},
            "D": {"pf": 62, "va": 66, "vc": 74, "winds": 64, "hn": 62},
        }
        return defaults_by_mode.get(mode, default_caps)

    def _get_cc_config_for_mode(self, mode: str, is_melody: bool = False) -> 'CCConfig':
        """
        获取指定模式的 CC 配置

        Args:
            mode: 段落模式 (A/B/C/D)
            is_melody: 是否为主旋律轨道

        Returns:
            CCConfig 对象
        """
        from .plan_schema import CCConfig

        if self.plan.arrangement and self.plan.arrangement.cc_by_mode:
            cc_by_mode = self.plan.arrangement.cc_by_mode
            if is_melody:
                return cc_by_mode.melody.get(mode, CCConfig())
            else:
                return cc_by_mode.others.get(mode, CCConfig())

        # 默认配置
        if is_melody:
            defaults = {
                "A": CCConfig(cc7=102, cc11=100, cc91=35, cc93=8),
                "B": CCConfig(cc7=102, cc11=105, cc91=35, cc93=8),
                "C": CCConfig(cc7=102, cc11=108, cc91=35, cc93=8),
                "D": CCConfig(cc7=102, cc11=112, cc91=35, cc93=8),
            }
        else:
            defaults = {
                "A": CCConfig(cc91=25, cc93=6),
                "D": CCConfig(cc91=27, cc93=6),
            }

        return defaults.get(mode, CCConfig())

    def _add_cc_messages_to_track(
        self,
        messages: List[Tuple[str, Dict]],
        cc_config: 'CCConfig',
        channel: int,
        start_tick: int = 0
    ) -> List[Tuple[str, Dict]]:
        """
        向轨道消息列表添加 CC 消息

        Args:
            messages: 现有轨道消息列表
            cc_config: CC 配置
            channel: 通道号
            start_tick: 起始时间

        Returns:
            添加了 CC 消息的轨道消息列表
        """
        if cc_config is None:
            return messages

        # 在 program change 之后、第一个音符之前插入 CC 消息
        result = []
        cc_inserted = False

        for msg in messages:
            if not cc_inserted and msg[0] in ('note_on', 'note_off'):
                # 插入 CC 消息
                current_tick = start_tick
                if msg[0] == 'note_on':
                    current_tick = msg[1].get('time', 0)

                if cc_config.cc7 is not None:
                    result.append(('control_change', {
                        'control': 7, 'value': cc_config.cc7, 'channel': channel, 'time': 0
                    }))
                if cc_config.cc11 is not None:
                    result.append(('control_change', {
                        'control': 11, 'value': cc_config.cc11, 'channel': channel, 'time': 0
                    }))
                if cc_config.cc91 is not None:
                    result.append(('control_change', {
                        'control': 91, 'value': cc_config.cc91, 'channel': channel, 'time': 0
                    }))
                if cc_config.cc93 is not None:
                    result.append(('control_change', {
                        'control': 93, 'value': cc_config.cc93, 'channel': channel, 'time': 0
                    }))
                cc_inserted = True

            result.append(msg)

        return result

    def _apply_humanize(
        self,
        notes: List[NoteEvent],
        part: PartSpec,
        timing_jitter: int = 0,
        velocity_jitter: int = 0
    ) -> List[NoteEvent]:
        """
        应用人性化处理

        注意：主旋律永远不应用 humanize

        Args:
            notes: 音符事件列表
            part: 声部配置
            timing_jitter: timing 随机偏移量（ticks）
            velocity_jitter: 力度随机波动

        Returns:
            处理后的音符列表
        """
        import random

        if part.role == "melody":
            return notes

        if timing_jitter <= 0 and velocity_jitter <= 0:
            return notes

        result = []
        for start, end, pitch, velocity, channel in notes:
            # Timing jitter - 在 start time 上加随机偏移
            if timing_jitter > 0:
                jitter = random.randint(-timing_jitter, timing_jitter)
                start = max(0, start + jitter)

            # Velocity jitter - 力度随机波动
            if velocity_jitter > 0:
                jitter = random.randint(-velocity_jitter, velocity_jitter)
                velocity = max(1, min(127, velocity + jitter))

            result.append((start, end, pitch, velocity, channel))

        return result

    def _auto_add_percussion(
        self,
        accompaniment_tracks: Dict[str, List[NoteEvent]],
        arrangement_context: ArrangementContext
    ) -> Dict[str, List[NoteEvent]]:
        """
        自动添加打击乐

        根据 PercussionPolicy 自动生成 timpani 和 triangle 轨道

        Args:
            accompaniment_tracks: 现有伴奏轨道
            arrangement_context: 编排上下文

        Returns:
            添加了打击乐的伴奏轨道
        """
        if not self.plan.arrangement or not self.plan.arrangement.percussion:
            return accompaniment_tracks

        percussion_policy = self.plan.arrangement.percussion

        # 检查是否已经存在打击乐声部
        existing_percussion = set()
        for part in self.ensemble.parts:
            if part.role in ("percussion", "bass_rhythm", "accent"):
                if part.instrument in ("timpani", "cymbal", "percussion", "drums"):
                    existing_percussion.add(part.instrument)

        # 自动生成 Timpani
        if percussion_policy.timpani_enabled and "timpani" not in existing_percussion:
            timpani_notes = self._generate_timpani_notes(arrangement_context, percussion_policy)
            if timpani_notes:
                accompaniment_tracks["auto_timpani"] = timpani_notes

        # 自动生成 Triangle
        if percussion_policy.triangle_enabled and "triangle" not in existing_percussion:
            triangle_notes = self._generate_triangle_notes(arrangement_context, percussion_policy)
            if triangle_notes:
                accompaniment_tracks["auto_triangle"] = triangle_notes

        return accompaniment_tracks

    def _generate_timpani_notes(
        self,
        context: ArrangementContext,
        policy
    ) -> List[NoteEvent]:
        """
        生成定音鼓音符

        Timpani: phrase_end_beat4, vel=35
        """
        import random

        notes: List[NoteEvent] = []
        channel = 11  # Timpani channel
        ticks_per_beat = context.ticks_per_beat
        measure_len = context.measure_len
        vel_base = policy.timp_vel_base if hasattr(policy, 'timp_vel_base') else 35
        dur = policy.timp_dur_ticks if hasattr(policy, 'timp_dur_ticks') else 240

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            # phrase_end_beat4: 第4拍后半拍
            tick = measure_start + int(3.5 * ticks_per_beat)

            # 力度
            velocity = vel_base + random.randint(-8, 8)
            velocity = max(25, min(50, velocity))

            # 音高用根音但限制在定音鼓范围
            pitch = max(45, min(53, root))
            if pitch > 53:
                pitch = pitch - 12
            if pitch < 45:
                pitch = pitch + 12

            notes.append((tick, tick + dur, pitch, velocity, channel))

        return notes

    def _generate_triangle_notes(
        self,
        context: ArrangementContext,
        policy
    ) -> List[NoteEvent]:
        """
        生成三角铁音符

        Triangle: phrase_start_beat1, vel=25
        """
        import random

        notes: List[NoteEvent] = []
        channel = 12  # Percussion channel
        ticks_per_beat = context.ticks_per_beat
        measure_len = context.measure_len
        vel_base = policy.tri_vel_base if hasattr(policy, 'tri_vel_base') else 25
        dur = policy.tri_dur_ticks if hasattr(policy, 'tri_dur_ticks') else 60

        for measure_idx, chord_info in context.chord_per_measure.items():
            measure_start = measure_idx * measure_len

            # phrase_start_beat1: 第1拍
            tick = measure_start

            # 力度
            velocity = vel_base + random.randint(-5, 5)
            velocity = max(18, min(35, velocity))

            # 三角铁音高
            pitch = 76  # 高音

            notes.append((tick, tick + dur, pitch, velocity, channel))

        return notes

    def _apply_per_measure_mode_adjustments(
        self,
        accompaniment_tracks: Dict[str, List[NoteEvent]],
        arrangement_context: ArrangementContext
    ) -> Dict[str, List[NoteEvent]]:
        """
        按小节模式调整伴奏力度

        根据每小节的模式应用不同的力度上限

        Args:
            accompaniment_tracks: 伴奏轨道
            arrangement_context: 编排上下文

        Returns:
            调整后的伴奏轨道
        """
        section_modes = arrangement_context.section_modes
        measure_len = arrangement_context.measure_len

        # 构建每小节的力度上限
        measure_velocity_caps: Dict[int, Dict[str, int]] = {}
        for measure_idx, mode in section_modes.items():
            measure_velocity_caps[measure_idx] = self._get_velocity_caps_for_mode(mode)

        result: Dict[str, List[NoteEvent]] = {}

        for track_id, notes in accompaniment_tracks.items():
            if not notes:
                result[track_id] = notes
                continue

            # 获取该轨道的乐器标识
            instrument_key = self._get_instrument_key_for_track(track_id)

            adjusted_notes: List[NoteEvent] = []
            for start, end, pitch, velocity, channel in notes:
                # 计算音符所在的小节索引
                measure_idx = start // measure_len

                # 获取该小节的力度上限
                caps = measure_velocity_caps.get(measure_idx, measure_velocity_caps.get(0, {}))

                # 应用力度上限
                cap = caps.get(instrument_key, 127)
                if velocity > cap:
                    velocity = cap

                adjusted_notes.append((start, end, pitch, velocity, channel))

            result[track_id] = adjusted_notes

        return result

    def _get_instrument_key_for_track(self, track_id: str) -> str:
        """
        获取轨道对应的乐器标识键

        用于查找力度上限
        """
        # 尝试从 ensemble parts 匹配
        if self.ensemble and self.ensemble.parts:
            for part in self.ensemble.parts:
                if part.id == track_id:
                    instr = part.instrument.lower() if part.instrument else ""
                    if "piano" in instr or "harp" in instr:
                        return "pf"
                    elif "viola" in instr:
                        return "va"
                    elif "cello" in instr or "violoncello" in instr:
                        return "vc"
                    elif "flute" in instr or "oboe" in instr or "clarinet" in instr:
                        return "winds"
                    elif "horn" in instr or "french_horn" in instr:
                        return "hn"

        # 回退：根据轨道 ID 猜测
        if "piano" in track_id.lower() or "pf" in track_id.lower():
            return "pf"
        elif "viola" in track_id.lower() or "va" in track_id.lower():
            return "va"
        elif "cello" in track_id.lower() or "vc" in track_id.lower():
            return "vc"
        elif "wind" in track_id.lower():
            return "winds"
        elif "horn" in track_id.lower() or "hn" in track_id.lower():
            return "hn"

        return "pf"  # 默认钢琴

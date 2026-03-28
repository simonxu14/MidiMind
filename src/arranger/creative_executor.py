"""
CreativeExecutor - 创意执行器

用于场景4/5/6：
- 稻香→古典时期风格钢琴小提琴重奏（10分钟）
- 欢乐颂→15人乐队（20分钟）
- 风格转变

核心组件：
1. MaterialPool - 素材提取
2. StructurePlanner - 结构规划
3. StyleFramework - 风格框架
4. VariationEngine - 变奏生成
"""

from __future__ import annotations

import random
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from .midi_io import MidiReader, MidiFile, TrackInfo
from .plan_schema import (
    UnifiedPlan,
    StyleSpecification,
    EnsembleConfig,
    ChordInfo,
    ArrangementContext,
    NoteEvent,
)


# ============ 曲式模板 ============

class StructureTemplate(Enum):
    """曲式模板"""
    SONATA_FORM = "sonata_form"      # 呈示部-展开部-再现部
    RONDO = "rondo"                  # A-B-A-C-A
    VARIATION = "variation"           # 主题-变奏1-变奏2...
    ABA_FORM = "aba_form"            # 三段式
    AABB = "aabb"                    # 二段式
    FREE_FORM = "free_form"          # 自由曲式


@dataclass
class Section:
    """曲式段落"""
    name: str
    start_measure: int
    end_measure: int
    function: str  # exposition, development, recapitulation, etc.
    material_ids: List[str]  # 引用的素材ID
    variation_type: Optional[str] = None  # 变奏类型


# ============ 素材池 ============

@dataclass
class MusicalMaterial:
    """音乐素材"""
    id: str
    type: str  # motif, phrase, chord_progression, bass_line, ornamental
    pitch_sequence: List[int]  # MIDI pitch numbers
    rhythm_pattern: List[int]  # duration in ticks
    start_tick: int
    end_tick: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class MaterialPool:
    """
    素材池 - 从原曲提取的素材库
    """

    def __init__(self):
        self.materials: Dict[str, List[MusicalMaterial]] = {
            "motifs": [],
            "phrases": [],
            "chord_progressions": [],
            "bass_lines": [],
            "ornaments": []
        }

    def extract_from_midi(
        self,
        midi_data: bytes,
        plan: UnifiedPlan
    ) -> "MaterialPool":
        """
        从输入MIDI提取素材

        Args:
            midi_data: MIDI二进制数据
            plan: 编曲方案

        Returns:
            包含提取素材的MaterialPool
        """
        midi = MidiReader.read_midi(midi_data)
        tracks = MidiReader.extract_track_messages(midi)

        # 1. 提取核心动机
        self.materials["motifs"] = self._extract_motifs(tracks)

        # 2. 提取和弦进行
        self.materials["chord_progressions"] = self._extract_chord_progressions(tracks)

        # 3. 提取乐句
        self.materials["phrases"] = self._extract_phrases(tracks)

        # 4. 提取低音线
        self.materials["bass_lines"] = self._extract_bass_lines(tracks)

        return self

    def _extract_motifs(self, tracks: List[TrackInfo]) -> List[MusicalMaterial]:
        """提取核心动机"""
        motifs = []

        for track in tracks:
            if not track.notes:
                continue

            # 简化：取每4小节的核心音符作为动机
            ticks_per_measure = 480 * 4  # 假设4/4拍
            notes = track.notes

            current_measure = 0
            while True:
                measure_start = current_measure * ticks_per_measure
                measure_end = (current_measure + 4) * ticks_per_measure

                measure_notes = [
                    n for n in notes
                    if measure_start <= n.start_tick < measure_end
                ]

                if not measure_notes:
                    break

                # 取前几个音符作为动机
                motif_notes = measure_notes[:4]
                if len(motif_notes) >= 2:
                    motif = MusicalMaterial(
                        id=f"motif_{len(motifs)}",
                        type="motif",
                        pitch_sequence=[n.pitch for n in motif_notes],
                        rhythm_pattern=[n.end_tick - n.start_tick for n in motif_notes],
                        start_tick=motif_notes[0].start_tick,
                        end_tick=motif_notes[-1].end_tick
                    )
                    motifs.append(motif)

                current_measure += 4

        return motifs

    def _extract_chord_progressions(self, tracks: List[TrackInfo]) -> List[MusicalMaterial]:
        """提取和弦进行"""
        chords = []

        # 简化：基于所有音符提取和弦
        all_notes = []
        for track in tracks:
            all_notes.extend(track.notes)

        if not all_notes:
            return chords

        ticks_per_measure = 480 * 4
        current_measure = 0

        while True:
            measure_start = current_measure * ticks_per_measure
            measure_end = (current_measure + 1) * ticks_per_measure

            measure_notes = [
                n for n in all_notes
                if measure_start <= n.start_tick < measure_end
            ]

            if not measure_notes:
                break

            # 提取这一小节的和弦音
            pitches = sorted(set(n.pitch for n in measure_notes))

            chord = MusicalMaterial(
                id=f"chord_{len(chords)}",
                type="chord_progression",
                pitch_sequence=pitches[:5],  # 最多5个音
                rhythm_pattern=[ticks_per_measure],
                start_tick=measure_start,
                end_tick=measure_end
            )
            chords.append(chord)

            current_measure += 1

        return chords

    def _extract_phrases(self, tracks: List[TrackInfo]) -> List[MusicalMaterial]:
        """提取乐句"""
        phrases = []

        for track in tracks:
            if not track.notes:
                continue

            notes = track.notes
            ticks_per_phrase = 480 * 16  # 假设16小节为一句

            current_start = notes[0].start_tick
            phrase_notes = []

            for note in notes:
                if note.start_tick - current_start < ticks_per_phrase:
                    phrase_notes.append(note)
                else:
                    if phrase_notes:
                        phrase = MusicalMaterial(
                            id=f"phrase_{len(phrases)}",
                            type="phrase",
                            pitch_sequence=[n.pitch for n in phrase_notes],
                            rhythm_pattern=[n.end_tick - n.start_tick for n in phrase_notes],
                            start_tick=phrase_notes[0].start_tick,
                            end_tick=phrase_notes[-1].end_tick
                        )
                        phrases.append(phrase)
                    phrase_notes = [note]
                    current_start = note.start_tick

            # 处理最后一个乐句
            if phrase_notes:
                phrase = MusicalMaterial(
                    id=f"phrase_{len(phrases)}",
                    type="phrase",
                    pitch_sequence=[n.pitch for n in phrase_notes],
                    rhythm_pattern=[n.end_tick - n.start_tick for n in phrase_notes],
                    start_tick=phrase_notes[0].start_tick,
                    end_tick=phrase_notes[-1].end_tick
                )
                phrases.append(phrase)

        return phrases

    def _extract_bass_lines(self, tracks: List[TrackInfo]) -> List[MusicalMaterial]:
        """提取低音线"""
        bass_lines = []

        # 找最低音轨
        lowest_track = None
        min_pitch = 128

        for track in tracks:
            if track.notes:
                track_min = min(n.pitch for n in track.notes)
                if track_min < min_pitch:
                    min_pitch = track_min
                    lowest_track = track

        if not lowest_track:
            return bass_lines

        notes = lowest_track.notes
        ticks_per_measure = 480 * 4

        current_measure = 0
        bass_note = None
        bass_start = 0

        for note in notes:
            measure = note.start_tick // ticks_per_measure

            if bass_note is None:
                bass_note = note.pitch
                bass_start = (measure // 4) * 4 * ticks_per_measure
            elif note.pitch < bass_note:
                bass_note = note.pitch

            # 每小节记录一个低音
            if measure != current_measure:
                if bass_note is not None:
                    bass_line = MusicalMaterial(
                        id=f"bass_{len(bass_lines)}",
                        type="bass_line",
                        pitch_sequence=[bass_note],
                        rhythm_pattern=[ticks_per_measure],
                        start_tick=current_measure * ticks_per_measure,
                        end_tick=(current_measure + 1) * ticks_per_measure
                    )
                    bass_lines.append(bass_line)
                bass_note = note.pitch
                current_measure = measure

        return bass_lines


# ============ 风格框架 ============

class StyleFramework:
    """
    风格框架 - 定义古典时期的音乐风格规范
    """

    CLASSICAL_FEATURES = {
        "early_classical": {
            "chord_progressions": ["I-IV-V-I", "I-V-IV-I", "I-V-I"],
            "voicing": "open",
            "ornaments": ["mordent", "turn"],
            "texture": "homophonic",
            "cadences": ["perfect", "plagal", "half"],
        },
        "high_classical": {
            "chord_progressions": ["I-IV-V-I", "I-VI-IV-V", "I-IV-V7-I", "ii-V-I"],
            "voicing": "close_to_close",
            "ornaments": ["mordent", "turn", "trill", "appoggiatura"],
            "texture": "homophonic_with_light_counterpoint",
            "cadences": ["perfect", "deceptive", "plagal"],
        },
        "late_classical": {
            "chord_progressions": ["I-IV-V-I", "I-VI-IV-V", "ii-V-I", "chromatic"],
            "voicing": "varied",
            "ornaments": ["mordent", "turn", "trill", "appoggiatura", "arpeggio"],
            "texture": "homophonic_to_counterpoint",
            "cadences": ["perfect", "deceptive", "plagal", "half"],
        }
    }

    def __init__(self, style: StyleSpecification):
        self.era = style.era
        self.period = style.period or "high_classical"
        self.key_characteristics = style.key_characteristics or {}
        self.features = self.CLASSICAL_FEATURES.get(
            f"{self.era}_{self.period}",
            self.CLASSICAL_FEATURES["high_classical"]
        )

    def validate_harmony(self, chord_progression: List[str]) -> bool:
        """验证和声进行是否符合风格"""
        allowed = self.features.get("chord_progressions", [])
        for chord in chord_progression:
            if chord not in allowed:
                return False
        return True

    def get_ornaments(self) -> List[str]:
        """获取这个风格的装饰音类型"""
        return self.features.get("ornaments", [])

    def get_voicing_rules(self) -> Dict[str, Any]:
        """获取音区规则"""
        return {
            "voicing": self.features.get("voicing", "close_position"),
        }


# ============ 结构规划器 ============

class StructurePlanner:
    """
    结构规划器 - 决定扩展后的曲式结构
    """

    def __init__(self):
        pass

    def plan_structure(
        self,
        original_duration_minutes: float,
        target_duration_minutes: float,
        material_pool: MaterialPool,
        style: Optional[StyleSpecification] = None
    ) -> List[Section]:
        """
        规划目标曲式结构

        Args:
            original_duration_minutes: 原曲时长（分钟）
            target_duration_minutes: 目标时长（分钟）
            material_pool: 素材池
            style: 目标风格

        Returns:
            段落列表
        """
        # 1. 确定曲式（根据目标时长）
        if target_duration_minutes > 15:
            form = StructureTemplate.SONATA_FORM
        elif target_duration_minutes > 8:
            form = StructureTemplate.VARIATION
        else:
            form = StructureTemplate.RONDO

        # 2. 计算时长比例
        expansion_ratio = target_duration_minutes / original_duration_minutes

        # 3. 生成段落
        sections = self._generate_sections(
            form,
            expansion_ratio,
            material_pool
        )

        return sections

    def _generate_sections(
        self,
        form: StructureTemplate,
        expansion_ratio: float,
        material_pool: MaterialPool
    ) -> List[Section]:
        """根据曲式生成段落"""
        sections = []
        current_measure = 0

        if form == StructureTemplate.SONATA_FORM:
            # 奏鸣曲式
            # 呈示部 25%
            expo_len = max(8, int(16 * expansion_ratio * 0.25))
            sections.append(Section(
                name="exposition",
                start_measure=current_measure,
                end_measure=current_measure + expo_len,
                function="exposition",
                material_ids=["phrase_0", "phrase_1"]
            ))
            current_measure += expo_len

            # 展开部 25%
            dev_len = max(8, int(16 * expansion_ratio * 0.25))
            sections.append(Section(
                name="development",
                start_measure=current_measure,
                end_measure=current_measure + dev_len,
                function="development",
                material_ids=["motif_0", "motif_1"]
            ))
            current_measure += dev_len

            # 再现部 25%
            recap_len = max(8, int(16 * expansion_ratio * 0.25))
            sections.append(Section(
                name="recapitulation",
                start_measure=current_measure,
                end_measure=current_measure + recap_len,
                function="recapitulation",
                material_ids=["phrase_0", "phrase_1"]
            ))
            current_measure += recap_len

            # 尾声 15%
            coda_len = max(4, int(16 * expansion_ratio * 0.15))
            sections.append(Section(
                name="coda",
                start_measure=current_measure,
                end_measure=current_measure + coda_len,
                function="coda",
                material_ids=["phrase_0"]
            ))

        elif form == StructureTemplate.VARIATION:
            # 变奏曲式
            # 主题 20%
            theme_len = max(8, int(16 * expansion_ratio * 0.20))
            sections.append(Section(
                name="theme",
                start_measure=current_measure,
                end_measure=current_measure + theme_len,
                function="theme",
                material_ids=["phrase_0"],
                variation_type="original"
            ))
            current_measure += theme_len

            # 4个变奏
            for i in range(4):
                var_len = max(8, int(16 * expansion_ratio * 0.15))
                sections.append(Section(
                    name=f"variation_{i+1}",
                    start_measure=current_measure,
                    end_measure=current_measure + var_len,
                    function="variation",
                    material_ids=[f"phrase_0"],
                    variation_type=f"variation_{i+1}"
                ))
                current_measure += var_len

            # 尾声
            coda_len = max(4, int(16 * expansion_ratio * 0.20))
            sections.append(Section(
                name="coda",
                start_measure=current_measure,
                end_measure=current_measure + coda_len,
                function="coda",
                material_ids=["phrase_0"]
            ))

        elif form == StructureTemplate.RONDO:
            # 回旋曲式 A-B-A-C-A
            sections.append(Section(
                name="theme_a",
                start_measure=current_measure,
                end_measure=current_measure + 8,
                function="theme",
                material_ids=["phrase_0"]
            ))
            current_measure += 8

            sections.append(Section(
                name="episode_b",
                start_measure=current_measure,
                end_measure=current_measure + 6,
                function="episode",
                material_ids=["phrase_1"]
            ))
            current_measure += 6

            sections.append(Section(
                name="theme_a1",
                start_measure=current_measure,
                end_measure=current_measure + 8,
                function="theme",
                material_ids=["phrase_0"]
            ))
            current_measure += 8

            sections.append(Section(
                name="episode_c",
                start_measure=current_measure,
                end_measure=current_measure + 8,
                function="episode",
                material_ids=["phrase_2"]
            ))
            current_measure += 8

            sections.append(Section(
                name="theme_a2",
                start_measure=current_measure,
                end_measure=current_measure + 12,
                function="theme",
                material_ids=["phrase_0"]
            ))

        else:
            # 自由曲式
            sections.append(Section(
                name="free_form",
                start_measure=0,
                end_measure=int(16 * expansion_ratio),
                function="free",
                material_ids=["phrase_0", "phrase_1"]
            ))

        return sections


# ============ 变奏引擎 ============

class VariationEngine:
    """
    变奏引擎 - 对素材进行古典风格的变奏
    """

    def __init__(self, style_framework: Optional[StyleFramework] = None):
        self.style = style_framework

    def vary_material(
        self,
        material: MusicalMaterial,
        variation_type: str,
        target_range: Tuple[int, int]
    ) -> MusicalMaterial:
        """
        对素材进行变奏

        Args:
            material: 原始素材
            variation_type: 变奏类型
            target_range: 目标音区

        Returns:
            变奏后的素材
        """
        if variation_type == "original":
            return material

        varied = MusicalMaterial(
            id=f"{material.id}_var",
            type=material.type,
            pitch_sequence=list(material.pitch_sequence),
            rhythm_pattern=list(material.rhythm_pattern),
            start_tick=material.start_tick,
            end_tick=material.end_tick,
            metadata=dict(material.metadata)
        )

        if variation_type == "rhythmic":
            varied = self._rhythmic_variation(varied)
        elif variation_type == "melodic":
            varied = self._melodic_variation(varied)
        elif variation_type == "registral":
            varied = self._registral_variation(varied, target_range)
        elif variation_type == "ornamental":
            varied = self._add_ornaments(varied)
        elif variation_type == "augmentation":
            varied = self._augmentation(varied)
        elif variation_type == "diminution":
            varied = self._diminution(varied)

        return varied

    def _rhythmic_variation(self, material: MusicalMaterial) -> MusicalMaterial:
        """节奏变奏"""
        varied = material
        # 简单：将节奏 pattern 翻倍或减半
        if random.random() > 0.5:
            varied.rhythm_pattern = [r * 2 for r in material.rhythm_pattern]
        else:
            varied.rhythm_pattern = [max(60, r // 2) for r in material.rhythm_pattern]
        return varied

    def _melodic_variation(self, material: MusicalMaterial) -> MusicalMaterial:
        """旋律变奏"""
        varied = material
        # 简单：略微改变一些音高
        new_pitches = []
        for pitch in material.pitch_sequence:
            delta = random.choice([-2, -1, 0, 1, 2])
            new_pitches.append(max(21, min(108, pitch + delta)))
        varied.pitch_sequence = new_pitches
        return varied

    def _registral_variation(
        self,
        material: MusicalMaterial,
        target_range: Tuple[int, int]
    ) -> MusicalMaterial:
        """音区变奏"""
        varied = material
        # 移动到目标音区
        current_range = (min(material.pitch_sequence), max(material.pitch_sequence))
        current_mid = (current_range[0] + current_range[1]) // 2
        target_mid = (target_range[0] + target_range[1]) // 2

        delta = target_mid - current_mid
        varied.pitch_sequence = [
            max(target_range[0], min(target_range[1], p + delta))
            for p in material.pitch_sequence
        ]
        return varied

    def _add_ornaments(self, material: MusicalMaterial) -> MusicalMaterial:
        """添加装饰音"""
        varied = material
        ornaments = self.style.get_ornaments() if self.style else ["mordent"]

        # 在每个音后添加装饰音
        new_pitches = []
        new_rhythms = []

        for i, (pitch, rhythm) in enumerate(zip(material.pitch_sequence, material.rhythm_pattern)):
            new_pitches.append(pitch)
            new_rhythms.append(rhythm)

            if random.random() < 0.3:  # 30%概率添加装饰
                ornament = random.choice(ornaments)
                if ornament == "mordent":
                    # 回音
                    new_pitches.extend([pitch + 1, pitch])
                    new_rhythms.extend([rhythm // 3, rhythm // 3])
                elif ornament == "turn":
                    # 环绕音
                    new_pitches.extend([pitch + 2, pitch, pitch - 2, pitch])
                    new_rhythms.extend([rhythm // 4] * 4)

        varied.pitch_sequence = new_pitches
        varied.rhythm_pattern = new_rhythms
        return varied

    def _augmentation(self, material: MusicalMaterial) -> MusicalMaterial:
        """扩大（节奏扩大一倍）"""
        varied = material
        varied.rhythm_pattern = [r * 2 for r in material.rhythm_pattern]
        return varied

    def _diminution(self, material: MusicalMaterial) -> MusicalMaterial:
        """缩小（节奏缩小一半）"""
        varied = material
        varied.rhythm_pattern = [max(30, r // 2) for r in material.rhythm_pattern]
        return varied


# ============ CreativeExecutor ============

class CreativeExecutor:
    """
    创意执行器

    用于场景4/5/6：
    - 稻香→古典时期风格钢琴小提琴重奏（10分钟）
    - 欢乐颂→15人乐队（20分钟）
    - 风格转变
    """

    def __init__(self, plan: UnifiedPlan):
        self.plan = plan
        self.material_pool: Optional[MaterialPool] = None
        self.style_framework: Optional[StyleFramework] = None
        self.structure_planner = StructurePlanner()
        self.variation_engine: Optional[VariationEngine] = None

    def execute(
        self,
        input_midi: bytes
    ) -> Tuple[List[List[Tuple[str, Dict]]], Dict[str, Any]]:
        """
        执行创意编曲

        Args:
            input_midi: 输入MIDI二进制数据

        Returns:
            (output_tracks, stats)
        """
        # 1. 提取素材
        self.material_pool = MaterialPool()
        self.material_pool.extract_from_midi(input_midi, self.plan)

        # 2. 初始化风格框架
        if self.plan.style:
            self.style_framework = StyleFramework(self.plan.style)
            self.variation_engine = VariationEngine(self.style_framework)

        # 3. 规划结构
        original_duration = self._estimate_duration(input_midi)
        target_duration = self.plan.transform.target_duration_minutes or original_duration

        sections = self.structure_planner.plan_structure(
            original_duration_minutes=original_duration,
            target_duration_minutes=target_duration,
            material_pool=self.material_pool,
            style=self.plan.style
        )

        # 4. 生成输出轨道
        output_tracks = self._generate_output_tracks(sections)

        # 5. 统计信息
        stats = {
            "sections": [s.name for s in sections],
            "material_count": {
                k: len(v) for k, v in self.material_pool.materials.items()
            },
            "estimated_duration_minutes": target_duration,
        }

        return output_tracks, stats

    def _estimate_duration(self, midi_data: bytes) -> float:
        """估算MIDI时长（分钟）"""
        midi = MidiReader.read_midi(midi_data)

        # 找到最后一个音符的tick
        max_tick = 0
        for track in midi.tracks:
            for msg in track:
                if hasattr(msg, 'time'):
                    max_tick += msg.time

        # 转换为秒
        if midi.ticks_per_beat > 0:
            # 假设120 BPM
            seconds = max_tick / midi.ticks_per_beat / 2
            return seconds / 60  # 转换为分钟

        return 3.0  # 默认3分钟

    def _generate_output_tracks(
        self,
        sections: List[Section]
    ) -> List[List[Tuple[str, Dict]]]:
        """生成输出轨道"""
        from .midi_io import MidiWriter

        output_tracks: List[List[Tuple[str, Dict]]] = []

        # 获取ensemble配置
        ensemble = self.plan.ensemble
        if not ensemble:
            # 默认钢琴+小提琴
            ensemble = EnsembleConfig(
                name="piano_violin_duo",
                size="small",
                parts=[]
            )

        # 为每个声部生成内容
        for part in ensemble.parts:
            track_data = []
            track_data.append(('track_name', {'name': part.name}))
            track_data.append(('program_change', {
                'program': part.midi.program,
                'channel': part.midi.channel
            }))

            # 为每个section生成音符
            for section in sections:
                section_notes = self._generate_section_notes(section, part)
                track_data.extend(section_notes)

            output_tracks.append(track_data)

        return output_tracks

    def _generate_section_notes(
        self,
        section: Section,
        part
    ) -> List[Tuple[str, Dict]]:
        """为段落生成音符"""
        notes: List[Tuple[str, Dict]] = []

        # 获取段落素材
        materials = []
        for mat_id in section.material_ids:
            for mat_list in self.material_pool.materials.values():
                for mat in mat_list:
                    if mat.id == mat_id:
                        materials.append(mat)
                        break

        if not materials:
            return notes

        # 根据变奏类型生成音符
        ticks_per_measure = 480 * 4
        current_tick = section.start_measure * ticks_per_measure

        for material in materials:
            # 应用变奏
            if section.variation_type and self.variation_engine:
                varied = self.variation_engine.vary_material(
                    material,
                    section.variation_type,
                    target_range=(48, 84)  # 中音区
                )
            else:
                varied = material

            # 添加到轨道
            for pitch, rhythm in zip(varied.pitch_sequence, varied.rhythm_pattern):
                notes.append(('note_on', {
                    'pitch': pitch,
                    'velocity': 80,
                    'channel': part.midi.channel,
                    'time': current_tick
                }))
                current_tick += rhythm
                notes.append(('note_off', {
                    'pitch': pitch,
                    'velocity': 0,
                    'channel': part.midi.channel,
                    'time': 0
                }))

        return notes

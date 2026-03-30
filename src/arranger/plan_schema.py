"""
Plan Schema 定义 - MVP v1.0

支持 transform.type=orchestration 的编曲模式。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Literal, Tuple, List, Dict, Any, Union

from pydantic import BaseModel, Field, ConfigDict


# ============ 顶层结构 ============

class DifficultyConfig(BaseModel):
    """难度配置"""

    target_level: Literal["beginner", "intermediate", "advanced", "expert"] = "intermediate"

    # 简化元素列表（用于 simplify 模式）
    simplify_elements: List[str] = Field(
        default_factory=list,
        description="要简化的元素：octave_jumps, tremolo, dense_arpeggio, rapid_repetitions, extreme_register, pedal_points"
    )

    # 复杂化元素列表（用于 complexify 模式）
    complexify_elements: List[str] = Field(
        default_factory=list,
        description="要复杂化的元素：arpeggios, ornamental_notes,_broken_chords, voice_layers"
    )

    model_config = ConfigDict(extra="forbid")


class UnifiedPlan(BaseModel):
    """
    统一 Plan Schema - MVP 阶段只支持 orchestration 模式
    """
    schema_version: str = "1.0"

    # ============ 变换类型 ============
    transform: TransformSpec

    # ============ 乐队编制（用于 orchestration 场景） ============
    ensemble: Optional[EnsembleConfig] = None

    # ============ 和声上下文（用于 orchestration 场景） ============
    harmony_context: Optional[HarmonyContext] = None

    # ============ 编曲详细配置（参考 AnyGen） ============
    arrangement: Optional[ArrangementConfig] = None

    # ============ 通用约束 ============
    constraints: Constraints

    # ============ 难度配置（用于 simplify/complexify 场景） ============
    difficulty: Optional[DifficultyConfig] = None

    # ============ 输出配置 ============
    outputs: OutputConfig

    model_config = ConfigDict(extra="forbid")


# ============ TransformSpec ============

class TransformSpec(BaseModel):
    """变换规格"""

    type: Literal["orchestration"] = "orchestration"
    # MVP 只支持 orchestration，其他模式（difficulty/style/creative）放二期

    # 目标时长（分钟），null 表示与原曲相同
    target_duration_minutes: Optional[float] = None

    # 是否保持原曲结构
    preserve_structure: bool = True

    # 是否保持原曲顺序
    preserve_order: bool = True

    # 目标风格（用于风格转变，MVP 不支持）
    target_style: Optional[str] = None

    # ============ 快捷预设（可选） ============
    # 用户说"更柔和"时，Planner 可以直接输出 preset
    preset: Optional[str] = Field(
        default=None,
        description="预设选项：chamber_soft（柔和室内乐）、orchestra_bright（明亮交响）、minimal（简约版）"
    )

    model_config = ConfigDict(extra="forbid")


# ============ EnsembleConfig ============

class EnsembleConfig(BaseModel):
    """乐队编制配置"""

    name: str = "standard_chamber"
    size: Literal["small", "medium", "large"] = "small"
    target_size: Optional[int] = None

    parts: List[PartSpec] = Field(default_factory=list)

    # 是否自动配置
    auto_configure: bool = False

    model_config = ConfigDict(extra="forbid")


class PartSpec(BaseModel):
    """声部规格"""

    id: str = Field(description="声部唯一标识")
    name: str = Field(description="声部名称，如 Violin I")
    role: Literal[
        "melody", "inner_voice", "bass", "accompaniment", "percussion",
        "counter_melody", "sustain_support", "fanfare", "tutti",
        "bass_rhythm", "anchor", "accent"
    ] = Field(
        description="声部角色"
    )
    instrument: str = Field(description="乐器名称")
    midi: MidiSpec

    # 模板相关
    template_name: Optional[str] = Field(
        default=None,
        description="使用的模板名称，如为空则自动选择"
    )
    template_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="模板参数字典"
    )

    model_config = ConfigDict(extra="forbid")


class MidiSpec(BaseModel):
    """MIDI 音色配置"""

    channel: int = Field(ge=0, le=15)
    program: int = Field(ge=0, le=127)
    secondary_channels: Optional[List[int]] = Field(
        default=None,
        description="多音色支持（如打击乐）"
    )

    model_config = ConfigDict(extra="forbid")


# ============ HarmonyContext ============

class HarmonyContext(BaseModel):
    """和声上下文配置"""

    # 用哪些轨道作为和声参考（排除旋律轨）
    source_track_indices: List[int] = Field(
        default_factory=list,
        description="作为和声分析源的轨道索引列表"
    )

    # 和声分析方法
    method: Literal["measure_pitchset_triadish", "chord_recognition", "key_aware"] = "measure_pitchset_triadish"
    """
    方法选项：
    - measure_pitchset_triadish: 按小节抽取 pitchset，提取根音/三音/五音（快速但粗略）
    - chord_recognition: 和弦识别（更精确但更慢，MVP 不支持）
    - key_aware: 基于调性的和声分析（MVP 不支持）
    """

    # 粒度
    granularity: Literal["per_measure", "per_beat", "per_chord"] = "per_measure"
    """
    - per_measure: 每小节一个和弦
    - per_beat: 每拍一个和弦
    - per_chord: 按和弦变化点
    """

    model_config = ConfigDict(extra="forbid")


# ============ LockMelodyConfig ============

class LockMelodyConfig(BaseModel):
    """旋律锁定配置"""

    enabled: bool = True  # MVP 默认启用

    # ============ 源轨道明确引用 ============
    source_track_ref: Optional[str] = Field(
        default=None,
        description="轨道引用：track_index（如 '1'）或 track_name（如 'Piano'）"
    )

    source_track_selection_mode: Literal["auto", "user_select", "fixed"] = "auto"
    """
    模式：
    - auto: 自动选择（基于 analyze 返回的 melody_candidates[0]）
    - user_select: 由用户在 analyze 后确认
    - fixed: 固定轨道，无需确认
    """

    user_confirm_required: bool = Field(
        default=True,
        description="当 auto 模式且置信度不足时，是否回问用户确认"
    )

    # 比较字段
    compare_fields: List[str] = Field(
        default=["abs_time", "type", "pitch", "velocity"],
        description="逐事件比对字段"
    )

    target_track_name: Optional[str] = Field(
        default=None,
        description="输出旋律轨的名称"
    )

    model_config = ConfigDict(extra="forbid")


# ============ Constraints ============

class Constraints(BaseModel):
    """通用约束"""

    lock_melody_events: LockMelodyConfig = Field(default_factory=LockMelodyConfig)
    keep_total_ticks: bool = True
    instrumentation_fixed: bool = False

    # 护栏配置
    guards: Optional[GuardsConfig] = None

    model_config = ConfigDict(extra="forbid")


# ============ GuardsConfig ============

class GuardsConfig(BaseModel):
    """护栏配置 - 控制生成边界"""

    # 力度上限（per instrument id）
    velocity_caps: Dict[str, int] = Field(
        default_factory=dict,
        description="各声部力度上限，如 {'piano': 58, 'viola': 62}"
    )

    # 旋律 onset 避让
    avoid_melody_onsets: bool = Field(
        default=True,
        description="是否在旋律起音附近减少伴奏"
    )

    onset_window_ticks: int = Field(
        default=120,
        description="旋律起音避让窗口（tick）"
    )

    onset_avoidance_action: Union[Literal["scale_velocity", "delay", "drop"], Dict[str, Literal["scale_velocity", "delay", "drop"]]] = Field(
        default="scale_velocity",
        description="避让动作: 单值时全局策略，dict时按声部如 {'piano':'delay','timpani':'drop','triangle':'drop'}"
    )

    # 音区分离
    register_separation: bool = Field(
        default=True,
        description="是否保持伴奏与旋律的音区分离"
    )

    model_config = ConfigDict(extra="forbid")


# ============ OutputConfig ============

class MidiOutputConfig(BaseModel):
    """MIDI 输出配置"""

    enabled: bool = True
    filename: str = "arranged.mid"
    format: Literal["type0", "type1"] = "type1"
    track_grouping: Literal["by_instrument"] = "by_instrument"  # MVP 固定

    model_config = ConfigDict(extra="forbid")


class PdfOutputConfig(BaseModel):
    """PDF 输出配置（MVP 不支持）"""
    enabled: bool = False
    filename: str = "score.pdf"

    model_config = ConfigDict(extra="forbid")


class AudioOutputConfig(BaseModel):
    """音频输出配置（MVP 不支持）"""
    enabled: bool = False
    filename: str = "output.mp3"
    format: str = "mp3"

    model_config = ConfigDict(extra="forbid")


class OutputConfig(BaseModel):
    """输出配置"""

    midi: MidiOutputConfig = Field(default_factory=MidiOutputConfig)
    pdf: Optional[PdfOutputConfig] = None  # MVP 不支持
    audio: Optional[AudioOutputConfig] = None  # MVP 不支持

    model_config = ConfigDict(extra="forbid")


# ============ 辅助类型 ============

class StyleSpecification(BaseModel):
    """风格规范"""

    era: str = Field(description="时代：baroque, classical, romantic, impressionist, modern")
    period: Optional[str] = Field(default=None, description="时期子分类")
    key_characteristics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="调性特征"
    )

    model_config = ConfigDict(extra="forbid")


class ChordInfo(BaseModel):
    """和弦信息"""

    root: int = Field(description="根音 MIDI pitch")
    third: int = Field(description="三音 MIDI pitch")
    fifth: int = Field(description="五音 MIDI pitch")
    seventh: Optional[int] = Field(default=None, description="七音 MIDI pitch（如果有）")
    quality: Literal["major", "minor", "diminished", "augmented", "dominant7", "major7", "minor7", "unknown"] = "unknown"

    # 和弦功能
    chord_function: Optional[str] = Field(default=None, description="和弦功能: I, ii, iii, IV, V, vi, vii°")

    model_config = ConfigDict(extra="forbid")


class ArrangementContext(BaseModel):
    """
    模板编排上下文

    模板生成时会接收这个上下文信息
    """

    # 节拍信息
    measure_len: int = Field(description="一小节的 tick 数")
    ticks_per_beat: int = Field(description="每拍的 tick 数")
    time_signature_num: int = Field(default=4, description="拍号分子")
    time_signature_den: int = Field(default=4, description="拍号分母")

    # 和声上下文（per measure）
    chord_per_measure: Dict[int, ChordInfo] = Field(
        default_factory=dict,
        description="每小节的和弦信息"
    )

    # 段落模式（per measure）
    section_modes: Dict[int, str] = Field(
        default_factory=dict,
        description="每小节的段落模式: A/B/C/D/CODA"
    )

    # 当前段落模式（供模板使用）
    current_mode: str = Field(default="A", description="当前段落模式")

    # 旋律信息
    melody_onsets: List[int] = Field(
        default_factory=list,
        description="旋律音符的开始时间列表"
    )
    melody_notes: List[NoteEvent] = Field(
        default_factory=list,
        description="旋律音符完整事件列表 (start, end, pitch, velocity, channel)"
    )
    melody_range: Tuple[int, int] = Field(
        default=(0, 127),
        description="旋律音域 (min_pitch, max_pitch)"
    )

    # 音乐风格推断
    tempo: int = Field(default=120, description="速度 BPM")
    style: str = Field(default="general", description="音乐风格: ballad, upbeat, dance, classical")

    # 乐器音区目标
    register_targets: Dict[str, str] = Field(
        default_factory=dict,
        description="各乐器的音区目标，如 {'piano': 'middle', 'violin': 'high'}"
    )

    # 上一小节和弦（用于声部连接）
    prev_chord_root: Optional[int] = Field(default=None, description="上一小节根音")

    # 速度配置
    velocity_caps: Dict[str, int] = Field(
        default_factory=dict,
        description="当前模式的力度上限"
    )

    model_config = ConfigDict(extra="forbid")


# ============ NoteEvent 类型 ============

# 统一的 NoteEvent 结构：(start_tick, end_tick, pitch, velocity, channel)
NoteEvent = Tuple[int, int, int, int, int]
"""
NoteEvent 元组格式：
- start_tick: 事件开始时间（绝对 tick）
- end_tick: 事件结束时间（绝对 tick）
- pitch: MIDI pitch number (0-127)
- velocity: 力度值 (0-127)
- channel: MIDI channel (0-15)
"""


# ============ 段落模式系统 (参考 AnyGen) ============

class SectionMode(str):
    """段落模式枚举"""
    A = "A"  # 透明/克制
    B = "B"  # 流动
    C = "C"  # 明亮
    D = "D"  # 高潮
    CODA = "CODA"  # 尾声/空段


class SectionModeThresholds(BaseModel):
    """
    段落模式检测阈值

    根据 8 小节统计的旋律特征判定模式：
    - D (高潮): avg_velocity >= D_av
    - B (流动): note_density > B_nn
    - C (明亮): avg_pitch > C_ap
    - A (透明): 其他情况
    """
    D_av: int = Field(default=85, description="高潮段力度阈值")
    B_nn: int = Field(default=80, description="流动段音符密度阈值")
    C_ap: int = Field(default=72, description="明亮段平均音高阈值")


class VelocityCapsByMode(BaseModel):
    """
    按段落模式的力度上限

    动态调整各声部力度上限，避免盖过主旋律
    """
    A: Dict[str, int] = Field(
        default_factory=lambda: {"pf": 52, "va": 56, "vc": 62, "winds": 58, "hn": 56},
        description="透明段力度上限"
    )
    B: Dict[str, int] = Field(
        default_factory=lambda: {"pf": 56, "va": 60, "vc": 66, "winds": 60, "hn": 58},
        description="流动段力度上限"
    )
    C: Dict[str, int] = Field(
        default_factory=lambda: {"pf": 58, "va": 62, "vc": 70, "winds": 62, "hn": 60},
        description="明亮段力度上限"
    )
    D: Dict[str, int] = Field(
        default_factory=lambda: {"pf": 62, "va": 66, "vc": 74, "winds": 64, "hn": 62},
        description="高潮段力度上限"
    )


class CCConfig(BaseModel):
    """单个声部的 CC 配置"""
    cc7: Optional[int] = Field(default=None, description="Channel Volume")
    cc11: Optional[int] = Field(default=None, description="Expression")
    cc91: Optional[int] = Field(default=None, description="Reverb Send")
    cc93: Optional[int] = Field(default=None, description="Chorus Send")


class CCByMode(BaseModel):
    """
    按段落模式的 CC 配置

    CC11 用于段落动态变化，CC91/CC93 用于空间感
    """
    melody: Dict[str, CCConfig] = Field(
        default_factory=lambda: {
            "A": CCConfig(cc7=102, cc11=100, cc91=35, cc93=8),
            "B": CCConfig(cc7=102, cc11=105, cc91=35, cc93=8),
            "C": CCConfig(cc7=102, cc11=108, cc91=35, cc93=8),
            "D": CCConfig(cc7=102, cc11=112, cc91=35, cc93=8),
        },
        description="主旋律 CC 配置"
    )
    others: Dict[str, CCConfig] = Field(
        default_factory=lambda: {
            "A": CCConfig(cc91=25, cc93=6),
            "D": CCConfig(cc91=27, cc93=6),
        },
        description="伴奏 CC 配置"
    )


class HumanizeConfig(BaseModel):
    """
    人性化处理配置

    注意：主旋律永远不应用 humanize
    """
    enabled: bool = Field(default=False, description="是否启用人性化处理")
    timing_jitter_ticks: int = Field(default=0, description="timing 随机偏移量（ticks）")
    velocity_jitter: int = Field(default=0, description="力度随机波动")
    apply_to: List[str] = Field(
        default_factory=lambda: ["accompaniment"],
        description="应用的声部类型"
    )


class PercussionPolicy(BaseModel):
    """
    打击乐策略

    定音鼓和三角铁的触发规则
    """
    phrase_block_measures: int = Field(default=8, description="乐句块小节数")
    timpani_enabled: bool = Field(default=True, description="是否启用定音鼓")
    timp_vel_base: int = Field(default=35, description="定音鼓基础力度")
    timp_dur_ticks: int = Field(default=240, description="定音鼓持续时间")
    triangle_enabled: bool = Field(default=True, description="是否启用三角铁")
    tri_vel_base: int = Field(default=25, description="三角铁基础力度")
    tri_dur_ticks: int = Field(default=60, description="三角铁持续时间")


class PianoTemplatePool(BaseModel):
    """
    钢琴模板池（按模式）

    第一层：按段落模式选择模板池
    第二层：在池内按 variation_strength 采样
    """
    A: List[str] = Field(
        default_factory=lambda: ["broken_8ths", "sustain_arpeggio_sparse"],
        description="透明段模板"
    )
    B: List[str] = Field(
        default_factory=lambda: ["alberti_8ths", "offbeat_dyads"],
        description="流动段模板"
    )
    C: List[str] = Field(
        default_factory=lambda: ["register_shift", "arpeggio_16ths"],
        description="明亮段模板"
    )
    D: List[str] = Field(
        default_factory=lambda: ["tremolo_like", "octave_support"],
        description="高潮段模板"
    )


class ArrangementConfig(BaseModel):
    """
    编曲详细配置（参考 AnyGen Plan）

    包含模板选择、护栏、混音等完整配置
    """
    # 段落模式检测
    section_mode_thresholds: SectionModeThresholds = Field(
        default_factory=SectionModeThresholds,
        description="段落模式检测阈值"
    )

    # 模板池配置
    piano_template_pool: PianoTemplatePool = Field(
        default_factory=PianoTemplatePool,
        description="钢琴模板池"
    )
    variation_strength: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="模板多样性强度（0-1）"
    )

    # 和声上下文
    triad_pick: Literal["lowest_three", "heuristic"] = Field(
        default="heuristic",
        description="和弦根音选择方法"
    )

    # 护栏
    avoid_melody_onsets: bool = Field(default=True, description="避让旋律起音")
    onset_window_ticks: int = Field(default=120, description="起音避让窗口")
    reduce_ratio: float = Field(default=0.6, description="避让时力度折减比")
    onset_avoidance_action: Union[Literal["scale_velocity", "delay", "drop"], Dict[str, Literal["scale_velocity", "delay", "drop"]]] = Field(
        default="scale_velocity",
        description="避让动作: 单值时全局策略，dict时按声部如 {'piano':'delay','timpani':'drop','triangle':'drop'}"
    )
    register_separation: bool = Field(default=True, description="音区分离")
    min_semitones: int = Field(default=5, description="与旋律最小音程序离")

    # 力度上限
    velocity_caps_by_mode: VelocityCapsByMode = Field(
        default_factory=VelocityCapsByMode,
        description="按模式的力度上限"
    )

    # CC 混音
    cc_by_mode: CCByMode = Field(
        default_factory=CCByMode,
        description="按模式的 CC 配置"
    )

    # 人性化
    humanize: HumanizeConfig = Field(
        default_factory=HumanizeConfig,
        description="人性化处理配置"
    )

    # 打击乐
    percussion: PercussionPolicy = Field(
        default_factory=PercussionPolicy,
        description="打击乐策略"
    )


# ============ API 请求/响应类型 ============

class AnalyzeRequest(BaseModel):
    """MIDI 分析请求"""
    midi_data: bytes = Field(description="MIDI 文件二进制数据")


class AnalyzeResponse(BaseModel):
    """MIDI 分析响应"""

    tracks: List[TrackStats] = Field(description="各轨道统计信息")
    melody_candidates: List[MelodyCandidate] = Field(description="旋律候选列表（按置信度排序）")
    total_ticks: int = Field(description="MIDI 总 tick 数")
    ticks_per_beat: int = Field(description="每拍 tick 数")
    tempo: int = Field(description="速度（BPM）")
    time_signature: str = Field(description="拍号，如 '4/4'")


class TrackStats(BaseModel):
    """轨道统计"""

    index: int
    name: str
    note_on_count: int
    pitch_range: Tuple[int, int]
    max_polyphony: int


class MelodyCandidate(BaseModel):
    """旋律候选"""

    track_index: int
    score: float = Field(ge=0, le=1, description="置信度评分")
    reason: str = Field(description="评分原因")


class ArrangeRequest(BaseModel):
    """编曲请求"""

    midi_data: bytes = Field(description="MIDI 文件二进制数据")
    plan: UnifiedPlan = Field(description="编曲方案")


class ArrangeResponse(BaseModel):
    """编曲响应"""

    output_url: Optional[str] = Field(default=None, description="输出文件 URL（MVP 为本地路径）")
    output_path: Optional[str] = Field(default=None, description="输出文件本地路径")
    checks: Dict[str, CheckResult] = Field(description="各项检查结果")
    stats: ArrangeStats = Field(description="统计信息")


class CheckResult(BaseModel):
    """检查结果"""

    passed: bool
    message: Optional[str] = None


class ArrangeStats(BaseModel):
    """编曲统计"""

    duration_seconds: float
    track_count: int
    parts_count: int = Field(description="声部数量（不含 conductor track）")
    instrument_list: List[str]

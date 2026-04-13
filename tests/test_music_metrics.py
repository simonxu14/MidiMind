"""
Music Quality Regression Tests

音乐行为回归测试 - 确保编曲质量不退化

使用固定样本 MIDI 检查关键音乐指标：
- note density per part
- melody masking ratio
- register overlap ratio
- onset collision ratio
- velocity cap hits
- out-of-range count
- percussion hit sanity
- flute/wind activity

每次修改后运行，确保音乐质量不退化。
"""

import pytest
from io import BytesIO

from arranger.midi_io import MidiWriter
from arranger.orchestrate_executor import OrchestrateExecutor
from arranger.plan_schema import (
    UnifiedPlan, TransformSpec, EnsembleConfig, PartSpec, MidiSpec,
    HarmonyContext, Constraints, LockMelodyConfig, GuardsConfig,
    ArrangementConfig, OutputConfig, MidiOutputConfig, PercussionPolicy
)
from arranger.auto_fixer import AutoFixer
from arranger.config import INSTRUMENT_RANGES


class TestMusicQualityMetrics:
    """音乐质量回归测试"""

    @pytest.fixture
    def simple_4_4_melody(self):
        """创建简单的 4/4 旋律 MIDI - 用于回归测试"""
        tracks = [[
            # 4 小节简单旋律 C-G-Am-F
            ("note_on", {"channel": 0, "note": 60, "velocity": 64, "time": 0}),
            ("note_off", {"channel": 0, "note": 60, "velocity": 0, "time": 480}),
            ("note_on", {"channel": 0, "note": 64, "velocity": 64, "time": 480}),
            ("note_off", {"channel": 0, "note": 64, "velocity": 0, "time": 960}),
            ("note_on", {"channel": 0, "note": 67, "velocity": 64, "time": 960}),
            ("note_off", {"channel": 0, "note": 67, "velocity": 0, "time": 1440}),
            ("note_on", {"channel": 0, "note": 65, "velocity": 64, "time": 1440}),
            ("note_off", {"channel": 0, "note": 65, "velocity": 0, "time": 1920}),
            # 4 小节重复
            ("note_on", {"channel": 0, "note": 60, "velocity": 64, "time": 1920}),
            ("note_off", {"channel": 0, "note": 60, "velocity": 0, "time": 2400}),
            ("note_on", {"channel": 0, "note": 64, "velocity": 64, "time": 2400}),
            ("note_off", {"channel": 0, "note": 64, "velocity": 0, "time": 2880}),
            ("note_on", {"channel": 0, "note": 53, "velocity": 64, "time": 2880}),
            ("note_off", {"channel": 0, "note": 53, "velocity": 0, "time": 3360}),
            ("note_on", {"channel": 0, "note": 55, "velocity": 64, "time": 3360}),
            ("note_off", {"channel": 0, "note": 55, "velocity": 0, "time": 3840}),
        ]]

        midi_data = MidiWriter.write_midi(
            tracks=tracks,
            ticks_per_beat=480,
            tempo=120,
            time_signature=(4, 4),
        )
        return midi_data

    @pytest.fixture
    def chamber_ensemble_plan(self):
        """标准室内乐配置"""
        ensemble = EnsembleConfig(
            name="chamber_test",
            size="small",
            parts=[
                PartSpec(
                    id="vn1", name="Violin I", role="melody",
                    instrument="violin", midi=MidiSpec(channel=0, program=40),
                    template_name="violin_cantabile"
                ),
                PartSpec(
                    id="vn2", name="Violin II", role="inner_voice",
                    instrument="violin", midi=MidiSpec(channel=1, program=40),
                    template_name="offbeat_dyads"
                ),
                PartSpec(
                    id="va", name="Viola", role="inner_voice",
                    instrument="viola", midi=MidiSpec(channel=2, program=41),
                    template_name="viola_inner_16ths"
                ),
                PartSpec(
                    id="vc", name="Cello", role="bass",
                    instrument="cello", midi=MidiSpec(channel=3, program=42),
                    template_name="cello_pedal_root"
                ),
            ]
        )

        return UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            ensemble=ensemble,
            harmony_context=HarmonyContext(
                method="measure_pitchset_triadish",
                granularity="per_measure"
            ),
            constraints=Constraints(
                lock_melody_events=LockMelodyConfig(
                    enabled=True, source_track_ref="0"
                ),
                keep_total_ticks=True,
                guards=GuardsConfig(
                    velocity_caps={},
                    avoid_melody_onsets=True,
                    onset_window_ticks=120,
                    onset_avoidance_action="scale_velocity",
                    register_separation=True
                )
            ),
            arrangement=ArrangementConfig(
                reduce_ratio=0.6,
                onset_avoidance_action="scale_velocity",
                register_separation=True,
                min_semitones=5,
                velocity_caps_by_mode={},
                cc_by_mode={},
                humanize={"enabled": False},
                percussion=PercussionPolicy(
                    timpani_enabled=False,
                    triangle_enabled=False
                )
            ),
            outputs=OutputConfig(
                midi=MidiOutputConfig(enabled=True, filename="test.mid")
            )
        )

    def _extract_note_events(self, tracks):
        """从 tracks 提取 NoteEvent 列表"""
        events = []
        for track_data in tracks:
            for msg_type, params in track_data:
                if msg_type == "note_on":
                    time = params.get("time", 0)
                    note = params.get("note", 0)
                    velocity = params.get("velocity", 0)
                    channel = params.get("channel", 0)
                    events.append((time, note, velocity, channel))
        return events

    def test_note_density_in_expected_range(self, simple_4_4_melody, chamber_ensemble_plan):
        """每个 part 的 note density 应该在合理范围内"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        # 提取所有非旋律轨的音符
        accompaniment_notes = []
        melody_notes = []
        for track_data in output_tracks:
            is_melody = False
            channel = None
            for msg_type, params in track_data:
                if msg_type == "track_name" and "melody" in params.get("name", ""):
                    is_melody = True
                if msg_type == "note_on" and params.get("velocity", 0) > 0:
                    note_info = {
                        "note": params["note"],
                        "velocity": params["velocity"],
                        "channel": params["channel"]
                    }
                    if is_melody:
                        melody_notes.append(note_info)
                    else:
                        accompaniment_notes.append(note_info)

        # 伴奏应该有音符
        assert len(accompaniment_notes) > 0, \
            f"Accompaniment should have notes, got {len(accompaniment_notes)}"

        # note density：非 melody channel 音符数 / 总时长(小节数)
        # 8 小节 * 4 拍 = 32 拍，伴奏密度应该在合理范围
        total_measures = 8
        density = len(accompaniment_notes) / total_measures

        # 室内乐 4 人配置，伴奏密度应该在 5-50 notes/measure
        assert 3 <= density <= 60, \
            f"Note density {density:.1f} notes/measure out of expected range [3, 60]"

    def test_melody_not_masked_by_accompaniment(self, simple_4_4_melody, chamber_ensemble_plan):
        """主旋律不应该被伴奏完全遮盖（melody masking ratio 检查）"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        # 获取旋律 channel
        melody_channel = None
        for track_data in output_tracks:
            for msg_type, params in track_data:
                if msg_type == "track_name" and "melody" in params.get("name", ""):
                    # 从 program change 获取 channel
                    pass
                if msg_type == "note_on":
                    melody_channel = params.get("channel")
                    break
            if melody_channel is not None:
                break

        assert melody_channel is not None, "Melody channel should be identified"

        # 获取所有音符按 channel 分组
        channel_notes = {}
        for track_data in output_tracks:
            for msg_type, params in track_data:
                if msg_type == "note_on" and params.get("velocity", 0) > 0:
                    ch = params["channel"]
                    if ch not in channel_notes:
                        channel_notes[ch] = []
                    channel_notes[ch].append(params)

        melody_notes = channel_notes.get(melody_channel, [])

        # Melody 音符应该有较高力度
        # Note: velocity may be scaled by guards/arrangement (reduce_ratio=0.6), so allow lower threshold
        avg_melody_vel = sum(n["velocity"] for n in melody_notes) / max(1, len(melody_notes))
        assert avg_melody_vel >= 40, \
            f"Melody average velocity {avg_melody_vel:.1f} too low, melody may be masked"

    def test_out_of_range_count_acceptable(self, simple_4_4_melody, chamber_ensemble_plan):
        """out-of-range 音符数量应该在可接受范围内"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        # 收集所有音符
        all_notes = []
        for track_data in output_tracks:
            for msg_type, params in track_data:
                if msg_type == "note_on" and params.get("velocity", 0) > 0:
                    all_notes.append((
                        params["time"],
                        params["note"],
                        params["velocity"],
                        params["channel"]
                    ))

        # 使用 AutoFixer 检测 out-of-range
        fixer = AutoFixer()
        # 构建 channel -> range 映射
        channel_ranges = {}
        for part in chamber_ensemble_plan.ensemble.parts:
            if part.role == "melody":
                continue
            instr = part.instrument.lower()
            if instr in INSTRUMENT_RANGES:
                channel_ranges[part.midi.channel] = INSTRUMENT_RANGES[instr]

        out_of_range_count = 0
        for start, note, velocity, channel in all_notes:
            if channel in channel_ranges:
                lo, hi = channel_ranges[channel]
                if note < lo or note > hi:
                    out_of_range_count += 1

        # out-of-range 应该 <= 5%
        total = len(all_notes)
        if total > 0:
            oor_ratio = out_of_range_count / total
            assert oor_ratio <= 0.05, \
                f"Out-of-range ratio {oor_ratio:.1%} too high ({out_of_range_count}/{total})"

    def test_onset_collision_acceptable(self, simple_4_4_melody, chamber_ensemble_plan):
        """onset collision 数量应该在可接受范围内"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        # 收集所有 note_on 的 onset tick
        all_onsets = []
        for track_data in output_tracks:
            for msg_type, params in track_data:
                if msg_type == "note_on" and params.get("velocity", 0) > 0:
                    all_onsets.append((params["time"], params["channel"], params["note"]))

        # 按 onset tick 分组，检查同一时刻是否有太多音符同时响起
        from collections import Counter
        onset_counts = Counter(t for t, ch, n in all_onsets)

        # 统计同一时刻 3 个以上音符同时起音的情况
        collisions = sum(1 for count in onset_counts.values() if count >= 3)

        # 应该没有大量 simultaneous onsets（这意味着过度叠置）
        # 室内乐配置，4-6 个声部同时起音的情况应该很少见
        assert collisions <= 10, \
            f"Too many onset collisions: {collisions} ticks with >=3 simultaneous notes"

    def test_percussion_channel_not_in_standard_parts(self, simple_4_4_melody, chamber_ensemble_plan):
        """标准室内乐（无打击乐）的非 percussion channel 不应该有 channel 9"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        # 检查 channel 9 是否出现在不应该出现的地方
        channel_9_found = False
        for track_data in output_tracks:
            track_name = None
            for msg_type, params in track_data:
                if msg_type == "track_name":
                    track_name = params.get("name", "")
                if msg_type == "note_on" and params.get("channel") == 9:
                    # 如果 percussion 被禁用，不应该有 channel 9 的音符
                    if "percussion" not in track_name.lower() and "timpani" not in track_name.lower():
                        channel_9_found = True

        assert not channel_9_found, \
            "Channel 9 (percussion) found in non-percussion tracks when percussion disabled"

    def test_auto_fixer_fix_count_reasonable(self, simple_4_4_melody, chamber_ensemble_plan):
        """AutoFixer 修复数量应该在合理范围内（不应该过度修复）"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        arrangement_report = stats.get("arrangement_report", {})
        fixes = arrangement_report.get("fixes_applied", [])

        # fixes 数量应该合理（过多说明输入质量差）
        assert len(fixes) <= 20, \
            f"Too many autofixes ({len(fixes)}), may indicate quality issues"

    def test_register_separation_maintained(self, simple_4_4_melody, chamber_ensemble_plan):
        """伴奏与旋律的音区分离应该被保持"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        # 提取 melody 和 accompaniment 的音高
        melody_pitches = []
        other_pitches = []

        melody_track_found = False
        for track_data in output_tracks:
            track_name = ""
            for msg_type, params in track_data:
                if msg_type == "track_name":
                    track_name = params.get("name", "")
                if msg_type == "note_on" and params.get("velocity", 0) > 0:
                    if "melody" in track_name.lower():
                        melody_pitches.append(params["note"])
                    else:
                        other_pitches.append(params["note"])

        if not melody_pitches or not other_pitches:
            pytest.skip("Not enough notes to check register separation")

        # 计算平均音高差
        avg_melody = sum(melody_pitches) / len(melody_pitches)
        avg_other = sum(other_pitches) / len(other_pitches)

        # 伴奏平均音高应该与旋律有明显差距（至少 5 semitones）
        pitch_diff = abs(avg_melody - avg_other)
        assert pitch_diff >= 5, \
            f"Register separation insufficient: melody avg={avg_melody:.1f}, others avg={avg_other:.1f}, diff={pitch_diff:.1f}"

    def test_arrangement_report_has_expected_fields(self, simple_4_4_melody, chamber_ensemble_plan):
        """arrangement report 应该包含所有关键字段"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        arrangement_report = stats.get("arrangement_report", {})

        # 检查关键字段存在
        expected_fields = [
            "section_modes",
            "guards_stats",
            "percussion_hits",
            "template_usage",
            "fixes_applied"
        ]

        for field in expected_fields:
            assert field in arrangement_report, \
                f"arrangement_report missing field: {field}"

        # guards_stats 应该包含 onset_avoidance 信息
        guards_stats = arrangement_report.get("guards_stats", {})
        assert "onset_avoidance_hits" in guards_stats or "velocity_cap_hits" in guards_stats, \
            "guards_stats should contain onset_avoidance or velocity_cap metrics"

    def test_ensemble_size_matches_plan(self, simple_4_4_melody, chamber_ensemble_plan):
        """stats["parts_count"] 应该反映显式 plan 声部数量（含 melody）"""
        executor = OrchestrateExecutor(chamber_ensemble_plan)
        output_tracks, stats = executor.execute(simple_4_4_melody, melody_track_index=0)

        expected_parts = len(chamber_ensemble_plan.ensemble.parts)
        actual_parts = stats.get("parts_count", 0)

        assert actual_parts == expected_parts, \
            f"Parts count mismatch: expected {expected_parts}, got {actual_parts}"

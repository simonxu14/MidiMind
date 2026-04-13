"""
MIDI 分析模块

负责 MIDI 轨道分析和旋律候选识别。
"""

from __future__ import annotations

from typing import List, Tuple, Optional
import re

from .midi_io import MidiReader, MidiAnalyzer, MidiFile, TrackInfo


# ============ 旋律候选评分器 ============

class MelodyScorer:
    """
    旋律候选评分器

    使用启发式算法评估每个轨道是否是旋律轨
    """

    # 轨道名称关键词
    MELODY_KEYWORDS = [
        'melody', 'lead', 'solo', 'vocal', 'voice',
        'soprano', 'alto', 'tenor', 'bass',
        'violin', 'flute', 'oboe', 'clarinet', 'trumpet', 'horn'
    ]

    NON_MELODY_KEYWORDS = [
        'drum', 'percussion', 'bass', ' accompaniment', 'chord',
        'piano', 'guitar', 'strings', 'woodwind', 'brass'
    ]

    def score_track(self, track: TrackInfo) -> Tuple[float, str]:
        """
        给轨道评分

        Returns:
            (score, reason) - 评分（0-1）和评分原因
        """
        if not track.notes:
            return 0.0, "No notes in track"

        score = 0.0
        reasons = []

        # 1. 音域评分（高音区更可能是旋律）
        pitch_range = track.notes[-1].pitch - track.notes[0].pitch if len(track.notes) > 1 else 0
        pitch_avg = sum(n.pitch for n in track.notes) / len(track.notes)

        if pitch_avg >= 65:  # 高音区（65以上几乎肯定是旋律）
            score += 0.35
            reasons.append("Very high average pitch (melodic range)")
        elif pitch_avg >= 60:  # 中高音区
            score += 0.25
            reasons.append("High average pitch")
        elif pitch_avg >= 55:  # 中音区偏上
            score += 0.15
            reasons.append("Upper mid-range pitch")
        elif pitch_avg >= 48:  # 中音区
            score += 0.05
            reasons.append("Mid-range pitch")

        # 音域宽度评分（需要先计算 max_poly）
        max_poly = self._calc_polyphony(track.notes)

        if pitch_range > 24:  # 超过两个八度
            score += 0.1
            reasons.append("Wide pitch range")
        elif pitch_range < 12 and max_poly <= 2:
            # 窄范围 + 低复调 = 独奏旋律特征
            score += 0.15
            reasons.append("Narrow range suggests solo melody")

        # 2. 复调评分（旋律通常是单声部或低复调）
        if max_poly <= 1:
            score += 0.25
            reasons.append("Monophonic (clear melody)")
        elif max_poly <= 2:
            score += 0.15
            reasons.append("Low polyphony")
        elif max_poly >= 5:
            score -= 0.2
            reasons.append("High polyphony (likely accompaniment)")

        # 3. 轨道名称评分
        name_lower = track.name.lower()
        if any(kw in name_lower for kw in self.MELODY_KEYWORDS):
            score += 0.2
            reasons.append("Track name suggests melody")
        if any(kw in name_lower for kw in self.NON_MELODY_KEYWORDS):
            # 高音域的 piano 可能是主旋律（如简单钢琴曲）
            if 'piano' in name_lower:
                if pitch_avg >= 65 or max_poly <= 2:
                    score += 0.15  # 高音或低复调的钢琴可能是旋律
                elif max_poly <= 4:
                    score += 0.05  # 中等复调也给点分
            else:
                score -= 0.1
                reasons.append("Track name suggests non-melody")

        # 4. 音符数量评分（旋律通常有合理的音符数量）
        note_count = len(track.notes)
        if 20 <= note_count <= 500:
            score += 0.1
            reasons.append("Reasonable note count")
        elif note_count < 10:
            score -= 0.1
            reasons.append("Too few notes")

        # 5. 节奏密度评分（旋律通常有规律的节奏）
        rhythm_score = self._calc_rhythm_regularity(track.notes)
        score += rhythm_score * 0.1
        if rhythm_score > 0.5:
            reasons.append("Regular rhythm pattern")

        # 限制分数在 0-1 之间
        score = max(0.0, min(1.0, score))

        return score, "; ".join(reasons) if reasons else "No clear melody indicators"

    @staticmethod
    def _calc_polyphony(notes: List) -> int:
        """计算最大复调数"""
        if not notes:
            return 0

        events = []
        for note in notes:
            events.append((note.start_tick, 1))
            events.append((note.end_tick, -1))

        events.sort(key=lambda x: (x[0], x[1]))

        max_poly = 0
        current = 0
        for _, delta in events:
            current += delta
            max_poly = max(max_poly, current)

        return max_poly

    @staticmethod
    def _calc_rhythm_regularity(notes: List) -> float:
        """
        计算节奏规律性（0-1）

        简单算法：计算音符间隔的标准差
        """
        if len(notes) < 3:
            return 0.5

        # 获取所有音符的 onset 时间
        onsets = sorted(set(n.start_tick for n in notes))

        # 计算间隔
        intervals = [onsets[i+1] - onsets[i] for i in range(len(onsets) - 1)]

        if not intervals:
            return 0.5

        # 计算标准差
        mean = sum(intervals) / len(intervals)
        variance = sum((i - mean) ** 2 for i in intervals) / len(intervals)
        std_dev = variance ** 0.5

        # 标准差越小，规律性越高
        # 归一化：假设标准差 > mean * 2 就是不规律
        if mean == 0:
            return 0.5
        normalized_std = std_dev / mean
        regularity = max(0.0, 1.0 - normalized_std)

        return regularity


# ============ MIDI 分析 API ============

class MidiAnalysisService:
    """
    MIDI 分析服务

    提供 MIDI 文件的完整分析功能
    """

    def __init__(self):
        self.scorer = MelodyScorer()

    def analyze(self, midi_data: bytes) -> MidiAnalysisResult:
        """
        分析 MIDI 文件

        Args:
            midi_data: MIDI 文件二进制数据

        Returns:
            MidiAnalysisResult - 包含轨道统计和旋律候选
        """
        # 读取 MIDI
        midi = MidiReader.read_midi(midi_data)

        # 提取轨道信息
        tracks = MidiReader.extract_track_messages(midi)

        # 计算统计
        analyzer = MidiAnalyzer(midi)
        analysis = analyzer.analyze()

        note_tracks = [track for track in tracks if track.notes]

        # 评分旋律候选
        melody_candidates = []
        for track in tracks:
            score, reason = self.scorer.score_track(track)
            if score > 0:
                melody_candidates.append(MelodyCandidateResult(
                    track_index=track.index,
                    track_name=track.name,
                    score=score,
                    reason=reason
                ))

        # 如果文件里只有一个真正有音符的轨道，把它视为默认旋律来源，
        # 即使它是钢琴独奏/钢琴谱式的复调轨，也不应继续保持极低置信度。
        if len(note_tracks) == 1:
            only_track = note_tracks[0]
            for candidate in melody_candidates:
                if candidate.track_index == only_track.index:
                    candidate.score = max(candidate.score, 0.35)
                    if "Only note-bearing track in file" not in candidate.reason:
                        candidate.reason = (
                            f"{candidate.reason}; Only note-bearing track in file"
                            if candidate.reason
                            else "Only note-bearing track in file"
                        )
                    break

        # 按分数排序
        melody_candidates.sort(key=lambda x: x.score, reverse=True)

        # 取 top 3
        top_candidates = melody_candidates[:3]

        return MidiAnalysisResult(
            tracks=analysis.tracks,
            melody_candidates=top_candidates,
            total_ticks=analysis.total_ticks,
            ticks_per_beat=analysis.ticks_per_beat,
            tempo=analysis.tempo,
            time_signature=analysis.time_signature
        )


# ============ 结果数据结构 ============

from dataclasses import dataclass


@dataclass
class MelodyCandidateResult:
    """旋律候选结果"""
    track_index: int
    track_name: str
    score: float
    reason: str


@dataclass
class MidiAnalysisResult:
    """MIDI 分析结果"""
    tracks: List[TrackInfo]
    melody_candidates: List[MelodyCandidateResult]
    total_ticks: int
    ticks_per_beat: int
    tempo: int
    time_signature: Tuple[int, int]


# ============ 便捷函数 ============

def analyze_midi(midi_data: bytes) -> MidiAnalysisResult:
    """
    便捷函数：分析 MIDI 文件

    Args:
        midi_data: MIDI 文件二进制数据

    Returns:
        MidiAnalysisResult
    """
    service = MidiAnalysisService()
    return service.analyze(midi_data)

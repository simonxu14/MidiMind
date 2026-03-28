"""
MIDI IO 模块

负责 MIDI 文件的读写、abs/delta 转换、note 配对、meta 信息提取。
"""

from __future__ import annotations

import io
from typing import List, Tuple, Dict, Optional, Any
from dataclasses import dataclass

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from .plan_schema import NoteEvent


# ============ 数据结构 ============

@dataclass
class ParsedNote:
    """解析后的音符"""
    start_tick: int
    end_tick: int
    pitch: int
    velocity: int
    channel: int


@dataclass
class TrackInfo:
    """轨道信息"""
    index: int
    name: str
    notes: List[ParsedNote]
    messages: List[Any]  # 原始消息列表


@dataclass
class MidiAnalysis:
    """MIDI 分析结果"""
    tracks: List[TrackInfo]
    total_ticks: int
    ticks_per_beat: int
    tempo: int
    time_signature: Tuple[int, int]  # (numerator, denominator)
    track_stats: List[TrackStats]


@dataclass
class TrackStats:
    """轨道统计"""
    index: int
    name: str
    note_on_count: int
    pitch_min: int
    pitch_max: int
    max_polyphony: int


# ============ MIDI 读取与解析 ============

class MidiReader:
    """MIDI 读取器"""

    @staticmethod
    def read_midi(data: bytes) -> MidiFile:
        """从二进制数据读取 MIDI"""
        return MidiFile(file=io.BytesIO(data))

    @staticmethod
    def read_midi_file(path: str) -> MidiFile:
        """从文件路径读取 MIDI"""
        return MidiFile(path)

    @staticmethod
    def extract_track_messages(midi: MidiFile) -> List[TrackInfo]:
        """提取每个轨道的消息"""
        tracks = []

        for idx, track in enumerate(midi.tracks):
            # 提取轨道名称
            name = MidiReader._get_track_name(track)

            # 转换为绝对时间
            abs_track = MidiReader.to_abs_time(track)

            # 过滤出 note_on/off 消息用于配对
            note_track = [msg for msg in abs_track if hasattr(msg, 'type') and msg.type in ('note_on', 'note_off')]

            # 配对 note_on/note_off
            notes = MidiReader.pair_notes(note_track)

            tracks.append(TrackInfo(
                index=idx,
                name=name,
                notes=notes,
                messages=abs_track
            ))

        return tracks

    @staticmethod
    def _get_track_name(track: MidiTrack) -> str:
        """获取轨道名称"""
        for msg in track:
            if msg.type == 'track_name':
                return msg.name
            if hasattr(msg, 'text'):
                # 某些 MIDI 使用 text 消息
                pass
        return f"Track {track.index}" if hasattr(track, 'index') else "Unknown"

    @staticmethod
    def to_abs_time(track: MidiTrack) -> List[Message]:
        """将 track 消息转换为绝对时间"""
        abs_track = []
        current_time = 0

        for msg in track:
            current_time += msg.time
            # MetaMessages (like set_tempo) can't be converted to Message
            # Skip them - we only need note_on/off for note extraction
            if hasattr(msg, 'is_meta') and msg.is_meta:
                abs_track.append(msg.copy(time=current_time))
                continue
            msg_dict = msg.dict()
            msg_type = msg_dict.pop('type')
            msg_dict.pop('time', None)
            abs_msg = Message(msg_type, time=current_time, **msg_dict)
            abs_track.append(abs_msg)

        return abs_track

    @staticmethod
    def to_delta_time(track: List[Message]) -> List[Message]:
        """将绝对时间消息转换为 delta 时间"""
        if not track:
            return []

        delta_track = []
        prev_time = 0

        for msg in track:
            delta_time = msg.time - prev_time
            msg_dict = msg.dict()
            msg_type = msg_dict.pop('type')
            msg_dict.pop('time', None)
            delta_msg = Message(msg_type, time=delta_time, **msg_dict)
            delta_track.append(delta_msg)
            prev_time = msg.time

        return delta_track

    @staticmethod
    def pair_notes(track: List[Message]) -> List[ParsedNote]:
        """
        将 note_on/note_off 配对为音符

        注意：不支持 note_on velocity=0 作为 note_off 的情况
        """
        notes = []
        pending_notes: Dict[Tuple[int, int], ParsedNote] = {}  # (channel, pitch) -> note

        for msg in track:
            if msg.type == 'note_on' and msg.velocity > 0:
                # note_on 开始一个音符
                note = ParsedNote(
                    start_tick=msg.time,
                    end_tick=0,  # 待填充
                    pitch=msg.note,
                    velocity=msg.velocity,
                    channel=msg.channel
                )
                pending_notes[(msg.channel, msg.note)] = note

            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                # note_off 结束一个音符
                key = (msg.channel, msg.note)
                if key in pending_notes:
                    note = pending_notes.pop(key)
                    note.end_tick = msg.time
                    notes.append(note)

        # 处理未配对的 note_on（没有对应的 note_off）
        for note in pending_notes.values():
            # 使用 track 最后一个消息的时间作为结束时间
            if track:
                note.end_tick = track[-1].time if hasattr(track[-1], 'time') else note.start_tick
            else:
                note.end_tick = note.start_tick + 480  # 默认 1 拍

        return notes


# ============ MIDI 分析 ============

class MidiAnalyzer:
    """MIDI 分析器"""

    def __init__(self, midi: MidiFile):
        self.midi = midi

    def analyze(self) -> MidiAnalysis:
        """完整分析 MIDI"""
        tracks = MidiReader.extract_track_messages(self.midi)
        track_stats = [self._calc_track_stats(t) for t in tracks]

        # 提取 meta 信息
        tempo = self._extract_tempo()
        time_signature = self._extract_time_signature()
        total_ticks = self._calc_total_ticks(tracks)

        return MidiAnalysis(
            tracks=tracks,
            total_ticks=total_ticks,
            ticks_per_beat=self.midi.ticks_per_beat,
            tempo=tempo,
            time_signature=time_signature,
            track_stats=track_stats
        )

    def _calc_track_stats(self, track: TrackInfo) -> TrackStats:
        """计算轨道统计"""
        if not track.notes:
            return TrackStats(
                index=track.index,
                name=track.name,
                note_on_count=0,
                pitch_min=0,
                pitch_max=0,
                max_polyphony=0
            )

        pitches = [n.pitch for n in track.notes]
        polyphony = self._calc_max_polyphony(track.notes)

        return TrackStats(
            index=track.index,
            name=track.name,
            note_on_count=len(track.notes),
            pitch_min=min(pitches),
            pitch_max=max(pitches),
            max_polyphony=polyphony
        )

    @staticmethod
    def _calc_max_polyphony(notes: List[ParsedNote]) -> int:
        """计算最大复调数（同时发声的音符数）"""
        if not notes:
            return 0

        # 事件点：(tick, +1/-1)
        events: List[Tuple[int, int]] = []
        for note in notes:
            events.append((note.start_tick, 1))
            events.append((note.end_tick, -1))

        # 按 tick 排序
        events.sort(key=lambda x: (x[0], x[1]))

        max_poly = 0
        current = 0

        for tick, delta in events:
            current += delta
            max_poly = max(max_poly, current)

        return max_poly

    def _extract_tempo(self) -> int:
        """提取 tempo（默认 120 BPM）"""
        for track in self.midi.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    # mido 返回的是微秒每拍，转换为 BPM
                    return mido.tempo2bpm(msg.tempo)
        return 120  # 默认值

    def _extract_time_signature(self) -> Tuple[int, int]:
        """提取拍号（默认 4/4）"""
        for track in self.midi.tracks:
            for msg in track:
                if msg.type == 'time_signature':
                    return (msg.numerator, msg.denominator)
        return (4, 4)  # 默认值

    @staticmethod
    def _calc_total_ticks(tracks: List[TrackInfo]) -> int:
        """计算总 tick 数（取所有轨道的最大值）"""
        max_ticks = 0
        for track in tracks:
            if track.notes:
                track_end = max(n.end_tick for n in track.notes)
                max_ticks = max(max_ticks, track_end)
        return max_ticks


# ============ MIDI 写入 ============

class MidiWriter:
    """MIDI 写入器"""

    @staticmethod
    def write_midi(
        tracks: List[List[Tuple[str, Any]]],
        ticks_per_beat: int = 480,
        tempo: int = 120,
        time_signature: Tuple[int, int] = (4, 4),
        filename: Optional[str] = None
    ) -> bytes:
        """
        写入 MIDI 文件

        Args:
            tracks: 轨道列表，每条轨道是消息列表
                   消息格式: (message_type, params_dict)
            ticks_per_beat: 每拍 tick 数
            tempo: 速度（BPM）
            time_signature: 拍号
            filename: 输出文件路径（可选）

        Returns:
            MIDI 文件二进制数据
        """
        midi = MidiFile(type=1, ticks_per_beat=ticks_per_beat)

        # 添加 tempo track（conductor track）
        tempo_track = MidiWriter._create_tempo_track(tempo, time_signature)
        midi.tracks.append(tempo_track)

        # 添加数据轨道
        for track_data in tracks:
            track = MidiTrack()

            for msg_type, params in track_data:
                if msg_type == 'note_on':
                    track.append(Message('note_on', **params))
                elif msg_type == 'note_off':
                    track.append(Message('note_off', **params))
                elif msg_type == 'program_change':
                    track.append(Message('program_change', **params))
                elif msg_type == 'control_change':
                    track.append(Message('control_change', **params))
                elif msg_type == 'track_name':
                    name = params.get('name', '')
                    ascii_name = name.encode('ascii', 'replace').decode('ascii')
                    track.append(MetaMessage('track_name', name=ascii_name))

            # 补齐 end_of_track
            track.append(MetaMessage('end_of_track'))

            midi.tracks.append(track)

        # 写出
        if filename:
            midi.save(filename)

        output = io.BytesIO()
        midi.save(file=output)
        return output.getvalue()

    @staticmethod
    def _create_tempo_track(tempo: int, time_signature: Tuple[int, int]) -> MidiTrack:
        """创建 tempo track（conductor track）"""
        track = MidiTrack()

        # tempo
        tempo_microseconds = mido.bpm2tempo(tempo)
        track.append(MetaMessage('set_tempo', tempo=tempo_microseconds))

        # time signature
        track.append(MetaMessage(
            'time_signature',
            numerator=time_signature[0],
            denominator=time_signature[1]
        ))

        # track name
        track.append(MetaMessage('track_name', name='Conductor'))

        # end
        track.append(MetaMessage('end_of_track'))

        return track

    @staticmethod
    def create_track_from_note_events(
        track_name: str,
        note_events: List[NoteEvent],
        program: int = 0,
        channel: int = 0
    ) -> List[Tuple[str, Dict]]:
        """
        从 NoteEvent 列表创建轨道消息

        Args:
            track_name: 轨道名称
            note_events: 音符事件列表
            program: 音色 program 号
            channel: 通道号

        Returns:
            消息列表
        """
        messages: List[Tuple[str, Dict]] = []

        # 轨道名称 - 转换为 ASCII 避免 mido 编码问题
        ascii_name = track_name.encode('ascii', 'replace').decode('ascii')
        messages.append(('track_name', {'name': ascii_name}))

        # Program change
        messages.append(('program_change', {'program': program, 'channel': channel}))

        if not note_events:
            return messages

        # 转换为 delta 时间并排序
        # 首先计算每个音符的 duration
        note_data = []
        for start, end, pitch, velocity, ch in note_events:
            duration = end - start
            note_data.append((start, duration, pitch, velocity, ch))

        # 按 start_tick 排序
        note_data.sort(key=lambda x: x[0])

        # 转换为 delta 消息
        current_tick = 0
        active_notes: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}  # (pitch, channel) -> (start, duration, velocity)

        # 创建事件列表
        events = []  # (tick, type, params)
        for start, duration, pitch, velocity, channel in note_data:
            events.append((start, 'note_on', {'note': pitch, 'velocity': velocity, 'channel': channel}))
            events.append((start + duration, 'note_off', {'note': pitch, 'velocity': 0, 'channel': channel}))

        # 按 tick 排序
        events.sort(key=lambda x: (x[0], x[1] == 'note_off'))  # note_off 在同一 tick 优先处理

        # 转换为 delta 消息
        prev_tick = 0
        for tick, msg_type, params in events:
            delta = int(tick - prev_tick)
            params['time'] = delta
            messages.append((msg_type, params))
            prev_tick = tick

        return messages

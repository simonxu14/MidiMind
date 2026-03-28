"""
Arrangement Tracer - 执行追踪日志

详细记录编曲过程中的所有信息：
- LLM prompts 和 responses
- 中间处理结果
- 模板生成详情
- 轨道分析数据
- 和声分析过程
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
import traceback


@dataclass
class TraceEvent:
    """追踪事件"""
    event_id: str
    stage: str  # "intent_analysis", "harmony_analysis", "template_selection", "generation", etc.
    event_type: str  # "llm_call", "processing", "calculation", "error"
    name: str
    data: Dict[str, Any]
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ArrangementTracer:
    """
    编曲追踪器

    详细记录每个编曲会话的所有处理过程，支持：
    - 层级化的追踪事件
    - LLM 调用记录
    - 中间计算结果
    - 错误追踪
    - 可视化导出
    """

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.events: List[TraceEvent] = []
        self._start_times: Dict[str, float] = {}
        self._current_stage = "init"

    def start_stage(self, stage: str) -> None:
        """开始一个处理阶段"""
        self._current_stage = stage

    def log_llm_call(
        self,
        name: str,
        model: str,
        prompt: str,
        response: Optional[str] = None,
        tokens_used: int = 0,
        duration_ms: int = 0,
        error: Optional[str] = None
    ) -> None:
        """记录 LLM 调用"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage=self._current_stage,
            event_type="llm_call",
            name=name,
            data={
                "model": model,
                "prompt": prompt[:5000] if len(prompt) > 5000 else prompt,  # 截断过长 prompt
                "response": response[:5000] if response and len(response) > 5000 else response,
                "tokens_used": tokens_used,
                "error": error
            },
            duration_ms=duration_ms
        )
        self.events.append(event)

    def log_processing(self, name: str, data: Dict[str, Any]) -> None:
        """记录处理过程"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage=self._current_stage,
            event_type="processing",
            name=name,
            data=data
        )
        self.events.append(event)

    def log_calculation(self, name: str, result: Any, input_params: Optional[Dict] = None) -> None:
        """记录计算结果"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage=self._current_stage,
            event_type="calculation",
            name=name,
            data={
                "input_params": input_params or {},
                "result": self._serialize(result)
            }
        )
        self.events.append(event)

    def log_error(self, name: str, error: Exception) -> None:
        """记录错误"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage=self._current_stage,
            event_type="error",
            name=name,
            data={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "traceback": traceback.format_exc()
            }
        )
        self.events.append(event)

    def log_midi_analysis(self, analysis_result: Dict[str, Any]) -> None:
        """记录 MIDI 分析结果"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage="midi_analysis",
            event_type="processing",
            name="midi_analysis_result",
            data=analysis_result
        )
        self.events.append(event)

    def log_harmony_analysis(self, harmony: Dict[str, Any]) -> None:
        """记录和声分析结果"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage="harmony_analysis",
            event_type="processing",
            name="harmony_per_measure",
            data={
                "measures_count": len(harmony),
                "sample_measures": {k: asdict(v) for k, v in list(harmony.items())[:5]}  # 只记录前5个小节
            }
        )
        self.events.append(event)

    def log_template_selection(self, instrument: str, role: str, template_name: str, params: Dict) -> None:
        """记录模板选择"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage="template_selection",
            event_type="processing",
            name="template_selected",
            data={
                "instrument": instrument,
                "role": role,
                "template_name": template_name,
                "template_params": params
            }
        )
        self.events.append(event)

    def log_note_generation(self, part_id: str, template_name: str, note_count: int, duration_ms: int) -> None:
        """记录音符生成"""
        event = TraceEvent(
            event_id=uuid.uuid4().hex[:12],
            stage="note_generation",
            event_type="processing",
            name="notes_generated",
            data={
                "part_id": part_id,
                "template_name": template_name,
                "note_count": note_count
            },
            duration_ms=duration_ms
        )
        self.events.append(event)

    @contextmanager
    def timer(self, name: str):
        """计时上下文管理器"""
        start = time.time()
        try:
            yield
        finally:
            duration_ms = int((time.time() - start) * 1000)
            event = TraceEvent(
                event_id=uuid.uuid4().hex[:12],
                stage=self._current_stage,
                event_type="timed_operation",
                name=name,
                data={},
                duration_ms=duration_ms
            )
            self.events.append(event)

    def get_summary(self) -> Dict[str, Any]:
        """获取追踪摘要"""
        total_duration = sum(e.duration_ms for e in self.events)

        by_type = {}
        for e in self.events:
            if e.event_type not in by_type:
                by_type[e.event_type] = {"count": 0, "total_duration_ms": 0}
            by_type[e.event_type]["count"] += 1
            by_type[e.event_type]["total_duration_ms"] += e.duration_ms

        by_stage = {}
        for e in self.events:
            if e.stage not in by_stage:
                by_stage[e.stage] = {"count": 0}
            by_stage[e.stage]["count"] += 1

        return {
            "conversation_id": self.conversation_id,
            "total_events": len(self.events),
            "total_duration_ms": total_duration,
            "by_type": by_type,
            "by_stage": by_stage
        }

    def get_llm_calls(self) -> List[TraceEvent]:
        """获取所有 LLM 调用"""
        return [e for e in self.events if e.event_type == "llm_call"]

    def export(self) -> Dict[str, Any]:
        """导出完整追踪数据"""
        return {
            "conversation_id": self.conversation_id,
            "exported_at": datetime.now().isoformat(),
            "summary": self.get_summary(),
            "events": [asdict(e) for e in self.events]
        }

    def save_to_file(self, filepath: Optional[Path] = None) -> Path:
        """保存追踪数据到文件"""
        if filepath is None:
            filepath = Path(f"/tmp/midimind_traces/{self.conversation_id}.json")
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.export(), f, ensure_ascii=False, indent=2)

        return filepath

    @staticmethod
    def _serialize(obj: Any) -> Any:
        """序列化对象用于 JSON 存储"""
        if hasattr(obj, "__dict__"):
            return str(obj)
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)


# 全局 tracer 实例（每个请求会创建新的）
_current_tracer: Optional[ArrangementTracer] = None


def get_tracer(conversation_id: str) -> ArrangementTracer:
    """获取当前 tracer 实例"""
    global _current_tracer
    if _current_tracer is None or _current_tracer.conversation_id != conversation_id:
        _current_tracer = ArrangementTracer(conversation_id)
    return _current_tracer

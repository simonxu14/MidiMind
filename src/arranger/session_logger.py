"""
Session Logger - 会话完整日志记录

为每次编曲会话创建完整的日志记录，包括：
- 会话基本信息
- 用户意图
- MIDI 分析结果
- LLM prompts 和 responses
- Plan JSON（每个版本）
- 执行过程追踪
- 输出结果
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field, asdict

from .storage import atomic_write_json, get_storage_dir


logger = logging.getLogger(__name__)


@dataclass
class SessionLog:
    """会话日志"""
    conversation_id: str
    version_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 基础信息
    user_intent: str = ""
    midi_filename: str = ""
    midi_analysis: Dict[str, Any] = field(default_factory=dict)

    # LLM 信息
    llm_prompt: str = ""
    llm_response: str = ""
    llm_model: str = ""
    llm_tokens_used: int = 0
    llm_duration_ms: int = 0

    # Plan JSON（关键！）
    plan: Dict[str, Any] = field(default_factory=dict)

    # 执行追踪
    trace_events: List[Dict[str, Any]] = field(default_factory=list)

    # 输出信息
    output_filename: str = ""
    output_stats: Dict[str, Any] = field(default_factory=dict)
    output_track_summary: List[Dict[str, Any]] = field(default_factory=list)

    # 状态
    status: str = "generated"  # generated, executing, completed, failed
    error_message: str = ""


class SessionLogger:
    """
    会话日志记录器

    为每次编曲会话创建完整的、结构化的日志文件。
    存储位置：由 MIDIMIND_SESSIONS_DIR 或 ~/.midimind/sessions 控制
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or get_storage_dir(
            "sessions",
            "MIDIMIND_SESSIONS_DIR",
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _get_lock(self, conversation_id: str) -> threading.RLock:
        """Return a stable in-process lock for a conversation session directory."""
        with self._locks_guard:
            return self._locks.setdefault(conversation_id, threading.RLock())

    def _get_session_dir(self, conversation_id: str) -> Path:
        """获取会话目录"""
        session_dir = self.base_dir / conversation_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def create_session_log(
        self,
        conversation_id: str,
        version_id: str,
        user_intent: str = "",
        midi_filename: str = ""
    ) -> SessionLog:
        """创建新的会话日志"""
        log = SessionLog(
            conversation_id=conversation_id,
            version_id=version_id,
            user_intent=user_intent,
            midi_filename=midi_filename
        )
        self.save_session_log(log)
        return log

    def save_session_log(self, log: SessionLog) -> Path:
        """保存会话日志到文件"""
        session_dir = self._get_session_dir(log.conversation_id)
        filepath = session_dir / f"{log.version_id}.json"

        with self._get_lock(log.conversation_id):
            atomic_write_json(filepath, asdict(log))

        return filepath

    def get_session_log(self, conversation_id: str, version_id: str) -> Optional[SessionLog]:
        """获取指定会话日志"""
        filepath = self._get_session_dir(conversation_id) / f"{version_id}.json"
        if not filepath.exists():
            return None

        with self._get_lock(conversation_id):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return SessionLog(**data)

    def get_session_logs(self, conversation_id: str) -> List[SessionLog]:
        """获取会话的所有版本日志"""
        session_dir = self._get_session_dir(conversation_id)
        logs = []

        with self._get_lock(conversation_id):
            for filepath in session_dir.glob("*.json"):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        logs.append(SessionLog(**data))
                except Exception as error:
                    logger.warning(
                        "Failed to read session log %s: %s",
                        filepath,
                        error,
                    )

        return sorted(logs, key=lambda x: x.created_at)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        sessions = []

        for session_dir in self.base_dir.iterdir():
            if session_dir.is_dir():
                conversation_id = session_dir.name
                versions = list(session_dir.glob("*.json"))

                if versions:
                    # 获取最新的版本信息
                    latest = max(versions, key=lambda p: p.stat().st_mtime)
                    try:
                        with self._get_lock(conversation_id):
                            with open(latest, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                sessions.append({
                                    "conversation_id": conversation_id,
                                    "version_id": data.get("version_id", ""),
                                    "created_at": data.get("created_at", ""),
                                    "user_intent": data.get("user_intent", "")[:100],
                                    "status": data.get("status", ""),
                                    "versions_count": len(versions)
                                })
                    except Exception as error:
                        logger.warning(
                            "Failed to summarize session %s: %s",
                            latest,
                            error,
                        )

        return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)

    def update_session_log(self, log: SessionLog) -> Path:
        """更新会话日志"""
        return self.save_session_log(log)

    def add_trace_event(self, conversation_id: str, version_id: str, event: Dict[str, Any]) -> None:
        """添加追踪事件"""
        log = self.get_session_log(conversation_id, version_id)
        if log:
            log.trace_events.append(event)
            self.save_session_log(log)

    def get_session_summary(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """获取会话摘要"""
        logs = self.get_session_logs(conversation_id)
        if not logs:
            return None

        latest_log = logs[-1]
        return {
            "conversation_id": conversation_id,
            "version_count": len(logs),
            "latest_version_id": latest_log.version_id,
            "latest_created_at": latest_log.created_at,
            "user_intent": latest_log.user_intent[:200] if latest_log.user_intent else "",
            "status": latest_log.status,
            "plan_parts_count": len(latest_log.plan.get("ensemble", {}).get("parts", [])) if latest_log.plan else 0
        }


# 全局实例
session_logger = SessionLogger()

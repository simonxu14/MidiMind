"""
Conversation Manager - 多轮对话状态管理

管理编曲会话的完整历史，支持：
- 会话创建、更新、查询
- 完整的消息历史记录
- LLM 思考过程追踪
- 中间处理结果记录
- 用户反馈收集
"""

from __future__ import annotations

import json
import uuid
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    PLANNER = "planner"
    EXECUTOR = "executor"


@dataclass
class Message:
    """消息记录"""
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMThought:
    """LLM 思考过程"""
    stage: str  # e.g., "intent_analysis", "plan_generation", "revision"
    prompt: str
    response: str
    model: str
    tokens_used: int = 0
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None


@dataclass
class ProcessingStep:
    """中间处理步骤"""
    step_name: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ArrangementVersion:
    """编曲版本记录"""
    version_id: str
    plan: Dict[str, Any]
    # 执行结果（新增）
    stats: Optional[Dict[str, Any]] = None  # 执行统计
    validator_result: Optional[Dict[str, Any]] = None  # 验证结果
    arrangement_report: Optional[Dict[str, Any]] = None  # arrangement report
    # 输出信息（新增）
    output_midi_hash: Optional[str] = None  # 输出 MIDI 的 SHA256
    output_file_path: Optional[str] = None  # 输出文件路径
    # 执行元数据（新增）
    commit_id: Optional[str] = None  # 执行的代码 commit
    execution_duration_ms: Optional[int] = None  # 执行耗时
    user_feedback: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "generated"  # generated, reviewed, revised, approved


class ConversationManager:
    """
    会话管理器

    负责：
    - 创建和管理会话
    - 记录完整对话历史
    - 追踪 LLM 思考过程
    - 记录中间处理步骤
    - 存储多个编曲版本
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path("/tmp/midimind_conversations")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 内存中的会话缓存
        self._conversations: Dict[str, Dict[str, Any]] = {}

    def create_conversation(self, user_intent: str, metadata: Optional[Dict] = None) -> str:
        """创建新会话"""
        conversation_id = uuid.uuid4().hex

        conversation = {
            "id": conversation_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "initial_intent": user_intent,
            "current_intent": user_intent,
            "messages": [],
            "llm_thoughts": [],
            "processing_steps": [],
            "arrangement_versions": [],
            "metadata": metadata or {},
            "status": "active"
        }

        self._conversations[conversation_id] = conversation
        self._save_to_disk(conversation_id, conversation)

        return conversation_id

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """添加消息到会话"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )

        conversation["messages"].append(asdict(message))
        conversation["updated_at"] = datetime.now().isoformat()

        self._save_to_disk(conversation_id, conversation)

    def add_llm_thought(self, conversation_id: str, thought: LLMThought) -> None:
        """添加 LLM 思考过程"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation["llm_thoughts"].append(asdict(thought))
        conversation["updated_at"] = datetime.now().isoformat()

        self._save_to_disk(conversation_id, conversation)

    def add_processing_step(self, conversation_id: str, step: ProcessingStep) -> None:
        """添加处理步骤"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation["processing_steps"].append(asdict(step))
        conversation["updated_at"] = datetime.now().isoformat()

        self._save_to_disk(conversation_id, conversation)

    def add_arrangement_version(
        self,
        conversation_id: str,
        plan: Dict[str, Any],
        version_id: Optional[str] = None
    ) -> str:
        """添加编曲版本"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        version_id = version_id or uuid.uuid4().hex[:8]

        version = ArrangementVersion(
            version_id=version_id,
            plan=plan,
            status="generated"
        )

        conversation["arrangement_versions"].append(asdict(version))
        conversation["updated_at"] = datetime.now().isoformat()

        self._save_to_disk(conversation_id, conversation)

        return version_id

    def update_version_feedback(
        self,
        conversation_id: str,
        version_id: str,
        feedback: str
    ) -> None:
        """更新版本反馈"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        for version in conversation["arrangement_versions"]:
            if version["version_id"] == version_id:
                version["user_feedback"] = feedback
                version["status"] = "reviewed"
                break

        conversation["updated_at"] = datetime.now().isoformat()
        self._save_to_disk(conversation_id, conversation)

    def update_version_status(self, conversation_id: str, version_id: str, status: str) -> None:
        """更新版本状态"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        for version in conversation["arrangement_versions"]:
            if version["version_id"] == version_id:
                version["status"] = status
                break

        conversation["updated_at"] = datetime.now().isoformat()
        self._save_to_disk(conversation_id, conversation)

    def update_arrangement_version_result(
        self,
        conversation_id: str,
        version_id: str,
        stats: Optional[Dict[str, Any]] = None,
        validator_result: Optional[Dict[str, Any]] = None,
        arrangement_report: Optional[Dict[str, Any]] = None,
        output_midi_hash: Optional[str] = None,
        output_file_path: Optional[str] = None,
        commit_id: Optional[str] = None,
        execution_duration_ms: Optional[int] = None
    ) -> None:
        """更新编曲版本的执行结果"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        for version in conversation["arrangement_versions"]:
            if version["version_id"] == version_id:
                if stats is not None:
                    version["stats"] = stats
                if validator_result is not None:
                    version["validator_result"] = validator_result
                if arrangement_report is not None:
                    version["arrangement_report"] = arrangement_report
                if output_midi_hash is not None:
                    version["output_midi_hash"] = output_midi_hash
                if output_file_path is not None:
                    version["output_file_path"] = output_file_path
                if commit_id is not None:
                    version["commit_id"] = commit_id
                if execution_duration_ms is not None:
                    version["execution_duration_ms"] = execution_duration_ms
                break

        conversation["updated_at"] = datetime.now().isoformat()
        self._save_to_disk(conversation_id, conversation)

    def update_intent(self, conversation_id: str, new_intent: str) -> None:
        """更新当前意图"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation["current_intent"] = new_intent
        conversation["updated_at"] = datetime.now().isoformat()

        self._save_to_disk(conversation_id, conversation)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        if conversation_id in self._conversations:
            return self._conversations[conversation_id]

        # 从磁盘加载
        file_path = self.storage_dir / f"{conversation_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                conversation = json.load(f)
                self._conversations[conversation_id] = conversation
                return conversation

        return None

    def get_conversation_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取对话历史"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return []
        return conversation.get("messages", [])

    def get_llm_thoughts(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取 LLM 思考过程"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return []
        return conversation.get("llm_thoughts", [])

    def get_processing_steps(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取处理步骤"""
        conversation = get_conversation(conversation_id)
        if not conversation:
            return []
        return conversation.get("processing_steps", [])

    def get_latest_version(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """获取最新编曲版本"""
        conversation = self.get_conversation(conversation_id)
        if not conversation or not conversation.get("arrangement_versions"):
            return None
        return conversation["arrangement_versions"][-1]

    def list_conversations(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        conversations = []
        for file_path in self.storage_dir.glob("*.json"):
            with open(file_path, "r", encoding="utf-8") as f:
                conv = json.load(f)
                conversations.append({
                    "id": conv["id"],
                    "created_at": conv["created_at"],
                    "updated_at": conv["updated_at"],
                    "initial_intent": conv["initial_intent"],
                    "status": conv["status"],
                    "versions_count": len(conv.get("arrangement_versions", []))
                })
        return sorted(conversations, key=lambda x: x["updated_at"], reverse=True)

    def export_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """导出会话完整记录"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        return conversation

    def _save_to_disk(self, conversation_id: str, conversation: Dict[str, Any]) -> None:
        """保存会话到磁盘"""
        file_path = self.storage_dir / f"{conversation_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(conversation, f, ensure_ascii=False, indent=2)


# 全局实例
conversation_manager = ConversationManager()

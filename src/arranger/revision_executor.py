"""
Revision Executor - 基于历史编曲的增量修改执行器

处理用户的修改请求，对现有方案进行增量变更：
1. add: 新增声部
2. remove: 删除声部
3. modify: 修改现有声部的配置
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List

from .plan_schema import (
    UnifiedPlan,
    RevisionIntent,
    RevisionResult,
    EnsembleConfig,
    PartSpec,
    MidiSpec,
)

logger = logging.getLogger(__name__)


class RevisionExecutor:
    """
    Revision 执行器

    对现有编曲方案进行增量修改
    """

    def __init__(self):
        pass

    def _part_payload_by_id(self, plan: UnifiedPlan) -> Dict[str, Dict[str, Any]]:
        """Index parts by id for semantic comparison across revision flows."""
        return {
            part.id: part.model_dump()
            for part in (plan.ensemble.parts if plan.ensemble else [])
        }

    def _build_failure_result(
        self,
        base_plan: UnifiedPlan,
        revision_type: Optional[str],
        message: str,
    ) -> RevisionResult:
        """Return a consistent failed revision result."""
        return RevisionResult(
            success=False,
            message=message,
            revised_plan=base_plan,
            revision_type=revision_type,
            modified_parts=[],
        )

    def _validate_add_result(
        self,
        base_plan: UnifiedPlan,
        modified_plan: UnifiedPlan,
    ) -> tuple[bool, str, List[str]]:
        """Ensure add revisions only append new parts and leave existing parts untouched."""
        base_parts = self._part_payload_by_id(base_plan)
        modified_parts = self._part_payload_by_id(modified_plan)

        missing_ids = [part_id for part_id in base_parts if part_id not in modified_parts]
        if missing_ids:
            return False, f"新增声部结果缺少原有声部: {', '.join(missing_ids)}", []

        changed_existing = [
            part_id
            for part_id, payload in base_parts.items()
            if modified_parts[part_id] != payload
        ]
        if changed_existing:
            return False, f"新增声部不应修改已有声部: {', '.join(changed_existing)}", []

        added_ids = [part_id for part_id in modified_parts if part_id not in base_parts]
        if not added_ids:
            return False, "新增声部结果没有实际新增任何声部", []

        return True, "", added_ids

    def _validate_modify_result(
        self,
        base_plan: UnifiedPlan,
        modified_plan: UnifiedPlan,
        target_part_id: str,
    ) -> tuple[bool, str]:
        """Ensure modify revisions only touch the target part and preserve the part set."""
        base_parts = self._part_payload_by_id(base_plan)
        modified_parts = self._part_payload_by_id(modified_plan)

        if set(base_parts) != set(modified_parts):
            return False, "修改声部不应新增或删除其他声部"

        if target_part_id not in modified_parts:
            return False, f"修改结果中缺少目标声部: {target_part_id}"

        changed_part_ids = [
            part_id
            for part_id in base_parts
            if base_parts[part_id] != modified_parts[part_id]
        ]

        if not changed_part_ids:
            return False, "修改声部结果没有产生任何变化"

        if changed_part_ids != [target_part_id]:
            return False, f"修改声部只应影响目标声部，实际变更: {', '.join(changed_part_ids)}"

        return True, ""

    def apply_revision(
        self,
        base_plan: UnifiedPlan,
        revision_intent: RevisionIntent,
        user_instruction: str,
        llm_planner=None,
        analyze_result=None
    ) -> RevisionResult:
        """
        对 base_plan 应用 revision 修改，返回新 plan

        Args:
            base_plan: 基础编曲方案
            revision_intent: 修改意图
            user_instruction: 用户的原始指令
            llm_planner: 可选的 LLM Planner，用于生成新声部
            analyze_result: 可选的 MIDI 分析结果

        Returns:
            RevisionResult：包含修改后的新方案
        """
        if not revision_intent.is_revision:
            # 全新创作，返回原 plan（调用方会重新生成）
            return RevisionResult(
                success=True,
                message="全新创作",
                revised_plan=base_plan,
                revision_type=None,
                modified_parts=[]
            )

        revision_type = revision_intent.revision_type

        if revision_type == "add":
            return self._apply_add(base_plan, revision_intent, user_instruction, llm_planner, analyze_result)
        elif revision_type == "remove":
            return self._apply_remove(base_plan, revision_intent)
        elif revision_type == "modify":
            return self._apply_modify(base_plan, revision_intent, user_instruction, llm_planner, analyze_result)
        else:
            return RevisionResult(
                success=False,
                message=f"未知的 revision_type: {revision_type}",
                revised_plan=base_plan,
                revision_type=revision_type,
                modified_parts=[]
            )

    def _apply_add(
        self,
        base_plan: UnifiedPlan,
        revision_intent: RevisionIntent,
        user_instruction: str,
        llm_planner=None,
        analyze_result=None
    ) -> RevisionResult:
        """
        处理新增声部

        使用 LLM 根据用户指令生成新声部配置
        """
        if not llm_planner:
            return self._build_failure_result(base_plan, "add", "新增声部需要 LLM Planner")

        try:
            # 构建上下文：告知 LLM 现有声部，让它推荐新声部
            existing_parts = []
            for part in base_plan.ensemble.parts:
                existing_parts.append(f"- {part.id}: {part.instrument} ({part.role})")

            existing_parts_str = "\n".join(existing_parts)

            # 复用 llm_planner 的 generate_plan，但传入特殊指令
            # 让 LLM 在现有方案基础上添加新声部
            modified_plan = llm_planner.apply_revision_for_add(
                base_plan=base_plan,
                user_instruction=user_instruction,
                existing_parts_str=existing_parts_str,
                analyze_result=analyze_result
            )

            is_valid, validation_message, modified_part_ids = self._validate_add_result(
                base_plan,
                modified_plan,
            )
            if not is_valid:
                return self._build_failure_result(base_plan, "add", validation_message)

            return RevisionResult(
                success=True,
                message=f"成功新增 {len(modified_part_ids)} 个声部",
                revised_plan=modified_plan,
                revision_type="add",
                modified_parts=modified_part_ids
            )

        except Exception as e:
            logger.error(f"Failed to add parts: {e}")
            return self._build_failure_result(base_plan, "add", f"新增声部失败: {str(e)}")

    def _apply_remove(
        self,
        base_plan: UnifiedPlan,
        revision_intent: RevisionIntent
    ) -> RevisionResult:
        """
        处理删除声部
        """
        target_id = revision_intent.target_part_id
        if not target_id:
            return self._build_failure_result(base_plan, "remove", "删除声部需要指定 target_part_id")

        # 找到要删除的声部
        parts_to_remove = [p.id for p in base_plan.ensemble.parts if p.id == target_id]
        if not parts_to_remove:
            return self._build_failure_result(base_plan, "remove", f"未找到声部: {target_id}")

        # 创建新 plan，移除指定声部
        new_parts = [p for p in base_plan.ensemble.parts if p.id != target_id]

        # 重建 ensemble
        new_ensemble = EnsembleConfig(
            name=base_plan.ensemble.name,
            size=base_plan.ensemble.size,
            target_size=len(new_parts),
            parts=new_parts,
            auto_configure=base_plan.ensemble.auto_configure
        )

        # 复制 plan 并替换 ensemble
        new_plan_dict = base_plan.model_dump()
        new_plan_dict["ensemble"] = new_ensemble.model_dump()
        new_plan_dict["ensemble"]["parts"] = [p.model_dump() for p in new_parts]

        revised_plan = UnifiedPlan(**new_plan_dict)

        return RevisionResult(
            success=True,
            message=f"成功删除声部: {target_id}",
            revised_plan=revised_plan,
            revision_type="remove",
            modified_parts=parts_to_remove
        )

    def _apply_modify(
        self,
        base_plan: UnifiedPlan,
        revision_intent: RevisionIntent,
        user_instruction: str,
        llm_planner=None,
        analyze_result=None
    ) -> RevisionResult:
        """
        处理修改现有声部
        """
        target_id = revision_intent.target_part_id
        if not target_id:
            return self._build_failure_result(base_plan, "modify", "修改声部需要指定 target_part_id")

        # 找到要修改的声部
        target_part = None
        for part in base_plan.ensemble.parts:
            if part.id == target_id:
                target_part = part
                break

        if not target_part:
            return self._build_failure_result(base_plan, "modify", f"未找到声部: {target_id}")

        if not llm_planner:
            return self._build_failure_result(base_plan, "modify", "修改声部需要 LLM Planner")

        try:
            # 使用 LLM 修改声部配置
            modified_plan = llm_planner.apply_revision_for_modify(
                base_plan=base_plan,
                target_part_id=target_id,
                user_instruction=user_instruction,
                analyze_result=analyze_result
            )

            is_valid, validation_message = self._validate_modify_result(
                base_plan,
                modified_plan,
                target_id,
            )
            if not is_valid:
                return self._build_failure_result(base_plan, "modify", validation_message)

            return RevisionResult(
                success=True,
                message=f"成功修改声部: {target_id}",
                revised_plan=modified_plan,
                revision_type="modify",
                modified_parts=[target_id]
            )

        except Exception as e:
            logger.error(f"Failed to modify part: {e}")
            return self._build_failure_result(base_plan, "modify", f"修改声部失败: {str(e)}")


def apply_revision_to_plan(
    base_plan: UnifiedPlan,
    revision_intent: RevisionIntent,
    user_instruction: str,
    llm_planner=None,
    analyze_result=None
) -> RevisionResult:
    """
    便捷函数：对 plan 应用 revision

    Args:
        base_plan: 基础编曲方案
        revision_intent: 修改意图
        user_instruction: 用户的原始指令
        llm_planner: LLM Planner
        analyze_result: MIDI 分析结果

    Returns:
        RevisionResult
    """
    executor = RevisionExecutor()
    return executor.apply_revision(
        base_plan=base_plan,
        revision_intent=revision_intent,
        user_instruction=user_instruction,
        llm_planner=llm_planner,
        analyze_result=analyze_result
    )

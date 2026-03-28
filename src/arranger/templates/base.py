"""
模板基类定义
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, TYPE_CHECKING

from ..plan_schema import NoteEvent, ArrangementContext

if TYPE_CHECKING:
    from ..plan_schema import PartSpec


class BaseTemplate(ABC):
    """
    模板基类

    所有模板必须继承此类并实现 generate 方法
    """

    # 模板名称
    name: str = "base_template"

    # 模板描述
    description: str = "Base template"

    # 适用的乐器列表
    applicable_instruments: List[str] = []

    # 适用的角色列表
    applicable_roles: List[str] = []

    @abstractmethod
    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成音符事件

        Args:
            context: 编排上下文（和声、调性、节拍等）
            params: 模板参数

        Returns:
            音符事件列表
        """
        pass

    def get_default_params(self) -> Dict[str, Any]:
        """
        返回默认参数

        Returns:
            默认参数字典
        """
        return {}

    def can_apply(self, part: "PartSpec") -> bool:
        """
        检查模板是否适用于指定声部

        Args:
            part: 声部规格

        Returns:
            是否适用
        """
        if self.applicable_instruments and part.instrument not in self.applicable_instruments:
            return False
        if self.applicable_roles and part.role not in self.applicable_roles:
            return False
        return True

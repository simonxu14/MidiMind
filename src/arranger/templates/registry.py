"""
模板注册表

自动发现并注册所有模板
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import List, Dict, Optional, Type

from .base import BaseTemplate


class TemplateRegistry:
    """
    模板注册表

    管理所有可用的模板，支持按乐器/角色查询
    """

    def __init__(self):
        self._templates: Dict[str, BaseTemplate] = {}

    def register(self, template: BaseTemplate) -> None:
        """
        注册模板

        Args:
            template: 模板实例
        """
        self._templates[template.name] = template

    def get(self, name: str) -> Optional[BaseTemplate]:
        """
        获取指定名称的模板

        Args:
            name: 模板名称

        Returns:
            模板实例或 None
        """
        return self._templates.get(name)

    def get_for_instrument(self, instrument: str) -> List[BaseTemplate]:
        """
        获取适用于指定乐器的模板

        Args:
            instrument: 乐器名称

        Returns:
            模板列表
        """
        return [
            t for t in self._templates.values()
            if instrument in t.applicable_instruments
        ]

    def get_for_role(self, role: str) -> List[BaseTemplate]:
        """
        获取适用于指定角色的模板

        Args:
            role: 角色名称

        Returns:
            模板列表
        """
        return [
            t for t in self._templates.values()
            if role in t.applicable_roles
        ]

    def get_for_instrument_and_role(
        self,
        instrument: str,
        role: str
    ) -> List[BaseTemplate]:
        """
        获取同时适用于指定乐器和角色的模板

        Args:
            instrument: 乐器名称
            role: 角色名称

        Returns:
            模板列表
        """
        return [
            t for t in self._templates.values()
            if instrument in t.applicable_instruments
            and role in t.applicable_roles
        ]

    def list_templates(self) -> List[str]:
        """
        列出所有已注册的模板名称

        Returns:
            模板名称列表
        """
        return list(self._templates.keys())

    def discover_templates(self, templates_dir: Path) -> None:
        """
        自动发现并注册模板

        Args:
            templates_dir: 模板目录路径
        """
        # 获取包的根路径（arranger）
        package_root = templates_dir.parent

        # 确定正确的包名
        # 当用 "python -m uvicorn src.arranger.api:app" 启动时，模块名是 "src.arranger"
        # 而不是 "arranger"
        src_dir = package_root.parent
        src_dir_str = str(src_dir)
        if src_dir_str not in sys.path:
            sys.path.insert(0, src_dir_str)

        # 构建包名：如果 src/arranger 在 sys.path，用 src.arranger；否则用 arranger
        package_name = package_root.name
        src_suffix = src_dir.name  # e.g., "src"

        # 检查是否有 src/arranger 这样的结构，并且可以从 sys.path 导入
        # 如果 sys.path 包含 /path/to/src，那么包名应该是 src.arranger
        # 否则就是 arranger
        potential_module_name = f"{src_suffix}.{package_name}"
        try:
            # 测试是否能导入
            importlib.import_module(f"{potential_module_name}.templates")
            package_name = potential_module_name
        except ImportError:
            # 回退到只使用 arranger
            pass

        # 遍历所有 Python 文件
        for py_file in templates_dir.rglob("*.py"):
            # 跳过 __init__.py 和 base.py
            if py_file.name.startswith("_"):
                continue
            if py_file.stem == "base":
                continue
            if py_file.stem == "registry":
                continue

            # 构建模块路径
            relative_path = py_file.relative_to(templates_dir)
            module_parts = list(relative_path.parts[:-1]) + [py_file.stem]
            module_name = f"{package_name}.templates." + ".".join(module_parts)

            try:
                # 动态导入模块
                module = importlib.import_module(module_name)

                # 获取模块自己的 BaseTemplate（避免不同包路径的 BaseTemplate 混淆）
                module_base = getattr(module, 'BaseTemplate', None)
                if module_base is None:
                    continue

                # 查找所有模板类
                for name in dir(module):
                    obj = getattr(module, name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, module_base)
                        and obj is not module_base
                    ):
                        # 注册模板实例
                        self.register(obj())

            except ImportError as e:
                print(f"Warning: Could not import template module {module_name}: {e}")


# ============ 全局模板注册表 ============

# 全局注册表实例
_registry: Optional[TemplateRegistry] = None


def get_registry() -> TemplateRegistry:
    """
    获取全局模板注册表

    Returns:
        模板注册表实例
    """
    global _registry

    if _registry is None:
        _registry = TemplateRegistry()

        # 自动发现模板
        templates_dir = Path(__file__).parent
        _registry.discover_templates(templates_dir)

    return _registry


def register_template(template: BaseTemplate) -> None:
    """注册模板到全局注册表"""
    get_registry().register(template)


def get_template(name: str) -> Optional[BaseTemplate]:
    """获取指定名称的模板"""
    return get_registry().get(name)


def list_templates() -> List[str]:
    """列出所有模板"""
    return get_registry().list_templates()

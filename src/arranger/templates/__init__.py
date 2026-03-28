"""
模板系统导出
"""

from .base import BaseTemplate
from .registry import (
    TemplateRegistry,
    get_registry,
    register_template,
    get_template,
    list_templates,
)

__all__ = [
    "BaseTemplate",
    "TemplateRegistry",
    "get_registry",
    "register_template",
    "get_template",
    "list_templates",
]

"""
测试模板系统
"""

import pytest
from arranger.templates.registry import TemplateRegistry, get_registry
from arranger.templates.base import BaseTemplate
from arranger.plan_schema import ArrangementContext, ChordInfo


class TestTemplateRegistry:
    """测试模板注册表"""

    def test_get_registry_singleton(self):
        """测试全局注册表是单例"""
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    def test_list_templates(self):
        """测试列出所有模板"""
        reg = get_registry()
        templates = reg.list_templates()
        assert len(templates) > 0
        assert isinstance(templates, list)
        assert all(isinstance(name, str) for name in templates)

    def test_get_template(self):
        """测试获取指定模板"""
        reg = get_registry()
        template = reg.get("broken_8ths")
        assert template is not None
        assert template.name == "broken_8ths"

    def test_get_nonexistent_template(self):
        """测试获取不存在的模板"""
        reg = get_registry()
        template = reg.get("nonexistent_template")
        assert template is None

    def test_get_for_instrument(self):
        """测试按乐器获取模板"""
        reg = get_registry()

        piano_templates = reg.get_for_instrument("piano")
        assert len(piano_templates) > 0
        assert all("piano" in t.applicable_instruments for t in piano_templates)

        violin_templates = reg.get_for_instrument("violin")
        assert len(violin_templates) > 0
        assert all("violin" in t.applicable_instruments for t in violin_templates)

    def test_get_for_role(self):
        """测试按角色获取模板"""
        reg = get_registry()

        melody_templates = reg.get_for_role("melody")
        assert len(melody_templates) > 0
        assert all("melody" in t.applicable_roles for t in melody_templates)

        bass_templates = reg.get_for_role("bass")
        assert len(bass_templates) > 0
        assert all("bass" in t.applicable_roles for t in bass_templates)

    def test_get_for_instrument_and_role(self):
        """测试同时按乐器和角色获取模板"""
        reg = get_registry()

        templates = reg.get_for_instrument_and_role("piano", "accompaniment")
        assert len(templates) > 0
        for t in templates:
            assert "piano" in t.applicable_instruments
            assert "accompaniment" in t.applicable_roles


class TestTemplateBase:
    """测试 BaseTemplate 基类"""

    def test_template_has_required_attributes(self):
        """测试模板有必需的属性"""
        reg = get_registry()
        for name in reg.list_templates():
            template = reg.get(name)
            assert hasattr(template, "name")
            assert hasattr(template, "description")
            assert hasattr(template, "applicable_instruments")
            assert hasattr(template, "applicable_roles")
            assert hasattr(template, "default_params")
            assert hasattr(template, "generate")


class TestBroken8thsTemplate:
    """测试分解八分音符模板"""

    @pytest.fixture
    def mock_context(self):
        """创建模拟上下文"""
        chord_per_measure = {
            0: ChordInfo(root=60, third=64, fifth=67, quality="major"),
            1: ChordInfo(root=62, third=65, fifth=69, quality="minor"),
        }
        return ArrangementContext(
            chord_per_measure=chord_per_measure,
            measure_len=1920,
            ticks_per_beat=480,
        )

    def test_generate_basic(self, mock_context):
        """测试基本生成"""
        reg = get_registry()
        template = reg.get("broken_8ths")
        assert template is not None

        notes = template.generate(mock_context, {})
        assert isinstance(notes, list)
        # 每个小节4个八分音符，2个小节 = 8个音符
        assert len(notes) > 0

    def test_generate_with_params(self, mock_context):
        """测试带参数生成"""
        reg = get_registry()
        template = reg.get("broken_8ths")

        notes = template.generate(mock_context, {"density": 0.5, "velocity_base": 60})
        assert isinstance(notes, list)

    def test_density_affects_note_count(self, mock_context):
        """测试密度参数影响音符数量"""
        reg = get_registry()
        template = reg.get("broken_8ths")

        notes_full = template.generate(mock_context, {"density": 1.0})
        notes_half = template.generate(mock_context, {"density": 0.5})

        # 更高密度应该产生更多或相等数量的音符
        assert len(notes_full) >= len(notes_half)


class TestAlberti8thsTemplate:
    """测试阿尔贝蒂低音模板"""

    @pytest.fixture
    def mock_context(self):
        """创建模拟上下文"""
        chord_per_measure = {
            0: ChordInfo(root=48, third=52, fifth=55, quality="major"),
        }
        return ArrangementContext(
            chord_per_measure=chord_per_measure,
            measure_len=1920,
            ticks_per_beat=480,
        )

    def test_generate_basic(self, mock_context):
        """测试基本生成"""
        reg = get_registry()
        template = reg.get("alberti_8ths")
        assert template is not None

        notes = template.generate(mock_context, {})
        assert isinstance(notes, list)
        # 阿尔贝蒂模式：根音-五音-三音-五音，4个八分音符
        assert len(notes) == 4


class TestCelloPedalRootTemplate:
    """测试大提琴持续根音模板"""

    @pytest.fixture
    def mock_context(self):
        """创建模拟上下文"""
        chord_per_measure = {
            0: ChordInfo(root=36, third=40, fifth=43, quality="major"),
            1: ChordInfo(root=38, third=41, fifth=45, quality="minor"),
        }
        return ArrangementContext(
            chord_per_measure=chord_per_measure,
            measure_len=1920,
            ticks_per_beat=480,
        )

    def test_generate_basic(self, mock_context):
        """测试基本生成"""
        reg = get_registry()
        template = reg.get("cello_pedal_root")
        assert template is not None

        notes = template.generate(mock_context, {})
        assert isinstance(notes, list)
        # 每个小节1个根音
        assert len(notes) == 2

    def test_notes_in_bass_range(self, mock_context):
        """测试音符在低音区范围内"""
        reg = get_registry()
        template = reg.get("cello_pedal_root")

        notes = template.generate(mock_context, {})
        for note in notes:
            tick, end_tick, pitch, velocity, channel = note
            # 大提琴低音区范围是 36-55
            assert 36 <= pitch <= 55

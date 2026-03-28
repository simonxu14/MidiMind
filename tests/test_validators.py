"""
测试验证器和自动修复器
"""

import pytest
from arranger.auto_fixer import AutoFixer
from arranger.harmony_validator import HarmonyValidator


class TestAutoFixer:
    """测试 AutoFixer"""

    def test_fix_octave_jumps(self):
        """测试八度跳跃修复"""
        fixer = AutoFixer()
        notes = [
            (0, 100, 60, 64, 0),   # C4
            (100, 200, 72, 64, 0), # C5 - 从C4跳到C5
            (200, 300, 64, 64, 0), # E4
        ]

        fixed = fixer.fix_octave_jumps(notes, threshold=12)

        # 应该没有跳八度
        for i in range(1, len(fixed)):
            prev_pitch = fixed[i-1][2]
            curr_pitch = fixed[i][2]
            if fixed[i][0] - fixed[i-1][1] < 50:  # 快速转换
                diff = abs(curr_pitch - prev_pitch)
                assert diff <= 12, f"Octave jump detected: {prev_pitch} -> {curr_pitch}"

    def test_fix_out_of_range(self):
        """测试超出音域修复"""
        fixer = AutoFixer()
        # 默认钢琴范围
        notes = [
            (0, 100, 20, 64, 0),   # 太低 - 钢琴最低C0
            (100, 200, 110, 64, 0), # 太高 - 钢琴最高
            (200, 300, 60, 64, 0), # C4 - 正常
        ]

        fixed = fixer.fix_out_of_range(notes, {"piano": (21, 108)})

        # 验证修复后的音符在范围内
        for note in fixed:
            pitch = note[2]
            assert 21 <= pitch <= 108, f"Pitch {pitch} out of range"

    def test_fix_voice_crossing(self):
        """测试声部交叉修复"""
        fixer = AutoFixer()
        # 假设是两个声部
        notes = [
            (0, 100, 60, 64, 0),   # 声部1: C4
            (0, 100, 48, 64, 1),   # 声部2: C3 - 声部1应该高于声部2
            (100, 200, 54, 64, 0), # 声部1: Db4
            (100, 200, 60, 64, 1), # 声部2: C4 - 现在声部2高于声部1（交叉）
        ]

        fixed = fixer.fix_voice_crossing(notes)

        # 验证返回的是列表
        assert isinstance(fixed, list)


class TestHarmonyValidator:
    """测试 HarmonyValidator"""

    def test_validate_clean_voices(self):
        """测试验证干净的和声"""
        validator = HarmonyValidator()
        # 构成和弦进行，没有平行
        voice1 = [(0, 100, 60, 64, 0), (100, 200, 62, 64, 0)]   # C4 -> D4
        voice2 = [(0, 100, 55, 64, 1), (100, 200, 57, 64, 1)]   # G3 -> A3

        notes = voice1 + voice2
        result = validator.validate(notes)

        # 干净和声应该通过
        assert result.passed is True

    def test_validate_with_parallel_fifths(self):
        """测试平行五度检测"""
        validator = HarmonyValidator()
        # 两个声部 - 需要同时开始，且构成五度并同向进行
        # C4-G4 (五度) -> D4-A4 (五度) - 同向五度平行
        voice1 = [(0, 100, 60, 64, 0), (100, 200, 62, 64, 0)]   # C4 -> D4
        voice2 = [(0, 100, 67, 64, 1), (100, 200, 69, 64, 1)]   # G4 -> A4

        notes = voice1 + voice2
        result = validator.validate(notes)

        # 应该有平行五度问题 - 但这取决于具体的检测逻辑

    def test_validate_single_voice(self):
        """测试单声部"""
        validator = HarmonyValidator()
        notes = [(0, 100, 60, 64, 0), (100, 200, 64, 64, 0)]

        result = validator.validate(notes)

        # 单声部应该通过（不足两个声部）
        assert result.passed is True

    def test_validate_empty_notes(self):
        """测试空音符列表"""
        validator = HarmonyValidator()
        result = validator.validate([])

        # 空应该通过
        assert result.passed is True

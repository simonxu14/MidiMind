"""
LLM Planner - 意图驱动的编曲规划器

根据用户意图和 MIDI 分析结果，调用 LLM 生成完整的编曲方案。
支持多轮对话和完整的过程追踪。
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional, Dict, Any, List
from anthropic import Anthropic, NOT_GIVEN

from .plan_schema import (
    UnifiedPlan,
    TransformSpec,
    EnsembleConfig,
    PartSpec,
    MidiSpec,
    Constraints,
    LockMelodyConfig,
    HarmonyContext,
    OutputConfig,
    MidiOutputConfig,
    AnalyzeResponse,
)
from .conversation import conversation_manager, MessageRole, LLMThought
from .tracer import get_tracer


class LLMPlanner:
    """
    LLM 编曲规划器

    完全基于用户意图生成编曲方案，支持：
    - 多轮对话优化
    - 完整的 LLM 思考追踪
    - 根据历史反馈改进方案
    """

    def __init__(self, api_key: Optional[str] = None, conversation_id: Optional[str] = None):
        self.client = Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "dummy"),
            base_url=os.environ.get("ANTHROPIC_BASE_URL") or "https://api.minimaxi.com/anthropic",
        )
        self.conversation_id = conversation_id
        self.tracer = get_tracer(conversation_id) if conversation_id else None

    SYSTEM_PROMPT = """你是一位顶级的乐队编曲大师。你的任务是根据用户的音乐意图和原始 MIDI 分析结果，创造性地设计一个最优的编曲方案。

## 你的核心能力

1. **深度理解用户意图**：准确把握用户想要表达的音乐风格、情绪、氛围
2. **创造性编曲**：不拘泥于固定模式，而是根据每首曲子独特的特点来编配
3. **专业乐队知识**：熟练掌握各种乐器的特性，知道如何让它们和谐配合

## 可用乐器库

**弦乐**:
- violin (小提琴) - 高音旋律，声音明亮
- viola (中提琴) - 中音旋律，温暖饱满
- cello (大提琴) - 低音旋律，深沉有力
- double_bass (低音提琴) - 最低音，稳固根基

**木管**:
- flute (长笛) - 清脆灵活，适合装饰旋律
- oboe (双簧管) - 富有表现力，独特音色
- clarinet (单簧管) - 灵活多变，跨越多个音区
- bassoon (巴松管) - 低音木管，幽默而深沉

**铜管**:
- horn (圆号) - 温暖和弦，连接木管和铜管
- trumpet (小号) - 明亮有力，节奏感强
- trombone (长号) - 庄严厚重，低音铜管
- tuba (大号) - 最低音，庄严稳固

**键盘/打击**:
- piano (钢琴) - 表现力丰富，流行/爵士必备
- timpani (定音鼓) - 节奏核心，低音打击

## 角色类型（必须严格使用以下角色之一）

**旋律类**:
- melody: 主旋律 - 乐曲的核心线

**内声部类**:
- inner_voice: 内声部 - 和声填充
- counter_melody: 副旋律 - 呼应的旋律线

**低音类**:
- bass: 低音 - 根基支撑
- bass_rhythm: 低音节奏 - 有节奏的低音型
- anchor: 锚固 - 稳定的低音基础

**伴奏类**:
- accompaniment: 伴奏 - 织体填充
- sustain_support: 持续音 - 氛围营造

**强调类**:
- accent: 强调 - 突出重点
- fanfare: 号角性 - 强劲有力的节奏型

**打击乐类**:
- percussion: 打击乐 - 节奏核心

**合奏类**:
- tutti: 全奏 - 整个声部组合

## 关键编曲原则

1. **钢琴是流行歌曲的灵魂**：如果原曲有钢琴或用户要求现代风格，钢琴必须作为核心
2. **阿尔贝蒂低音**：钢琴伴奏首选模式 - 根-五-三-五的循环
3. **乐器搭配法则**：
   - 每种乐器角色明确，不重复
   - 高音弦乐+中音木管+低音铜管形成天然分层
   - 避免声部交叉
4. **密度匹配风格**：
   - 轻柔风格：钢琴+少数弦乐，稀疏有致
   - 强劲风格：全乐队，节奏密集
5. **乐队规模决定复杂度**：
   - 4人：精简核心，每个声部都关键
   - 10人：室内乐标配，平衡丰富
   - 15人+：交响规模，音色丰富

## 钢琴伴奏模板（用于 template_params）

推荐使用 `dense_accompaniment` 模板，参数：
- density: 0.95-0.98（极高密度）
- style: modern/ballad/dance
- voicing: spread（八度展开）
- register: full（C2-C7 五八度）
- include_octaves: true
- alberti_octave_repeat: true
- bass_octave_depth: 2-3

## 声部排列规则（Voicing）

**close voicing（密集排列）**：和弦音紧密聚集在一个八度内
- 适合：独奏段落、室内乐、需要集中音色的时刻
- 钢琴在小型编制中常用 close voicing

**open voicing（开放排列）**：和弦音分散在多个八度
- 适合：交响乐队、全奏段落、需要宽阔音色的时刻
- 大型编制中各乐器分工不同音区

**spread voicing（八度展开）**：根音在低音，中高音区展开
- 适合：流行、爵士、大部分现代风格
- 钢琴伴奏首选

**一般原则**：
- 低音区：bass/double_bass 负责根音
- 中音区：cello/viola/horn 负责内声部
- 高音区：violin/flute 负责旋律和装饰

## 力度与奏法指导（template_params 中的 expressive 参数）

**velocity_curve**：力度曲线
- default: 标准力度
- crescendo: 渐强
- decrescendo: 渐弱
- sfz: 突强
- fp: 强后即弱

**articulation**：奏法
- normal: 正常连奏
- staccato: 断音
- legato: 完全连奏
- marcato: 强调重音

**建议**：在 template_params 中添加 expressive 参数来增强音乐表现力
```json
"template_params": {
  "density": 0.8,
  "expressive": {
    "dynamics": "crescendo",
    "articulation": "legato",
    "velocity_base": 80,
    "velocity_variance": 15
  }
}
```

## 各乐器模板映射（每个声部都必须指定 template_name）

**弦乐**:
- violin + melody: 使用 `violin_cantabile`（抒情旋律线）
- violin + counter_melody: 使用 `violin_cantabile`
- cello + bass: 使用 `cello_pedal_root`（持续根音支撑）
- cello + inner_voice: 使用 `cello_pedal_root`
- viola + inner_voice: 使用 `viola_inner_16ths`（16分音符内声部）

**木管**:
- flute + counter_melody: 使用 `flute_countermelody`（长笛副旋律）
- flute + inner_voice: 使用 `flute_countermelody`
- clarinet + inner_voice: 使用 `clarinet_sustain`（单簧管持续）
- clarinet + counter_melody: 使用 `clarinet_sustain`
- oboe + counter_melody: 使用 `oboe_color_tone`（双簧管色彩音）
- bassoon + bass: 使用 `bassoon_bass_line`（巴松管低音线）

**铜管**:
- horn + sustain_support: 使用 `root_pad`（圆号根音垫底）
- trumpet + melody: 使用 `trumpet_melody`（小号旋律线）
- trumpet + counter_melody: 使用 `trumpet_melody`
- trumpet + accent: 使用 `trumpet_fanfare`（小号号角性）
- trombone + bass: 使用 `trombone_anchor`（长号低音锚固）

**打击乐**:
- timpani + bass_rhythm: 使用 `timpani_rhythm`（定音鼓节奏）- 注意：定音鼓的 role 必须是 `bass_rhythm`，不是 `accent`
- percussion + accent: 使用 `accent_cymbal`（镲片强调）

**键盘**:
- piano + accompaniment: 使用 `dense_accompaniment`（高密度伴奏）
- piano + inner_voice: 使用 `arpeggio`（分解和弦）
- piano + melody: 使用 `piano_melody`（钢琴旋律）
- piano + counter_melody: 使用 `piano_melody`

## 重要：每个声部都必须指定 template_name

**错误示例**（LLM 实际返回的问题）：
```json
{
  "id": "vn1",
  "role": "melody",
  "instrument": "violin"
  // 缺少 template_name 和 template_params！
}
```

**正确示例**：
```json
{
  "id": "vn1",
  "role": "melody",
  "instrument": "violin",
  "template_name": "violin_cantabile",
  "template_params": {}
}
```

template_name 是**必须**的，不能省略！

## 输出要求

你必须返回一个完整、专业的 UnifiedPlan JSON，包含：

```json
{
  "ensemble": {
    "name": "自定义乐队名称",
    "size": "small/medium/large",
    "parts": [
      {
        "id": "vn1",
        "name": "第一小提琴",
        "role": "melody",
        "instrument": "violin",
        "midi": {"channel": 0, "program": 40},
        "template_name": "violin_cantabile",
        "template_params": {}
      },
      {
        "id": "piano",
        "name": "钢琴",
        "role": "accompaniment",
        "instrument": "piano",
        "midi": {"channel": 1, "program": 0},
        "template_name": "dense_accompaniment",
        "template_params": {"density": 0.95, "style": "modern"}
      }
    ]
  }
}
```

**重要格式要求**：
1. JSON 必须包含 `ensemble.parts` 数组
2. 每个 part 必须有 `id`, `name`, `role`, `instrument`, `midi`
3. `midi` 必须包含 `channel` (0-15) 和 `program` (0-127)
4. **每个 part 必须有 `template_name`（不能省略！），根据乐器和角色选择对应的模板**
5. `template_params` 可以为空对象 `{}`，但 `template_name` 不能为 "unknown"
6. **只输出 JSON，不要有任何解释文字**
7. 确保 channel 不冲突（melody 用 channel 0）

**关键：source_track_ref 设置**
- `constraints.lock_melody_events.source_track_ref` 必须是**包含音符的轨道索引**
- **绝对不能使用 "0"**，因为 Track 0 通常是 tempo/conductor track，**没有音符**
- 从 melody_candidates 信息中可以看到哪个轨道有音符（Track 1 Piano 有最高分 0.50）
- 正确示例：`"source_track_ref": "1"`（如果 Track 1 有音符）
"""

    def generate_plan(
        self,
        analyze_result: AnalyzeResponse,
        user_intent: str,
        target_size: Optional[int] = None,
        previous_feedback: Optional[str] = None
    ) -> UnifiedPlan:
        """
        生成编曲方案

        Args:
            analyze_result: MIDI 分析结果
            user_intent: 用户意图（自然语言描述）
            target_size: 目标乐队规模（可选）
            previous_feedback: 上一版本的反馈（用于多轮优化）
        """
        start_time = time.time()

        # 构建增强的用户提示
        user_prompt = self._build_user_prompt(analyze_result, user_intent, target_size, previous_feedback)

        # 如果有上一版本的反馈，添加到 system prompt
        system_with_context = self.SYSTEM_PROMPT
        if previous_feedback:
            system_with_context += f"\n\n## 历史反馈\n用户对上一版本的反馈：{previous_feedback}\n请根据反馈优化编曲方案。"

        # 记录 LLM 调用
        self.tracer.start_stage("plan_generation") if self.tracer else None

        try:
            response = self.client.messages.create(
                model="MiniMax-M2.7",
                max_tokens=8192,
                system=system_with_context,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 解析响应 - MiniMax 可能返回不同格式
            # MiniMax 返回 [ThinkingBlock, TextBlock]，需要找到 TextBlock
            plan_text = ""
            try:
                if hasattr(response, 'content') and response.content:
                    for content_block in response.content:
                        if hasattr(content_block, 'type') and content_block.type == 'text':
                            plan_text = content_block.text.strip()
                            break
                        elif hasattr(content_block, 'text'):
                            plan_text = content_block.text.strip()
                            break
                    if not plan_text:
                        # 如果没找到 text 类型，整个响应转字符串
                        plan_text = str(response.content)
                else:
                    plan_text = str(response)
            except Exception as e:
                raise Exception(f"Failed to parse response content: {e}, response={response}")

            # 提取 JSON
            if "```json" in plan_text:
                plan_text = plan_text.split("```json")[1].split("```")[0]
            elif "```" in plan_text:
                plan_text = plan_text.split("```")[1].split("```")[0]

            # 记录 LLM 响应 - MiniMax 使用不同的 usage 格式
            try:
                usage = getattr(response, 'usage', None)
                if usage:
                    tokens_used = getattr(usage, 'total_tokens', 0) or \
                                  (getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0))
                else:
                    tokens_used = 0
            except Exception:
                tokens_used = 0

            if self.tracer:
                self.tracer.log_llm_call(
                    name="plan_generation",
                    model="MiniMax-M2.7",
                    prompt=user_prompt,
                    response=plan_text,
                    tokens_used=tokens_used,
                    duration_ms=duration_ms
                )

            if self.conversation_id:
                thought = LLMThought(
                    stage="plan_generation",
                    prompt=user_prompt,
                    response=plan_text,
                    model="MiniMax-M2.7",
                    tokens_used=tokens_used,
                    duration_ms=duration_ms
                )
                conversation_manager.add_llm_thought(self.conversation_id, thought)

            plan_dict = json.loads(plan_text)

            # 验证并补充必要字段
            plan_dict = self._validate_and_complete_plan(plan_dict, analyze_result)

            return UnifiedPlan(**plan_dict)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            if self.tracer:
                self.tracer.log_error("plan_generation", e)

            if self.conversation_id:
                thought = LLMThought(
                    stage="plan_generation",
                    prompt=user_prompt,
                    response="",
                    model="MiniMax-M2.7",
                    tokens_used=0,
                    duration_ms=duration_ms,
                    error=str(e)
                )
                conversation_manager.add_llm_thought(self.conversation_id, thought)

            # LLM 失败时不要静默 fallback，而是抛出错误让用户知道
            # fallback 方案不遵循用户的详细意图
            raise Exception(f"LLM 编曲失败: {str(e)}。请检查 API 配置或重试。")

    def _build_user_prompt(
        self,
        analyze_result: AnalyzeResponse,
        user_intent: str,
        target_size: Optional[int],
        previous_feedback: Optional[str]
    ) -> str:
        """构建详细的用户提示"""

        melody_info = ", ".join([
            f"Track {c.track_index} (score: {c.score:.2f})"
            for c in analyze_result.melody_candidates[:3]
        ]) or "未检测到"

        duration = analyze_result.total_ticks / analyze_result.ticks_per_beat / (analyze_result.tempo / 60)

        prompt_parts = [
            f"## 用户意图",
            f"{user_intent}",
            "",
            f"## MIDI 分析结果",
            f"- 轨道数：{len(analyze_result.tracks)}",
            f"- 速度 (BPM)：{analyze_result.tempo}",
            f"- 拍号：{analyze_result.time_signature}",
            f"- 总时长：{duration:.1f} 秒",
            f"- 旋律轨道：{melody_info}",
        ]

        if target_size:
            prompt_parts.append(f"\n## 指定乐队规模")
            prompt_parts.append(f"用户要求：{target_size} 人乐队")

        if previous_feedback:
            prompt_parts.append(f"\n## 历史反馈")
            prompt_parts.append(f"用户对上一版本的反馈：{previous_feedback}")
            prompt_parts.append("请根据反馈改进编曲方案。")

        prompt_parts.extend([
            "",
            "## 你的任务",
            "请根据以上信息，设计一个最能表达用户意图的编曲方案。",
            "考虑：",
            "1. 乐器的音色搭配是否和谐",
            "2. 各声部的角色分配是否合理",
            "3. 伴奏织体是否与主旋律平衡",
            "4. 整体风格是否符合用户意图",
            "",
            "请直接输出 JSON，不要有其他文字。"
        ])

        return "\n".join(prompt_parts)

    def _validate_and_complete_plan(self, plan_dict: Dict, analyze_result: AnalyzeResponse) -> Dict:
        """
        验证并补充计划字段

        LLM 可能返回各种格式，这里做标准化处理
        """

        # 自动检测 source_track_ref：使用 melody_candidates 中分数最高的轨道
        auto_source_track = "0"
        if analyze_result and hasattr(analyze_result, 'melody_candidates') and analyze_result.melody_candidates:
            # 找到分数最高的候选（这是实际的旋律轨道）
            top_candidate = max(analyze_result.melody_candidates, key=lambda c: c.score)
            auto_source_track = str(top_candidate.track_index)

        # 构建完整的 plan 结构
        complete_plan = {
            "schema_version": "1.0",
            "transform": {
                "type": plan_dict.get("transform", {}).get("type", "orchestration"),
                "preserve_structure": plan_dict.get("transform", {}).get("preserve_structure", True),
                "preserve_order": plan_dict.get("transform", {}).get("preserve_order", True),
            },
            "ensemble": {
                "name": plan_dict.get("ensemble", {}).get("name", "custom_ensemble"),
                "size": plan_dict.get("ensemble", {}).get("size", "medium"),
                "target_size": len(plan_dict.get("ensemble", {}).get("parts", [])),
                "parts": []
            },
            "harmony_context": {
                "method": "measure_pitchset_triadish",
                "granularity": "per_measure"
            },
            "constraints": {
                "lock_melody_events": {
                    "enabled": True,
                    # 优先使用 LLM 指定的值，否则使用自动检测的值
                    "source_track_ref": plan_dict.get("constraints", {}).get("lock_melody_events", {}).get("source_track_ref") or auto_source_track,
                    "source_track_selection_mode": "auto"
                },
                "keep_total_ticks": True
            },
            "outputs": {
                "midi": {
                    "enabled": True,
                    "filename": "arranged.mid"
                }
            }
        }

        # 处理 parts
        raw_parts = plan_dict.get("ensemble", {}).get("parts", [])
        if not raw_parts and "parts" in plan_dict:
            raw_parts = plan_dict.get("parts", [])

        used_channels = set()
        for part in raw_parts:
            # 标准化每个 part
            standardized_part = {
                "id": part.get("id", f"part_{len(complete_plan['ensemble']['parts'])}"),
                "name": part.get("name", "Unnamed"),
                "role": part.get("role", "accompaniment"),
                "instrument": part.get("instrument", "piano"),
                "midi": {
                    "channel": part.get("midi", {}).get("channel", 0),
                    "program": part.get("midi", {}).get("program", 0)
                }
            }

            # 处理 template
            if "template" in part:
                standardized_part["template_name"] = part["template"]
                standardized_part["template_params"] = part.get("template_params") or {}
            elif "template_name" in part:
                standardized_part["template_name"] = part["template_name"]
                standardized_part["template_params"] = part.get("template_params") or {}
            else:
                standardized_part["template_name"] = "unknown"
                standardized_part["template_params"] = {}

            # 分配 channel
            ch = standardized_part["midi"]["channel"]
            if ch in used_channels:
                for c in range(16):
                    if c not in used_channels:
                        standardized_part["midi"]["channel"] = c
                        break
            used_channels.add(standardized_part["midi"]["channel"])

            complete_plan["ensemble"]["parts"].append(standardized_part)

        # 更新 target_size
        complete_plan["ensemble"]["target_size"] = len(complete_plan["ensemble"]["parts"])

        # 确保 melody 在 channel 0
        melody_parts = [p for p in complete_plan["ensemble"]["parts"] if p.get("role") == "melody"]
        if melody_parts and melody_parts[0]["midi"]["channel"] != 0:
            # 找到 channel 0 的 part 并交换
            for p in complete_plan["ensemble"]["parts"]:
                if p["midi"]["channel"] == 0:
                    p["midi"]["channel"] = melody_parts[0]["midi"]["channel"]
                    break
            melody_parts[0]["midi"]["channel"] = 0

        return complete_plan

    def _get_intent_based_fallback(self, user_intent: str, target_size: Optional[int]) -> UnifiedPlan:
        """根据意图生成 fallback 方案"""

        # 分析用户意图
        is_soft = any(kw in user_intent for kw in ["轻", "柔", "软", "温柔", "抒情"])
        is_popular = any(kw in user_intent for kw in ["流行", "现代", "Jazz", "pop"])
        is_classical = any(kw in user_intent for kw in ["古典", "交响", "大气"])
        is_small = any(kw in user_intent for kw in ["小", "简单", "精简"])

        # 确定规模
        if target_size is None:
            if is_small:
                target_size = 4
            elif is_classical:
                target_size = 15
            else:
                target_size = 10

        # 确定乐器配置
        if is_popular or "钢琴" in user_intent:
            parts = self._get_popular_ensemble(target_size)
        elif is_soft:
            parts = self._get_chamber_ensemble(target_size)
        elif is_classical:
            parts = self._get_symphonic_ensemble(target_size)
        else:
            parts = self._get_chamber_ensemble(target_size)

        return UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(
                type="orchestration",
                preserve_structure=True,
                preserve_order=True
            ),
            ensemble=EnsembleConfig(
                name=f"ensemble_{target_size}",
                size="small" if target_size <= 4 else ("medium" if target_size <= 10 else "large"),
                target_size=target_size,
                parts=[PartSpec(**p) for p in parts]
            ),
            harmony_context=HarmonyContext(
                method="measure_pitchset_triadish",
                granularity="per_measure"
            ),
            constraints=Constraints(
                lock_melody_events=LockMelodyConfig(
                    enabled=True,
                    source_track_ref="0"
                ),
                keep_total_ticks=True
            ),
            outputs=OutputConfig(
                midi=MidiOutputConfig(
                    enabled=True,
                    filename="arranged.mid"
                )
            )
        )

    def _get_popular_ensemble(self, size: int) -> List[Dict]:
        """流行风格乐队配置"""
        if size <= 6:
            return [
                {"id": "vn1", "name": "Violin", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}, "template_name": "violin_cantabile", "template_params": {}},
                {"id": "piano", "name": "Piano", "role": "accompaniment", "instrument": "piano", "midi": {"channel": 1, "program": 0}, "template_name": "dense_accompaniment", "template_params": {"density": 0.98, "style": "modern", "register": "full", "include_octaves": True, "alberti_octave_repeat": True, "bass_octave_depth": 3}},
                {"id": "vc", "name": "Cello", "role": "bass", "instrument": "cello", "midi": {"channel": 2, "program": 42}, "template_name": "cello_pedal_root", "template_params": {}},
                {"id": "cl", "name": "Clarinet", "role": "inner_voice", "instrument": "clarinet", "midi": {"channel": 3, "program": 71}, "template_name": "clarinet_sustain", "template_params": {}},
            ]
        elif size <= 10:
            return [
                {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}, "template_name": "violin_cantabile", "template_params": {}},
                {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}, "template_name": "adaptive_strings", "template_params": {}},
                {"id": "piano", "name": "Piano", "role": "accompaniment", "instrument": "piano", "midi": {"channel": 2, "program": 0}, "template_name": "dense_accompaniment", "template_params": {"density": 0.98, "style": "modern", "register": "full", "include_octaves": True, "alberti_octave_repeat": True, "bass_octave_depth": 3}},
                {"id": "vc", "name": "Cello", "role": "bass", "instrument": "cello", "midi": {"channel": 3, "program": 42}, "template_name": "cello_pedal_root", "template_params": {}},
                {"id": "fl", "name": "Flute", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 4, "program": 73}, "template_name": "flute_countermelody", "template_params": {}},
                {"id": "ob", "name": "Oboe", "role": "counter_melody", "instrument": "oboe", "midi": {"channel": 5, "program": 68}, "template_name": "oboe_color_tone", "template_params": {}},
                {"id": "hn", "name": "Horn", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 6, "program": 60}, "template_name": "root_pad", "template_params": {}},
            ]
        else:
            return [
                {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}, "template_name": "violin_cantabile", "template_params": {}},
                {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}, "template_name": "adaptive_strings", "template_params": {}},
                {"id": "va", "name": "Viola", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 2, "program": 41}, "template_name": "viola_inner_16ths", "template_params": {}},
                {"id": "vc", "name": "Cello", "role": "bass", "instrument": "cello", "midi": {"channel": 3, "program": 42}, "template_name": "cello_pedal_root", "template_params": {}},
                {"id": "db", "name": "Double Bass", "role": "bass", "instrument": "double_bass", "midi": {"channel": 4, "program": 43}, "template_name": "cello_pedal_root", "template_params": {}},
                {"id": "piano", "name": "Piano", "role": "accompaniment", "instrument": "piano", "midi": {"channel": 5, "program": 0}, "template_name": "dense_accompaniment", "template_params": {"density": 0.98, "style": "modern", "register": "full", "include_octaves": True, "alberti_octave_repeat": True, "bass_octave_depth": 3}},
                {"id": "fl1", "name": "Flute I", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 6, "program": 73}, "template_name": "flute_countermelody", "template_params": {}},
                {"id": "fl2", "name": "Flute II", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 7, "program": 73}, "template_name": "flute_countermelody", "template_params": {}},
                {"id": "ob", "name": "Oboe", "role": "counter_melody", "instrument": "oboe", "midi": {"channel": 8, "program": 68}, "template_name": "oboe_color_tone", "template_params": {}},
                {"id": "cl1", "name": "Clarinet I", "role": "inner_voice", "instrument": "clarinet", "midi": {"channel": 9, "program": 71}, "template_name": "clarinet_sustain", "template_params": {}},
                {"id": "hn1", "name": "Horn I", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 10, "program": 60}, "template_name": "root_pad", "template_params": {}},
                {"id": "hn2", "name": "Horn II", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 11, "program": 60}, "template_name": "root_pad", "template_params": {}},
                {"id": "timp", "name": "Timpani", "role": "percussion", "instrument": "timpani", "midi": {"channel": 12, "program": 47}, "template_name": "timpani_rhythm", "template_params": {}},
            ]

    def _get_chamber_ensemble(self, size: int) -> List[Dict]:
        """室内乐风格乐队配置"""
        base = [
            {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}, "template_name": "violin_cantabile", "template_params": {}},
            {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}, "template_name": "adaptive_strings", "template_params": {}},
            {"id": "va", "name": "Viola", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 2, "program": 41}, "template_name": "viola_inner_16ths", "template_params": {}},
            {"id": "vc", "name": "Cello", "role": "bass", "instrument": "cello", "midi": {"channel": 3, "program": 42}, "template_name": "cello_pedal_root", "template_params": {}},
        ]

        if size >= 6:
            base.append({"id": "piano", "name": "Piano", "role": "accompaniment", "instrument": "piano", "midi": {"channel": 4, "program": 0}, "template_name": "dense_accompaniment", "template_params": {"density": 0.95, "style": "modern", "register": "full", "include_octaves": True, "alberti_octave_repeat": True, "bass_octave_depth": 2}})

        if size >= 8:
            base.extend([
                {"id": "fl", "name": "Flute", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 5, "program": 73}, "template_name": "flute_countermelody", "template_params": {}},
                {"id": "cl", "name": "Clarinet", "role": "inner_voice", "instrument": "clarinet", "midi": {"channel": 6, "program": 71}, "template_name": "clarinet_sustain", "template_params": {}},
                {"id": "hn", "name": "Horn", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 7, "program": 60}, "template_name": "root_pad", "template_params": {}},
            ])

        return base[:size]

    def _get_symphonic_ensemble(self, size: int) -> List[Dict]:
        """交响乐团配置"""
        return [
            {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}, "template_name": "violin_cantabile", "template_params": {}},
            {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}, "template_name": "adaptive_strings", "template_params": {}},
            {"id": "va", "name": "Viola", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 2, "program": 41}, "template_name": "viola_inner_16ths", "template_params": {}},
            {"id": "vc", "name": "Cello", "role": "bass", "instrument": "cello", "midi": {"channel": 3, "program": 42}, "template_name": "cello_pedal_root", "template_params": {}},
            {"id": "db", "name": "Double Bass", "role": "bass", "instrument": "double_bass", "midi": {"channel": 4, "program": 43}, "template_name": "adaptive_bass", "template_params": {}},
            {"id": "fl1", "name": "Flute I", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 5, "program": 73}, "template_name": "flute_countermelody", "template_params": {}},
            {"id": "fl2", "name": "Flute II", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 6, "program": 73}, "template_name": "flute_countermelody", "template_params": {}},
            {"id": "ob", "name": "Oboe", "role": "counter_melody", "instrument": "oboe", "midi": {"channel": 7, "program": 68}, "template_name": "oboe_color_tone", "template_params": {}},
            {"id": "cl1", "name": "Clarinet I", "role": "inner_voice", "instrument": "clarinet", "midi": {"channel": 8, "program": 71}, "template_name": "clarinet_sustain", "template_params": {}},
            {"id": "bn", "name": "Bassoon", "role": "bass", "instrument": "bassoon", "midi": {"channel": 9, "program": 70}, "template_name": "adaptive_bass", "template_params": {}},
            {"id": "hn1", "name": "Horn I", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 10, "program": 60}, "template_name": "root_pad", "template_params": {}},
            {"id": "hn2", "name": "Horn II", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 11, "program": 60}, "template_name": "root_pad", "template_params": {}},
            {"id": "tp", "name": "Trumpet", "role": "accent", "instrument": "trumpet", "midi": {"channel": 12, "program": 56}, "template_name": "trumpet_fanfare", "template_params": {}},
            {"id": "trom", "name": "Trombone", "role": "bass", "instrument": "trombone", "midi": {"channel": 13, "program": 57}, "template_name": "trombone_anchor", "template_params": {}},
            {"id": "tuba", "name": "Tuba", "role": "bass", "instrument": "tuba", "midi": {"channel": 14, "program": 58}, "template_name": "adaptive_bass", "template_params": {}},
            {"id": "timp", "name": "Timpani", "role": "bass_rhythm", "instrument": "timpani", "midi": {"channel": 15, "program": 47}, "template_name": "timpani_rhythm", "template_params": {}},
        ][:size]

"""
LLM Planner - 意图驱动的编曲规划器

根据用户意图和 MIDI 分析结果，调用 LLM 生成完整的编曲方案。
支持多轮对话和完整的过程追踪。
"""

from __future__ import annotations

import json
import os
import time
import re
from typing import Optional, Dict, Any, List
from anthropic import Anthropic

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
    RevisionIntent,
)
from .conversation import conversation_manager, MessageRole, LLMThought
from .tracer import get_tracer
from .plan_normalizer import normalize_plan


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
        # 构建增强的用户提示
        user_prompt = self._build_user_prompt(analyze_result, user_intent, target_size, previous_feedback)

        # 如果有上一版本的反馈，添加到 system prompt
        system_with_context = self.SYSTEM_PROMPT
        if previous_feedback:
            system_with_context += f"\n\n## 历史反馈\n用户对上一版本的反馈：{previous_feedback}\n请根据反馈优化编曲方案。"

        # 记录 LLM 调用
        self.tracer.start_stage("plan_generation") if self.tracer else None

        try:
            response, duration_ms = self._call_llm(system_with_context, user_prompt, 8192)

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
            plan_dict = normalize_plan(plan_dict, analyze_result)

            return UnifiedPlan(**plan_dict)

        except Exception as e:
            duration_ms = 0

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
            self._raise_planner_error("LLM 编曲失败，请检查 API 配置或重试", e)

    def _extract_text_from_response(self, response: Any, error_prefix: str) -> str:
        """Extract the first text payload from an Anthropic-style response."""
        try:
            if hasattr(response, "content") and response.content:
                for content_block in response.content:
                    if hasattr(content_block, "type") and content_block.type == "text":
                        return content_block.text.strip()
                    if hasattr(content_block, "text"):
                        return content_block.text.strip()
                return str(response.content)
            return str(response)
        except Exception as exc:
            raise ValueError(f"{error_prefix}: {exc}, response={response}") from exc

    def _strip_json_fence(self, text: str) -> str:
        """Remove markdown code fences when the model wraps JSON in them."""
        if "```json" in text:
            return text.split("```json", 1)[1].split("```", 1)[0]
        if "```" in text:
            return text.split("```", 1)[1].split("```", 1)[0]
        return text

    def _response_tokens_used(self, response: Any) -> int:
        """Best-effort token usage extraction across provider payload shapes."""
        try:
            usage = getattr(response, "usage", None)
            if not usage:
                return 0
            return getattr(usage, "total_tokens", 0) or (
                getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
            )
        except Exception:
            return 0

    def _parse_json_response(self, response: Any, error_prefix: str) -> Dict[str, Any]:
        """Extract text, strip optional fences, and decode JSON."""
        response_text = self._extract_text_from_response(response, error_prefix)
        return json.loads(self._strip_json_fence(response_text))

    def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int) -> tuple[Any, int]:
        """Issue a single LLM request and return the raw response plus elapsed milliseconds."""
        start_time = time.time()
        response = self.client.messages.create(
            model="MiniMax-M2.7",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        duration_ms = int((time.time() - start_time) * 1000)
        return response, duration_ms

    def _raise_planner_error(self, prefix: str, error: Exception) -> None:
        """Raise a user-facing planner exception with a consistent message format."""
        raise Exception(f"{prefix}: {error}") from error

    def _summarize_plan_parts(self, plan: Optional[UnifiedPlan]) -> str:
        """Return a compact bullet list of current ensemble parts for prompt context."""
        if not plan or not plan.ensemble or not plan.ensemble.parts:
            return "（暂无）"
        return "\n".join(
            f"- {part.id}: {part.instrument} ({part.role})"
            for part in plan.ensemble.parts
        )

    def _build_revision_analysis_prompt(self, user_message: str, current_plan: UnifiedPlan) -> str:
        """Build the user prompt used to classify revision-vs-regenerate intent."""
        current_parts_str = self._summarize_plan_parts(current_plan)
        return f"""## 用户最新消息
{user_message}

## 当前编曲方案
现有声部：
{current_parts_str}

请判断用户的意图是全新创作还是基于现有方案修改。
"""

    def _build_add_part_prompt(self, existing_parts_str: str, user_instruction: str) -> str:
        """Build the prompt for additive revisions."""
        add_part_prompt = """你是一位顶级的乐队编曲大师。用户的编曲方案已经有一个基础，现在需要**在现有基础上添加新声部**。

## 现有方案
现有声部：
{existing_parts_str}

## 用户的新需求
{user_instruction}

## 你的任务
在现有方案基础上，添加用户要求的新声部。
- **保留所有现有声部，不要删除或修改它们**
- 只添加新声部
- 确保新声部与现有方案和谐搭配
- 注意 channel 不能冲突（melody 用 channel 0）

## 重要
1. 只输出**完整的** UnifiedPlan JSON，包含**所有声部**（原有的 + 新增的）
2. 每个声部都必须有 id, name, role, instrument, midi, template_name, template_params
3. **不要省略任何字段**

请直接输出 JSON，不要有其他文字。
"""
        return add_part_prompt.format(existing_parts_str=existing_parts_str, user_instruction=user_instruction)

    def _build_modify_part_prompt(self, base_plan: UnifiedPlan, target_part_id: str, user_instruction: str) -> str:
        """Build the prompt for single-part modifications."""
        modify_part_prompt = """你是一位顶级的乐队编曲大师。用户的编曲方案中有一个声部需要修改。

## 现有方案
{existing_plan_json}

## 目标声部
需要修改的声部 ID: {target_part_id}

## 用户的新需求
{user_instruction}

## 你的任务
根据用户的新需求，修改指定声部的配置（如 template_name、template_params、role 等）。
- **保留所有其他声部不变**
- 只修改 target_part_id 对应的声部
- 确保修改后的配置合理可行

## 重要
1. 只输出**完整的** UnifiedPlan JSON，包含**所有声部**
2. 每个声部都必须有 id, name, role, instrument, midi, template_name, template_params
3. **不要省略任何字段**

请直接输出 JSON，不要有其他文字。
"""
        return modify_part_prompt.format(
            existing_plan_json=json.dumps(base_plan.model_dump(), indent=2, ensure_ascii=False),
            target_part_id=target_part_id,
            user_instruction=user_instruction,
        )

    def _normalize_message_for_matching(self, user_message: str) -> str:
        """Normalize user text for coarse part-name matching heuristics."""
        lowered = user_message.lower()
        lowered = lowered.replace("_", " ").replace("-", " ")
        return re.sub(r"\s+", " ", lowered)

    def _instrument_aliases(self, instrument: str) -> List[str]:
        """Return common English/Chinese aliases for instrument matching."""
        alias_map = {
            "piano": ["钢琴"],
            "violin": ["小提琴"],
            "viola": ["中提琴"],
            "cello": ["大提琴"],
            "double_bass": ["低音提琴", "贝斯"],
            "flute": ["长笛", "笛子"],
            "oboe": ["双簧管"],
            "clarinet": ["单簧管", "黑管"],
            "bassoon": ["巴松"],
            "horn": ["圆号"],
            "trumpet": ["小号"],
            "trombone": ["长号"],
            "tuba": ["大号"],
            "timpani": ["定音鼓"],
        }
        return [instrument.lower(), *alias_map.get(instrument.lower(), [])]

    def _ordinal_aliases_for_part(self, part: PartSpec) -> List[str]:
        """Return ordinal aliases like '第一小提琴' for multi-part instruments."""
        aliases: List[str] = []
        instrument_aliases = self._instrument_aliases(part.instrument)
        id_lower = part.id.lower()
        name_lower = part.name.lower()

        ordinal_map = {
            "1": ["第一", "一", "1"],
            "2": ["第二", "二", "2"],
            "3": ["第三", "三", "3"],
            "4": ["第四", "四", "4"],
        }

        ordinal_key = None
        for key in ordinal_map:
            if id_lower.endswith(key) or f" {key}" in name_lower:
                ordinal_key = key
                break

        roman_ordinals = {
            " i": "1",
            " ii": "2",
            " iii": "3",
            " iv": "4",
        }
        if ordinal_key is None:
            for marker, key in roman_ordinals.items():
                if marker in name_lower:
                    ordinal_key = key
                    break

        if ordinal_key is None:
            return aliases

        for ordinal_alias in ordinal_map[ordinal_key]:
            for instrument_alias in instrument_aliases:
                if instrument_alias.isascii():
                    continue
                aliases.append(f"{ordinal_alias}{instrument_alias}")
                aliases.append(f"{instrument_alias}{ordinal_alias}")

        return aliases

    def _part_aliases(self, part: PartSpec) -> List[str]:
        """Return coarse aliases used to infer target parts from user language."""
        aliases = [part.id.lower(), part.name.lower()]
        aliases.extend(self._instrument_aliases(part.instrument))
        aliases.extend(self._ordinal_aliases_for_part(part))
        return list(dict.fromkeys(alias for alias in aliases if alias))

    def _infer_candidate_target_part_ids(
        self,
        user_message: str,
        current_plan: UnifiedPlan,
    ) -> List[str]:
        """Return candidate target part ids ordered by matching confidence."""
        normalized_message = self._normalize_message_for_matching(user_message)
        parts = current_plan.ensemble.parts if current_plan.ensemble else []

        def ordered_unique(matches: List[str]) -> List[str]:
            return list(dict.fromkeys(matches))

        exact_matches = [
            part.id
            for part in parts
            if part.id.lower() in normalized_message or part.name.lower() in normalized_message
        ]
        if exact_matches:
            return ordered_unique(exact_matches)

        ordinal_matches = [
            part.id
            for part in parts
            if any(alias in normalized_message for alias in self._ordinal_aliases_for_part(part))
        ]
        if ordinal_matches:
            return ordered_unique(ordinal_matches)

        instrument_matches = [
            part.id
            for part in parts
            if any(alias in normalized_message for alias in self._instrument_aliases(part.instrument))
        ]
        return ordered_unique(instrument_matches)

    def _infer_revision_target_part_id(
        self,
        user_message: str,
        current_plan: UnifiedPlan,
    ) -> Optional[str]:
        """Infer the most likely target part from the user message when the model omits it."""
        candidate_ids = self._infer_candidate_target_part_ids(user_message, current_plan)
        if len(candidate_ids) == 1:
            return candidate_ids[0]
        return None

    def _message_revision_signals(self, user_message: str) -> Dict[str, bool]:
        """Detect coarse revision-action signals from a user message."""
        normalized_message = self._normalize_message_for_matching(user_message)
        add_keywords = ["加", "添加", "增加", "添", "再来一个", "加上", "换成"]
        remove_keywords = ["删", "删除", "去掉", "移除", "不要", "拿掉"]
        modify_keywords = ["改", "修改", "更", "调整", "弱一点", "强一点", "复杂", "简单", "密一点", "写密", "写得更密", "柔和一点", "亮一点"]

        return {
            "add": any(keyword in normalized_message for keyword in add_keywords),
            "remove": any(keyword in normalized_message for keyword in remove_keywords),
            "modify": any(keyword in normalized_message for keyword in modify_keywords),
        }

    def _has_mixed_revision_signals(self, user_message: str) -> bool:
        """Return True when a message appears to request multiple revision actions at once."""
        signals = self._message_revision_signals(user_message)
        return sum(1 for active in signals.values() if active) > 1

    def _infer_revision_type_from_message(self, user_message: str) -> Optional[str]:
        """Fallback classifier for revision type when the model response is unavailable."""
        signals = self._message_revision_signals(user_message)
        if signals["add"]:
            return "add"
        if signals["remove"]:
            return "remove"
        if signals["modify"]:
            return "modify"
        return None

    def _normalize_revision_intent(
        self,
        result_dict: Dict[str, Any],
        user_message: str,
        current_plan: UnifiedPlan,
    ) -> RevisionIntent:
        """Coerce raw model output into a safer RevisionIntent contract."""
        is_revision = bool(result_dict.get("is_revision", False))
        revision_type = result_dict.get("revision_type")
        if revision_type not in {"add", "remove", "modify"}:
            revision_type = None

        target_part_id = result_dict.get("target_part_id")
        inferred_target_candidates = (
            self._infer_candidate_target_part_ids(user_message, current_plan)
            if revision_type in {"remove", "modify"} or is_revision
            else []
        )
        if revision_type in {"remove", "modify"} and not target_part_id:
            target_part_id = self._infer_revision_target_part_id(user_message, current_plan)

        if revision_type == "add":
            target_part_id = None

        if is_revision and revision_type is None:
            revision_type = self._infer_revision_type_from_message(user_message)

        if is_revision and self._has_mixed_revision_signals(user_message):
            is_revision = False
            revision_type = None
            target_part_id = None

        if is_revision and revision_type in {"remove", "modify"} and len(inferred_target_candidates) > 1:
            is_revision = False
            revision_type = None
            target_part_id = None

        if is_revision and revision_type in {"remove", "modify"} and not target_part_id:
            # Missing target means the safest action is to fall back to a fresh generation.
            is_revision = False
            revision_type = None

        return RevisionIntent(
            is_revision=is_revision,
            revision_type=revision_type,
            target_part_id=target_part_id,
            instruction=result_dict.get("instruction", user_message),
        )

    REVISION_ANALYSIS_PROMPT = """你是一位专业的音乐编曲顾问。你的任务是根据用户的最新消息和当前编曲方案，判断用户是想要：

1. **全新创作**：用户要求从头开始编一个完全不同的方案（如"我想换一个古典交响乐版本"）
2. **基于现有方案修改**：用户想在当前方案基础上进行增量修改（如"加一个钢琴"、"把提琴部分改得更复杂"）

## 判断规则

**全新创作的信号**：
- 用户明确说"重新"、"换一个"、"不要这个了"、"从头来"
- 用户要求的风格/规模与当前方案完全不同
- 用户上传了新的 MIDI 文件并要求重新编曲

**基于现有方案修改的信号**：
- 用户提到"加..."、"添..."、"再来一个..."
- 用户说"把...改..."、"...更...一些"
- 用户说"在基础上..."、"继续..."、"加上..."
- 用户只是调整参数（如"钢琴再复杂些"）

## 输出格式

请直接输出 JSON，不要有任何解释文字：

```json
{
  "is_revision": true/false,
  "revision_type": "add"/"remove"/"modify"/null,
  "target_part_id": "具体声部ID或null",
  "instruction": "用一句话描述用户的修改要求"
}
```

- 如果 is_revision=false，revision_type 和 target_part_id 都设为 null
- 如果是 add，说明要新增什么声部
- 如果是 remove/modify，说明要操作哪个现有声部
"""

    def analyze_revision_intent(
        self,
        user_message: str,
        current_plan: UnifiedPlan
    ) -> RevisionIntent:
        """
        分析用户消息，判断是全新创作还是基于现有方案的修改

        Args:
            user_message: 用户发送的最新消息
            current_plan: 当前最新的编曲方案

        Returns:
            RevisionIntent：包含是否为修改请求以及修改类型
        """
        prompt = self._build_revision_analysis_prompt(user_message, current_plan)

        try:
            response, duration_ms = self._call_llm(self.REVISION_ANALYSIS_PROMPT, prompt, 1024)

            result_dict = self._parse_json_response(response, "Failed to parse revision analysis response")

            return self._normalize_revision_intent(result_dict, user_message, current_plan)

        except Exception as e:
            duration_ms = 0

            # 如果分析失败，默认认为是全新创作（保守策略）
            # 或者可以根据消息内容简单判断
            simple_keywords = ["重新", "换一个", "不要这个", "从头", "新做一个", "另做一个"]
            is_likely_revision = not any(kw in user_message for kw in simple_keywords)
            inferred_type = self._infer_revision_type_from_message(user_message) if is_likely_revision else None
            inferred_target_candidates = (
                self._infer_candidate_target_part_ids(user_message, current_plan)
                if inferred_type in {"remove", "modify"}
                else []
            )
            inferred_target = (
                inferred_target_candidates[0]
                if len(inferred_target_candidates) == 1
                else None
            )

            if is_likely_revision and self._has_mixed_revision_signals(user_message):
                is_likely_revision = False
                inferred_type = None
                inferred_target = None

            if is_likely_revision and inferred_type in {"remove", "modify"} and len(inferred_target_candidates) > 1:
                is_likely_revision = False
                inferred_type = None
                inferred_target = None

            if is_likely_revision and inferred_type in {"remove", "modify"} and not inferred_target:
                is_likely_revision = False
                inferred_type = None

            return RevisionIntent(
                is_revision=is_likely_revision,
                revision_type=inferred_type,
                target_part_id=inferred_target,
                instruction=user_message,
            )

    def apply_revision_for_add(
        self,
        base_plan: UnifiedPlan,
        user_instruction: str,
        existing_parts_str: str,
        analyze_result=None
    ) -> UnifiedPlan:
        """
        新增声部：根据用户指令在现有方案基础上添加新声部

        Args:
            base_plan: 现有编曲方案
            user_instruction: 用户指令（如"加一个钢琴"）
            existing_parts_str: 现有声部的描述字符串
            analyze_result: MIDI 分析结果

        Returns:
            新的 UnifiedPlan
        """
        prompt = self._build_add_part_prompt(existing_parts_str, user_instruction)

        try:
            response, duration_ms = self._call_llm(self.SYSTEM_PROMPT, prompt, 8192)

            plan_dict = self._parse_json_response(response, "Failed to parse add-part response")

            # 验证并补充必要字段
            if analyze_result:
                plan_dict = normalize_plan(plan_dict, analyze_result)
            else:
                plan_dict = normalize_plan(plan_dict, None)

            return UnifiedPlan(**plan_dict)

        except Exception as e:
            self._raise_planner_error("LLM 添加声部失败", e)

    def apply_revision_for_modify(
        self,
        base_plan: UnifiedPlan,
        target_part_id: str,
        user_instruction: str,
        analyze_result=None
    ) -> UnifiedPlan:
        """
        修改声部：根据用户指令修改指定声部的配置

        Args:
            base_plan: 现有编曲方案
            target_part_id: 要修改的声部 ID
            user_instruction: 用户指令（如"把钢琴部分改得更复杂"）
            analyze_result: MIDI 分析结果

        Returns:
            新的 UnifiedPlan
        """
        prompt = self._build_modify_part_prompt(base_plan, target_part_id, user_instruction)

        try:
            response, duration_ms = self._call_llm(self.SYSTEM_PROMPT, prompt, 8192)

            plan_dict = self._parse_json_response(response, "Failed to parse modify-part response")

            # 验证并补充必要字段
            if analyze_result:
                plan_dict = normalize_plan(plan_dict, analyze_result)
            else:
                plan_dict = normalize_plan(plan_dict, None)

            return UnifiedPlan(**plan_dict)

        except Exception as e:
            self._raise_planner_error("LLM 修改声部失败", e)

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

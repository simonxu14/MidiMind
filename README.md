# MidiMind

**AI 驱动的 MIDI 编曲助手** - 将简单旋律改编成专业乐队总谱

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 最近更新 (2026-03-29)

### P1 修复（AnyGen 评估反馈）

| 问题 | 修复 | 文件 |
|------|------|------|
| AutoFixer channel key 类型 bug | 优先 int key 查找，再 str key，最后 fallback | `auto_fixer.py` |
| 打击乐参与声部交叉修复 | `fix_voice_crossing` 跳过 channel 9 (GM percussion) | `auto_fixer.py` |
| 旋律 onset 避让过弱 | 升级为三种策略：scale_velocity / delay / drop | `orchestrate_executor.py`, `plan_schema.py` |
| flute min_rest_beats=1 太严格 | 降低到 0.5 以适应连续旋律 | `flute_countermelody.py` |
| Plan guards/arrangement=None | Planner 显式输出默认值 | `llm_planner.py` |
| template_per_measure 为空 | 补齐所有模板路径的统计 | `orchestrate_executor.py` |
| percussion_hits=0 | 同时统计 auto 和显式 timpani/triangle | `orchestrate_executor.py` |

### 新增功能

| 功能 | 说明 | 文件 |
|------|------|------|
| Meter Grid API | 支持非 4/4 拍号（6/8, 9/8 等） | `timebase.py` |
| OrchestrateExecutor 执行结果保存 | stats/validator_result/arrangement_report 写入 conversation | `orchestrate_executor.py`, `conversation.py` |
| GuardsConfig.onset_avoidance_action | 三种避让策略配置 | `plan_schema.py` |
| Arrangement.onset_avoidance_action | arrangement 级别的避让策略 | `plan_schema.py` |

### 详细变更说明

#### 1. AutoFixer 音域映射修复

```python
# 修复前：只用 str key 查找
range_min, range_max = instrument_ranges.get(str(channel), (21, 108))

# 修复后：优先 int，再 str，最后 fallback
if channel in instrument_ranges:
    range_min, range_max = instrument_ranges[channel]
elif str(channel) in instrument_ranges:
    range_min, range_max = instrument_ranges[str(channel)]
else:
    range_min, range_max = (21, 108)
```

#### 2. Onset Avoidance 三种策略

```python
# plan_schema.py - GuardsConfig
onset_avoidance_action: Literal["scale_velocity", "delay", "drop"] = "scale_velocity"

# orchestrate_executor.py - 策略执行
if action == 'drop':
    continue  # 跳过该音符
elif action == 'delay':
    start += random.randint(15, 30)  # 延迟 15-30 ticks
    end += delay_ticks
else:  # scale_velocity
    velocity = int(velocity * reduce_ratio)
```

#### 3. Meter Grid API（支持非 4/4 拍号）

```python
# timebase.py
def meter_grid(ticks_per_beat, time_signature, kind, measure_start, measure_count, clip_to_measure):
    # kind = "quarter" | "eighth" | "pulse"
    # 6/8 等复合拍号自动使用 pulse 网格

# flute_countermelody.py 使用示例
if n % 3 == 0 and d == 8:
    grid_kind = "pulse"  # 6/8, 9/8, 12/8
else:
    grid_kind = "quarter"  # 4/4, 3/4, 2/4
```

#### 4. 打击乐语义化

```python
# timpani_rhythm.py
pitch_min, pitch_max = 45, 53  # 定音鼓标准音域

# accent_cymbal.py
channel = 9  # GM percussion channel
triangle_note = 81  # GM triangle
velocity_base = 35  # 降低力度
```

#### 5. OrchestrateExecutor Stats 新增字段

```python
self._report_stats = {
    "onset_avoidance_hits": 0,
    "onset_scale_velocity_hits": 0,  # 新增
    "onset_delay_hits": 0,          # 新增
    "onset_drop_hits": 0,           # 新增
    "velocity_cap_hits": 0,
    "percussion_hits": {"timpani": 0, "triangle": 0},
    # ...
}
```

---

## 功能特性

### 核心能力
- **自然语言编曲**: 用自然语言描述你的编曲需求
- **智能乐队编排**: 自动生成钢琴、弦乐、木管、铜管等声部
- **旋律原样保留**: 主旋律逐音符复制，确保与原曲一致
- **多轮对话优化**: 通过反馈迭代优化编曲结果
- **风格适应**: 支持流行、古典、爵士、电影配乐等多种风格

### 支持场景
| 场景 | 说明 |
|------|------|
| 乐队编曲 | 4人弦乐四重奏 → 15人交响乐团 |
| 难度调整 | 简化版 / 复杂化版 |
| 风格转换 | 流行 → 古典、爵士风格改编 |
| 乐器替换 | 钢琴伴奏 → 吉他/弦乐 |

---

## 快速开始

### 1. 安装依赖

```bash
cd /opt/midimind
python3 -m venv venv
source venv/bin/activate
pip install mido pydantic fastapi uvicorn python-multipart anthropic
```

### 2. 启动服务

```bash
export ANTHROPIC_API_KEY="your_api_key"
export ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"
export PYTHONPATH=/opt/midimind/src

cd /opt/midimind/src
python3 -m arranger.api --host 0.0.0.0 --port 8000
```

### 3. 访问 Web 界面

```
http://your_server_ip:8000
```

---

## API 使用

### HTTP API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/analyze_midi` | POST | 分析 MIDI 结构 |
| `/plan` | POST | 生成编曲方案 |
| `/arrange` | POST | 执行编曲 |
| `/conversation` | POST | 创建多轮会话 |
| `/conversation/{id}/message` | POST | 发送消息 |
| `/conversation/{id}/feedback` | POST | 提交反馈 |

### 示例

```bash
# 分析 MIDI
curl -X POST http://localhost:8000/analyze_midi \
  -F "file=@song.mid"

# 编曲
curl -X POST http://localhost:8000/plan \
  -F "file=@song.mid" \
  -F "intent=为这首歌编一个钢琴伴奏+弦乐四重奏"

# 执行编曲
curl -X POST http://localhost:8000/arrange \
  -F "file=@song.mid" \
  -F "plan_json=@plan.json"
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                         用户界面                              │
│                    (Web / API / Coze Bot)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLM Planner                            │
│  - 理解用户意图                                            │
│  - 生成编曲方案 (UnifiedPlan JSON)                         │
│  - 乐器配置、声部角色、模板参数                              │
│  - 显式输出 guards 和 arrangement（避免 None）              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    OrchestrateExecutor                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ 模板系统    │  │ 和声分析    │  │ 旋律锁定    │       │
│  │ 18个模板    │  │ ChordInfo   │  │ NoteEvent   │       │
│  │ + MeterGrid │  │ per_measure │  │ 原样复制    │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│  ┌─────────────────────────────────────────────────┐       │
│  │ Guard 系统（onset_avoidance / velocity_cap /    │       │
│  │          register_separation）                  │       │
│  └─────────────────────────────────────────────────┘       │
│  ┌─────────────────────────────────────────────────┐       │
│  │ AutoFixer（fix_octave_jumps / fix_voice_crossing /      │
│  │          fix_parallel_fifths / fix_out_of_range）│       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Validator                             │
│  硬约束: melody_identical | ticks_match | instrumentation │
│  软约束: harmony_valid (自动修复)                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    输出: arranged.mid
```

---

## 核心模块

### plan_schema.py - 数据模型

| 类 | 说明 |
|---|---|
| `UnifiedPlan` | 完整编曲方案，包含 ensemble、constraints、harmony_context、arrangement |
| `EnsembleConfig` | 乐队配置（名称、规模、声部列表） |
| `PartSpec` | 单个声部规格（ID、角色、乐器、MIDI通道、模板） |
| `Constraints` | 约束配置（旋律锁定、总时长、护栏） |
| `GuardsConfig` | 护栏配置（velocity_caps、onset_window_ticks、onset_avoidance_action、register_separation） |
| `ArrangementConfig` | 编曲配置（reduce_ratio、onset_avoidance_action、velocity_caps_by_mode、percussion） |
| `HarmonyContext` | 和声分析配置（方法、粒度） |

### orchestrate_executor.py - 主执行器

```
execute(input_midi, melody_track_index)
    │
    ├─1─ 解析 MIDI ─────────────────→ tracks[]
    │
    ├─2─ 锁定主旋律 ───────────────→ locked_melody_notes[]
    │
    ├─3─ 分析和声 ─────────────────→ chord_per_measure{}
    │
    ├─4─ 构建 ArrangementContext ──→ context
    │       (包含 time_signature_num, time_signature_den, meter_grid)
    │
    ├─5─ 生成各声部
    │       │
    │       ├─ melody: 原样复制
    │       ├─ accompaniment: DenseAccompaniment
    │       ├─ bass: CelloPedalRoot
    │       ├─ inner_voice: ViolaInner16ths
    │       └─ counter_melody: FluteCountermelody (min_rest_beats=0.5)
    │
    ├─6─ Guard 处理
    │       ├─ velocity_cap: min(velocity, max_velocity)
    │       ├─ onset_avoidance: scale/delay/drop
    │       └─ register_separation: octave_shift / chord_tone / skip
    │
    ├─7─ AutoFixer 修复
    │       ├─ fix_out_of_range: 按 instrument_ranges (int→str 查找)
    │       ├─ fix_octave_jumps: threshold=19 semitones
    │       ├─ fix_voice_crossing: 跳过 percussion channel 9
    │       └─ fix_parallel_fifths: 替换为经过音
    │
    └─8─ 输出 tracks_data[]
```

### validator.py - 验证器

**硬约束（必须通过）**:
- `melody_identical` - 主旋律逐事件一致
- `total_ticks_identical` - 总时长一致（±480 ticks 容差）
- `instrumentation_ok` - 编制符合 Plan
- `midi_valid` - MIDI 格式有效

**软约束（警告 + AutoFixer）**:
- `harmony_valid` - 无平行五八度、无声部交叉
- `instrument_range_valid` - 音符在乐器音域内

### auto_fixer.py - 自动修复

| 方法 | 说明 |
|------|------|
| `fix_out_of_range` | 音高移到乐器音域内（int/str key 双查找） |
| `fix_octave_jumps` | 超过 19 semitones 的跳跃改为级进 |
| `fix_voice_crossing` | 修复声部交叉（跳过 channel 9 percussion） |
| `fix_parallel_fifths` | 修复平行五八度（替换为经过音） |
| `apply_velocity_caps_by_mode` | 按模式力度上限调整 |
| `avoid_melody_onsets` | 旋律 onset 窗口内降低伴奏力度 |
| `apply_register_separation` | 伴奏与旋律音区分离（octave_shift → chord_tone → skip） |

### timebase.py - 拍号支持

| 函数 | 说明 |
|------|------|
| `beats_per_measure(time_signature)` | 返回每小节拍数（如 6/8 → 3.0） |
| `meter_grid(ticks_per_beat, time_signature, kind, ...)` | 返回拍网格位置 |

**Grid Kind 映射**：
- `quarter`: 4/4, 3/4, 2/4 → 每拍一个位置
- `pulse`: 6/8, 9/8, 12/8 → 每小节 3/6/12 个位置
- `eighth`: 任意 → 每八分音符一个位置

### templates/ - 模板系统

| 类别 | 模板 | 说明 |
|---|---|---|
| **Piano** | `dense_accompaniment` | 阿尔贝蒂低音，高密度织体 |
| | `arpeggio` | 分解和弦 |
| | `chord_block` | 柱式和弦 |
| | `broken_8ths` | 8分音符碎裂 |
| **Strings** | `cello_pedal_root` | 持续根音 |
| | `viola_inner_16ths` | 16分音符内声部 |
| | `violin_cantabile` | 抒情旋律 |
| **Winds** | `flute_countermelody` | 长笛副旋律（min_rest_beats=0.5） |
| | `clarinet_sustain` | 单簧管持续 |
| | `oboe_color_tone` | 双簧管色彩音 |
| **Brass** | `root_pad` | 圆号根音垫底 |
| | `trumpet_fanfare` | 小号号角性 |
| **Percussion** | `timpani_rhythm` | 定音鼓（pitch 45-53, GM channel） |
| | `accent_cymbal` | 三角铁（note 81, GM channel 9） |

---

## 项目结构

```
midimind/
├── src/arranger/
│   ├── api.py              # FastAPI 服务入口
│   ├── cli.py              # 命令行工具
│   ├── plan_schema.py      # Pydantic 数据模型（UnifiedPlan, Guards, Arrangement）
│   ├── orchestrate_executor.py  # 主执行器（Guard + AutoFixer 集成）
│   ├── simplify_executor.py    # 难度降低
│   ├── complexify_executor.py # 难度提升
│   ├── creative_executor.py    # 创意重构
│   ├── validator.py            # 验证器
│   ├── auto_fixer.py           # 自动修复（音域/跳跃/声部交叉/五八度）
│   ├── harmony_validator.py    # 和声验证
│   ├── harmony_analyzer.py      # 和声分析
│   ├── midi_io.py             # MIDI 读写
│   ├── analyze.py              # MIDI 分析
│   ├── llm_planner.py          # LLM 规划器（显式 guards/arrangement）
│   ├── conversation.py         # 多轮会话管理（+执行结果保存）
│   ├── timebase.py             # 拍号支持（meter_grid）
│   ├── tracer.py               # 执行追踪
│   └── templates/               # 模板系统
│       ├── registry.py
│       ├── piano/
│       ├── strings/
│       ├── winds/  (flute_countermelody: min_rest_beats=0.5)
│       ├── brass/
│       └── percussion/ (GM channel 9, timpani 45-53, triangle 81)
├── static/
│   └── index.html      # Web UI
├── tests/
│   └── ...
├── pyproject.toml
└── README.md
```

---

## 部署

### 系统要求
- Python 3.9+
- 4GB+ RAM
- 公网访问（用于调用 LLM API）

### systemd 服务配置

创建 `/etc/systemd/system/midimind.service`:

```ini
[Unit]
Description=MidiMind MIDI Arrangement Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/midimind
ExecStart=/opt/midimind/venv/bin/python3 -m arranger.api --host 0.0.0.0 --port 8000
Environment="ANTHROPIC_API_KEY=your_key"
Environment="ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic"
Environment="PYTHHPATH=/opt/midimind/src"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable midimind
sudo systemctl start midimind
```

### Nginx 反向代理（可选 HTTPS）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 与 Coze 集成

### Coze 插件配置

1. 创建 Coze 插件，添加以下端点：
   - `POST /analyze_midi`
   - `POST /plan`
   - `POST /arrange`

2. 在 Coze Bot 中添加工具

3. 配置 API 认证（可选）

### Bot 提示词示例

```
你是一个专业的编曲助手。用户上传 MIDI 文件后，你可以：
1. 分析 MIDI 的结构（轨道、速度、拍号）
2. 根据用户需求生成编曲方案
3. 执行编曲并返回结果

用户可以说："帮我把这首曲子编成弦乐四重奏"
```

---

## 常见问题

**Q: 编曲后的音色听起来不对？**
A: MIDI 是音色无关的，输出是 General MIDI 格式。在 DAW 中加载合适的音色库即可。

**Q: 如何调整编曲密度？**
A: 在 intent 中指定 `density: 0.9`（高密度）或 `density: 0.6`（低密度）

**Q: 主旋律丢失了？**
A: 检查 `source_track_ref` 是否指向正确的旋律轨道

**Q: 打击乐音高不对？**
A: 确保使用 GM percussion channel 9，timpani pitch 限制在 45-53，triangle 使用 note 81。

---

## 编曲架构设计（参考 AnyGen 方案）

### 核心架构

```
LLM (Planner) → Plan JSON → Executor (MIDI事件级操作) → Validator → 输出
```

LLM 的作用是"编曲导演 + 自动化工程师"，负责任规划策略和写程序；实际的音符修改是通过确定性的 Python 脚本对 MIDI 事件进行增删改。

### 段落模式系统

按 8 小节分段，统计每段旋律特征：

| 模式 | 条件 | 特点 |
|------|------|------|
| A (透明) | av < 85, nn ≤ 80, ap ≤ 72 | 钢琴轻织体，圆号长音，木管克制 |
| B (流动) | nn > 80 | 钢琴 alberti，低音行进，内声部更密 |
| C (明亮) | ap > 72 | 木管模仿动机，音区换位，色彩变化 |
| D (高潮) | av ≥ 85 | 全员更密，力度略增，但永远不盖旋律 |

**判定变量：**
- `nn`: 8小节内主旋律 note_on 数量（note_density）
- `av`: 平均力度（avg_velocity）
- `ap`: 平均音高（avg_pitch）

### 和声上下文（Harmony Context）

从伴奏轨抽取每小节的音高集合，推导 triad-ish 和弦骨架：

```python
def choose_triadish(pitches):
    if not pitches: return None
    P = sorted(set(pitches))
    root = P[0]  # 最低音当根音
    # third: 与root距离最接近3或4度的音
    third = argmin_{p in P} distance(|(p-root) mod 12|, {3, 4})
    # fifth: 与root距离最接近7度的音
    fifth = argmin_{p in P} distance(|(p-root) mod 12|, {7})
    return (root, third, fifth)
```

### 模板系统（按段落模式选择）

**钢琴模板池：**
```json
{
  "A": ["broken_8ths", "sustain_arpeggio_sparse"],
  "B": ["alberti_8ths", "offbeat_dyads"],
  "C": ["register_shift", "arpeggio_16ths"],
  "D": ["tremolo_like", "octave_support"]
}
```

**钢琴模板实现（核心节奏型）：**

1. **alberti_8ths**: `root+12, fifth+12, third+12, fifth+12` 循环
2. **arpeggio_16ths**: `root+24, third+24, fifth+24, third+24` 循环
3. **offbeat_dyads**: 在 offbeat 位置放双音
4. **tremolo_like**: 重复根音 + 低八度支撑
5. **register_shift**: 前半小节低音区，后半小节高音区

**弦乐模板：**
- Viola: `inner_16ths` - 16分音符内声部滚动 `[third+12, fifth+12, root+24, fifth+12]`
- Cello: `bass_walk_8ths` - 8分低音行进 `[root-12, fifth-12, third-12, fifth-12]`

**木管模板：**
- `flute_countermelody`: 旋律空隙（≥0.5拍）处插入 triad-relative motifs
- Motif 形状: `[3, 5, 8, 5]`, `[4, 7, 12, 7]`, `[0, 4, 7, 4]` 等

### 护栏系统（Guards）

**1. onset_avoidance_action**（新增三种策略）
```python
# scale_velocity (default): 降力度
velocity = int(velocity * reduce_ratio)  # reduce_ratio=0.6

# delay: 延迟 15-30 ticks
start += random.randint(15, 30)
end += delay_ticks

# drop: 跳过该音符
continue
```

**2. register_separation**
- 以旋律为锚点：同一时刻伴奏与旋律距离 ≥ 5 半音
- 修复优先级：八度移动 → 换和弦音 → 跳过

**3. velocity_caps_by_mode**
```json
{
  "A": {"pf": 52, "va": 56, "vc": 62, "winds": 58, "hn": 56},
  "B": {"pf": 56, "va": 60, "vc": 66, "winds": 60, "hn": 58},
  "C": {"pf": 58, "va": 62, "vc": 70, "winds": 62, "hn": 60},
  "D": {"pf": 62, "va": 66, "vc": 74, "winds": 64, "hn": 62}
}
```

### CC 混音系统

| CC | 名称 | 作用 |
|----|------|------|
| CC7 | Channel Volume | 通道音量（全程固定） |
| CC11 | Expression | 表情（按段落动态） |
| CC91 | Reverb Send | 混响发送（空间感） |
| CC93 | Chorus Send | 合唱发送（微扩散） |

**CC11 按段落动态：**
```json
{
  "melody": {"A": 100, "B": 105, "C": 108, "D": 112},
  "others": {"A": 25, "D": 27}
}
```

### 打击乐策略

**定音鼓 (Timpani):**
- MIDI: GM percussion channel 9
- 音高: 45-53（固定为 root - 12）
- 触发：每8小节块末尾（第7小节第4拍附近）
- 力度：~35，时值：TPB/2

**三角铁 (Triangle):**
- MIDI: GM percussion channel 9, note 81
- 触发：下一块开始（下一块第1拍）
- 力度：~25-35，时值：TPB/8

### Humanize（可选）

默认关闭。只对伴奏启用，且用于音频渲染版本，不用于出谱版本：
- `timing_jitter_ticks`: ±10（正态分布，σ=5）
- `velocity_jitter`: ±3
- 同一和弦内所有音符用同一个 jitter

---

## Plan Schema（当前版本）

```json
{
  "schema_version": "1.0",
  "transform": {
    "type": "orchestration",
    "preserve_structure": true,
    "preserve_order": true
  },
  "ensemble": {
    "name": "custom_ensemble",
    "size": "medium",
    "target_size": 10,
    "parts": [...]
  },
  "harmony_context": {
    "method": "measure_pitchset_triadish",
    "granularity": "per_measure"
  },
  "constraints": {
    "lock_melody_events": {
      "enabled": true,
      "source_track_ref": "0",
      "source_track_selection_mode": "auto"
    },
    "keep_total_ticks": true,
    "guards": {
      "velocity_caps": {},
      "avoid_melody_onsets": true,
      "onset_window_ticks": 120,
      "onset_avoidance_action": "scale_velocity",
      "register_separation": true
    }
  },
  "arrangement": {
    "reduce_ratio": 0.6,
    "onset_avoidance_action": "scale_velocity",
    "register_separation": true,
    "min_semitones": 5,
    "velocity_caps_by_mode": {},
    "cc_by_mode": {},
    "humanize": {"enabled": false},
    "percussion": {"enabled": true, "phrase_block": 8, "density": 0.5}
  },
  "outputs": {
    "midi": {
      "enabled": true,
      "filename": "arranged.mid"
    }
  }
}
```

---

## License

MIT License

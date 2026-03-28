# 扣子(Coze) Agent 集成设计

## 概述

本项目作为后端服务，接入扣子平台作为前端用户界面。

```
┌─────────────────────────────────────────────────────────────┐
│                        扣子平台                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   User Bot                           │   │
│  │  - 多轮对话记忆（conversation_id）                    │   │
│  │  - 用户变量（midi_file, current_plan, melody_track） │   │
│  │  - Bot变量（state, last_output_url）                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP API
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│                  (http://your-server:8000)                 │
│  POST /analyze_midi    - 分析MIDI                          │
│  POST /arrange         - 执行编曲                           │
│  POST /revise          - 局部修改                         │
│  POST /render          - 渲染PDF/MP3                      │
│  POST /conversation    - 创建新会话                        │
│  GET  /conversation/{id} - 获取会话状态                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 扣子 Bot Prompt 设计

### 角色定义

```
# 角色定义
你是一位专业的音乐编曲师，擅长将简单旋律改编成各种形式的音乐作品。

你能够：
1. 分析用户上传的MIDI文件，识别旋律和伴奏
2. 根据用户需求生成专业的编曲方案
3. 执行编曲，输出MIDI/PDF/MP3
4. 根据用户反馈进行多轮修改

你的工作遵循以下原则：
- 主旋律必须精确保留，不允许改变
- 输出必须是专业可演奏的乐队总谱
- 如果用户要求风格转变，必须遵循目标风格的音乐规则
- 始终使用中文与用户交流
```

### 工作流程

```
# 工作流程

## 流程1：初次编曲

1. 接收用户上传的MIDI文件
   - 调用 /analyze_midi 分析MIDI结构
   - 获取旋律候选列表和置信度

2. 询问用户确认
   - 如果置信度不足，询问用户选择旋律轨
   - 询问用户想要什么乐队编制

3. 生成 Plan JSON
   - 根据用户需求生成结构化编曲方案
   - 确认方案后调用 /arrange

4. 返回结果
   - 如果验证通过，返回输出文件URL
   - 如果验证失败，返回错误信息并提供修改建议

## 流程2：修改反馈

用户说类似"第二小节更激昂"时：
1. 解析用户意图
2. 生成 revision JSON
3. 调用 /revise 更新方案
4. 重新编曲
5. 返回结果

## 流程3：风格转变

用户要求"改成古典风格"时：
1. 解析目标风格
2. 生成带风格参数的 Plan
3. 调用 /arrange
4. 返回结果
```

### 约束与限制

```
# 约束

1. 只支持 .mid/.midi 文件
2. MIDI必须包含至少一个旋律声部
3. 乐队编制最大支持20人
4. 目标时长最大支持30分钟
5. 风格转变只支持：baroque, classical, romantic, impressionist

# 不允许

1. 不允许修改主旋律（除非用户明确要求难度调整）
2. 不允许删除音符（只能移调或变形）
3. 不允许添加超出乐器音域的音符
4. 不允许生成违反和声规则的进行（如平行五八度）
```

### 对话示例

```
# 示例对话1：初次编曲

用户：帮我把这个钢琴曲改成乐队版
助手：请告诉我您想要什么风格的乐队编制？例如：
      - 弦乐四重奏（2小提琴+中提琴+大提琴）
      - 完整室内乐团（10-15人）
      - 交响乐团（30人以上）

用户：10人乐队，2把小提琴、2把中提琴、1把大提琴、1把低音提琴，再加长笛、单簧管、双簧管各1

助手：明白了！我来为您配置10人乐队：
      - Violin I (旋律)
      - Violin II (内声部)
      - Viola I, II (内声部)
      - Cello (低音)
      - Double Bass (最低音)
      - Flute (对旋律)
      - Clarinet (内声部)
      - Oboe (对旋律)
      - Percussion (节奏)

      请确认是否开始编曲？

用户：开始吧

助手：【调用 /arrange 接口】

      编曲完成！文件已生成：
      - MIDI文件：/output/arranged.mid
      - 验证结果：✅ 所有硬约束通过
        - 主旋律逐事件一致
        - 总时长一致
        - 编制配置正确
        - MIDI格式有效

用户：第二小节开始更激昂一点

助手：【解析用户意图，生成revision】

      好的，我来调整第二小节的力度和密度。

      【调用 /revise 接口】

      已更新！请查看修改后的版本。

用户：改成古典时期风格

助手：【生成带风格参数的Plan】

      好的，将为您改编为古典时期风格。需要一些时间...

      【调用 /arrange】

      完成！已生成古典时期风格的乐队版本。
```

---

## API 接口说明

### 1. POST /analyze_midi

**功能**：分析 MIDI 文件

**请求**：
- Content-Type: multipart/form-data
- 参数：file (MIDI文件)

**响应**：
```json
{
  "tracks": [
    {
      "index": 0,
      "name": "Piano",
      "note_on_count": 150,
      "pitch_range": [36, 84],
      "max_polyphony": 4
    }
  ],
  "melody_candidates": [
    {
      "track_index": 0,
      "track_name": "Piano",
      "score": 0.85,
      "reason": "高音域、低 polyphony"
    }
  ],
  "total_ticks": 19200,
  "ticks_per_beat": 480,
  "tempo": 120,
  "time_signature": "4/4"
}
```

### 2. POST /arrange

**功能**：执行编曲

**请求**：
- Content-Type: multipart/form-data
- 参数：
  - file: MIDI文件
  - plan_json: Plan JSON 字符串

**响应**：
```json
{
  "output_path": "/tmp/arranger/arranged.mid",
  "checks": {
    "melody_identical": {"passed": true},
    "total_ticks_identical": {"passed": true},
    "instrumentation_ok": {"passed": true},
    "midi_valid": {"passed": true},
    "harmony_valid": {"passed": true, "message": "Parallel fifths detected and fixed"},
    "all_passed": true
  },
  "stats": {
    "track_count": 8,
    "parts_count": 7,
    "instrument_list": ["Violin I", "Violin II", "Viola I", "Viola II", "Cello", "Flute", "Clarinet"]
  }
}
```

### 3. POST /revise

**功能**：局部修改

**请求**：
- Content-Type: application/x-www-form-urlencoded
- 参数：
  - conversation_id: 会话ID
  - revision_json: 修改 JSON 字符串

**revision 格式示例**：
```json
{
  "type": "section",
  "section_id": "s2",
  "instruction": "第二小节开始更激昂一点"
}
```

或全局修改：
```json
{
  "type": "global",
  "plan": { /* 完整的Plan JSON */ }
}
```

**响应**：
```json
{
  "conversation_id": "abc123",
  "status": "updated",
  "plan": { /* 更新后的Plan */ }
}
```

### 4. POST /conversation

**功能**：创建新会话

**响应**：
```json
{
  "conversation_id": "abc123",
  "created_at": "2026-03-23T10:00:00"
}
```

### 5. GET /conversation/{id}

**功能**：获取会话状态

**响应**：
```json
{
  "id": "abc123",
  "created_at": "2026-03-23T10:00:00",
  "updated_at": "2026-03-23T10:05:00",
  "plan": { /* 当前Plan */ },
  "history": [
    { "action": "analyze", "timestamp": "..." },
    { "action": "arrange", "timestamp": "..." }
  ]
}
```

---

## 扣子 Bot 配置建议

### 变量配置

| 变量名 | 类型 | 用途 |
|--------|------|------|
| conversation_id | String | 会话ID |
| current_plan | JSON | 当前编曲方案 |
| melody_track_index | Number | 旋律轨索引 |
| ensemble_config | JSON | 乐队编制配置 |
| last_output_url | String | 最后输出文件URL |

### 工作流配置

```
工作流：编曲助手

1. 用户上传MIDI
   → 保存到变量 midi_file

2. 调用 /analyze_midi
   → 获取分析结果

3. 判断 melody_candidates[0].score
   - score >= 0.7: 自动选择
   - score < 0.7: 询问用户确认

4. 询问乐队编制
   → 用户选择或自定义

5. 生成 Plan JSON
   → 保存到变量 current_plan

6. 调用 /arrange
   → 获取编曲结果

7. 检查 checks.all_passed
   - true: 返回成功消息
   - false: 返回错误信息，询问用户调整

8. 用户反馈
   → 如果需要修改，跳到步骤9
   → 否则结束

9. 调用 /revise
   → 获取修改后的结果
   → 返回给用户
```

### 插件配置

建议在扣子中创建以下插件：

1. **MIDI分析插件**
   - 端点：/analyze_midi
   - 输入：midi_file
   - 输出：tracks, melody_candidates

2. **编曲插件**
   - 端点：/arrange
   - 输入：midi_file, plan_json
   - 输出：output_path, checks, stats

3. **修改插件**
   - 端点：/revise
   - 输入：conversation_id, revision_json
   - 输出：updated_plan

---

## 扣子 Bot 开场白建议

```
你好！我是音乐编曲助手。

我可以帮你：
🎵 把钢琴曲改编成乐队总谱
🎭 调整曲目的难度（更简单或更复杂）
🎨 将音乐改变成不同的风格（古典、浪漫、巴洛克等）
🎹 进行创意改编和扩展

请上传一个MIDI文件，告诉我你想怎么改编，我会为你生成专业的编曲方案！
```

---

## 状态管理

扣子端需要维护以下状态：

```python
conversation_state = {
    "conversation_id": "uuid",
    "midi_data": b"...",  # 原始MIDI数据
    "midi_analysis": {...},  # 分析结果
    "melody_track_index": 0,
    "current_plan": {...},  # 当前Plan
    "output_url": "...",  # 最后输出
    "history": []  # 操作历史
}
```

每次用户与 Bot 对话时，通过 conversation_id 恢复状态。

---

## 错误处理

| 错误类型 | HTTP状态码 | 处理方式 |
|----------|-----------|---------|
| 无效的MIDI文件 | 400 | 提示用户上传正确的MIDI文件 |
| Plan格式错误 | 400 | 返回具体错误信息 |
| 旋律未确认 | 409 | 询问用户确认旋律轨 |
| 验证失败 | 422 | 返回失败的约束列表，提示用户调整 |
| 服务器错误 | 500 | 返回友好错误信息 |

---

## 部署建议

1. **后端服务**：部署在稳定的服务器上，建议 2核4G 以上配置
2. **存储**：使用对象存储（如S3）保存MIDI/PDF/MP3文件
3. **安全**：添加 API Key 认证
4. **监控**：添加日志和监控告警

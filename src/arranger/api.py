"""
FastAPI 服务

提供 HTTP API 接口：
- GET / - Web 演示界面
- POST /analyze_midi - 分析MIDI
- POST /arrange - 执行编曲
- POST /revise - 局部修改
- POST /render - 渲染PDF/MP3
- GET /conversation/{id} - 获取状态
- POST /conversation - 创建新会话
- POST /conversation/{id}/message - 发送消息
- GET /conversation/{id}/trace - 获取追踪日志
"""

from __future__ import annotations

import logging
import os
import uuid
import json
import threading

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import asdict

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .plan_schema import (
    UnifiedPlan,
    AnalyzeResponse,
    TrackStats as PlanTrackStats,
    MelodyCandidate,
    ArrangeResponse,
    CheckResult,
    ArrangeStats,
)
from .analyze import MidiAnalysisService
from .orchestrate_executor import OrchestrateExecutor
from .simplify_executor import SimplifyExecutor
from .complexify_executor import ComplexifyExecutor
from .creative_executor import CreativeExecutor
from .validator import Validator
from .midi_io import MidiWriter, MidiReader, MidiAnalyzer
from .llm_planner import LLMPlanner
from .conversation import conversation_manager
from .tracer import get_tracer
from .session_logger import session_logger, SessionLog


# ============ App Setup ============

app = FastAPI(
    title="MidiMind API",
    description="MidiMind - AI 驱动的 MIDI 编曲服务",
    version="0.2.0",
)

# 存储目录
STORAGE_DIR = Path("/tmp/midimind")
STORAGE_DIR.mkdir(exist_ok=True)

# 会话存储
conversations: Dict[str, Dict[str, Any]] = {}
conversation_lock = threading.Lock()


# ============ 请求/响应模型 ============

class AnalyzeRequest(BaseModel):
    """分析请求"""
    pass  # 使用 form data


class AnalyzeResponseData(BaseModel):
    """分析响应数据"""
    tracks: list
    melody_candidates: list
    total_ticks: int
    ticks_per_beat: int
    tempo: int
    time_signature: str


class ArrangeRequest(BaseModel):
    """编曲请求"""
    plan: dict


class ArrangeResponseData(BaseModel):
    """编曲响应数据"""
    output_path: str
    checks: dict
    stats: dict


class ReviseRequest(BaseModel):
    """修改请求"""
    revision: dict


# ============ API 端点 ============

@app.get("/")
async def root():
    """Web 演示界面"""
    static_path = Path(__file__).parent.parent.parent / "static" / "index.html"
    return FileResponse(str(static_path))


# 挂载静态文件目录
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


# 示例 MIDI 文件目录
SAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


@app.get("/samples")
async def list_samples():
    """列出可用的示例 MIDI 文件"""
    samples = []
    if SAMPLES_DIR.exists():
        for f in SAMPLES_DIR.glob("*.mid"):
            if f.stem not in ['simple_melody', 'piano_chords']:  # 排除测试文件
                samples.append({
                    "name": f.stem,
                    "filename": f.name,
                    "display_name": f.stem.replace("_", " ").replace("-", " "),
                })
        for f in SAMPLES_DIR.glob("*.midi"):
            samples.append({
                "name": f.stem,
                "filename": f.name,
                "display_name": f.stem.replace("_", " ").replace("-", " "),
            })
    return {"samples": samples}


@app.get("/samples/{filename}")
async def download_sample(filename: str):
    """下载示例 MIDI 文件"""
    file_path = SAMPLES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample not found")
    return FileResponse(file_path, filename=filename, media_type="audio/midi")


@app.post("/midi_duration")
async def get_midi_duration(
    file: UploadFile = File(...),
):
    """获取 MIDI 文件的时长（秒）"""
    if not file.filename.endswith(('.mid', '.midi')):
        raise HTTPException(status_code=400, detail="Only MIDI files supported")

    midi_data = await file.read()
    await file.seek(0)

    try:
        midi = MidiReader.read_midi(midi_data)
        analyzer = MidiAnalyzer(midi)
        analysis = analyzer.analyze()

        total_ticks = analysis.total_ticks
        ticks_per_beat = analysis.ticks_per_beat
        tempo = analysis.tempo  # BPM

        # 计算时长（秒）
        # tempo 是 BPM，total_ticks / ticks_per_beat = 总拍数
        # duration = total_ticks / ticks_per_beat * 60 / tempo
        duration_sec = (total_ticks / ticks_per_beat) * (60 / tempo) if tempo > 0 else 0

        return {
            "duration_sec": duration_sec,
            "total_ticks": total_ticks,
            "ticks_per_beat": ticks_per_beat,
            "tempo": tempo,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze MIDI: {str(e)}")


@app.post("/analyze_midi")
async def analyze_midi(
    file: UploadFile = File(...),
):
    """
    分析 MIDI 文件

    - 分析轨道信息
    - 识别旋律候选
    - 返回统计信息
    """
    if not file.filename.endswith(('.mid', '.midi')):
        raise HTTPException(status_code=400, detail="Only MIDI files supported")

    # 读取文件
    midi_data = await file.read()

    # 分析
    service = MidiAnalysisService()
    result = service.analyze(midi_data)

    # 转换为响应格式
    response = {
        "tracks": [
            {
                "index": t.index,
                "name": t.name,
                "note_on_count": len(t.notes),
                "pitch_range": (
                    min(n.pitch for n in t.notes) if t.notes else 0,
                    max(n.pitch for n in t.notes) if t.notes else 0
                ),
                "max_polyphony": 0  # 简化
            }
            for t in result.tracks
        ],
        "melody_candidates": [
            {
                "track_index": c.track_index,
                "track_name": c.track_name,
                "score": c.score,
                "reason": c.reason
            }
            for c in result.melody_candidates
        ],
        "total_ticks": result.total_ticks,
        "ticks_per_beat": result.ticks_per_beat,
        "tempo": result.tempo,
        "time_signature": f"{result.time_signature[0]}/{result.time_signature[1]}"
    }

    return JSONResponse(content=response)


@app.post("/plan")
async def generate_plan(
    file: UploadFile = File(...),
    user_intent: str = Form(default="编一个标准的室内乐版本"),
    target_size: Optional[int] = Form(default=None),
):
    """
    使用 LLM 生成编曲方案

    - 接收 MIDI 文件
    - 接收用户意图（自然语言描述）
    - 调用 LLM 生成 UnifiedPlan
    - 返回编曲方案
    """
    if not file.filename.endswith(('.mid', '.midi')):
        raise HTTPException(status_code=400, detail="Only MIDI files supported")

    # 读取 MIDI 并分析
    midi_data = await file.read()
    service = MidiAnalysisService()
    analyze_result = service.analyze(midi_data)

    # 转换为 AnalyzeResponse
    analyze_response = AnalyzeResponse(
        tracks=[
            PlanTrackStats(
                index=t.index,
                name=t.name,
                note_on_count=len(t.notes),
                pitch_range=(
                    min(n.pitch for n in t.notes) if t.notes else 0,
                    max(n.pitch for n in t.notes) if t.notes else 0
                ),
                max_polyphony=0
            )
            for t in analyze_result.tracks
        ],
        melody_candidates=[
            MelodyCandidate(
                track_index=c.track_index,
                score=c.score,
                reason=c.reason
            )
            for c in analyze_result.melody_candidates
        ],
        total_ticks=analyze_result.total_ticks,
        ticks_per_beat=int(analyze_result.ticks_per_beat),
        tempo=int(analyze_result.tempo),
        time_signature=f"{analyze_result.time_signature[0]}/{analyze_result.time_signature[1]}"
    )

    # 调用 LLM Planner 生成方案
    tracer = get_tracer("global")
    tracer.start_stage("plan_generation")
    tracer.log_midi_analysis({
        "tracks_count": len(analyze_result.tracks),
        "tempo": analyze_result.tempo,
        "time_signature": str(analyze_result.time_signature),
        "melody_candidates": [
            {"track_index": c.track_index, "score": c.score}
            for c in analyze_result.melody_candidates[:3]
        ]
    })

    planner = LLMPlanner()
    plan = planner.generate_plan(
        analyze_result=analyze_response,
        user_intent=user_intent,
        target_size=target_size
    )

    return JSONResponse(content={
        "plan": plan.model_dump(),
        "analyze": {
            "tracks_count": len(analyze_response.tracks),
            "tempo": analyze_response.tempo,
            "time_signature": analyze_response.time_signature,
            "melody_candidates": [
                {"track_index": c.track_index, "score": c.score}
                for c in analyze_response.melody_candidates[:3]
            ]
        }
    })


@app.post("/arrange")
async def arrange(
    file: UploadFile = File(...),
    plan_json: str = Form(...),
    melody_track: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
):
    """
    执行编曲

    - 接收 MIDI 文件和 Plan JSON
    - 执行编曲
    - 返回输出文件和验证结果
    """
    if not file.filename.endswith(('.mid', '.midi')):
        raise HTTPException(status_code=400, detail="Only MIDI files supported")

    # 读取 MIDI
    midi_data = await file.read()

    # 解析 Plan
    try:
        plan_dict = json.loads(plan_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    # 详细日志输出 plan_dict 结构以便调试
    logger.info(f"Plan dict keys: {plan_dict.keys() if isinstance(plan_dict, dict) else 'not a dict'}")
    if isinstance(plan_dict, dict):
        if 'transform' in plan_dict:
            logger.info(f"Transform: {plan_dict['transform']}")
        if 'ensemble' in plan_dict:
            logger.info(f"Ensemble parts count: {len(plan_dict.get('ensemble', {}).get('parts', []))}")

    try:
        plan = UnifiedPlan(**plan_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 返回更详细的错误信息
        error_detail = f"Invalid plan: {e}"
        if hasattr(e, 'errors'):
            error_detail = f"Validation errors: {e.errors()}"
        raise HTTPException(status_code=400, detail=error_detail)

    # 确定 melody track（优先使用前端传递的参数）
    melody_track_index = 0
    if melody_track is not None:
        try:
            melody_track_index = int(melody_track)
        except ValueError:
            melody_track_index = 0
    elif plan.constraints and plan.constraints.lock_melody_events:
        source_ref = plan.constraints.lock_melody_events.source_track_ref
        if source_ref:
            try:
                melody_track_index = int(source_ref)
            except ValueError:
                melody_track_index = 0

    # 根据 transform.type 选择 Executor
    transform_type = plan.transform.type

    # 安全检查 melody_track_index
    try:
        midi_for_check = MidiReader.read_midi(midi_data)
        tracks_for_check = MidiReader.extract_track_messages(midi_for_check)
        if melody_track_index >= len(tracks_for_check):
            logger.warning(f"melody_track_index {melody_track_index} out of range, using 0. Available tracks: {len(tracks_for_check)}")
            melody_track_index = 0
    except Exception as e:
        logger.error(f"Error reading MIDI for track check: {e}")

    try:
        if transform_type == "orchestration":
            executor = OrchestrateExecutor(plan)
            try:
                output_tracks, stats = executor.execute(
                    input_midi=midi_data,
                    melody_track_index=melody_track_index
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise
        elif transform_type == "difficulty":
            if plan.transform.direction == "down":
                executor = SimplifyExecutor(plan)
            else:
                executor = ComplexifyExecutor(plan)
            output_data = executor.execute(midi_data)
            # 写回文件
            output_path = STORAGE_DIR / f"output_{uuid.uuid4().hex}.mid"
            with open(output_path, "wb") as f:
                f.write(output_data)
            return JSONResponse(content={
                "output_path": str(output_path),
                "checks": {},
                "stats": {"type": transform_type}
            })
        elif transform_type in ["creative", "style"]:
            executor = CreativeExecutor(plan)
            output_tracks, stats = executor.execute(midi_data)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported transform type: {transform_type}")

        # 从输入 MIDI 提取 tempo 和 time_signature
        input_midi = MidiReader.read_midi(midi_data)
        analyzer = MidiAnalyzer(input_midi)
        midi_analysis = analyzer.analyze()
        tempo = midi_analysis.tempo
        time_signature = midi_analysis.time_signature

        # 写入 MIDI 文件 - 使用唯一文件名避免并发覆盖
        output_filename = f"arranged_{uuid.uuid4().hex[:8]}.mid"
        output_path = STORAGE_DIR / output_filename

        # P1-2: 传入 total_ticks 以便正确补齐 end_of_track
        output_data = MidiWriter.write_midi(
            tracks=output_tracks,
            tempo=tempo,
            time_signature=time_signature,
            total_ticks=midi_analysis.total_ticks
        )

        with open(output_path, "wb") as f:
            f.write(output_data)

        # 同时保存一份 arranged.mid 方便下载
        latest_path = STORAGE_DIR / "arranged.mid"
        with open(latest_path, "wb") as f:
            f.write(output_data)

        # 验证
        validator = Validator(plan)
        validation_result = validator.validate(midi_data, output_tracks)

        # 返回结果
        import base64
        midi_data_b64 = base64.b64encode(output_data).decode('ascii')

        return JSONResponse(content={
            "output_path": str(latest_path),  # 返回固定路径方便下载
            "unique_path": str(output_path),  # 返回唯一路径
            "midi_data": midi_data_b64,  # 返回 base64 编码的 MIDI 数据
            "checks": validation_result.to_dict(),
            "stats": stats
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Arrangement failed: {e}")


@app.post("/revise")
async def revise(
    conversation_id: str = Form(...),
    revision_json: str = Form(...),
):
    """
    局部修改

    - 根据 revision 修改当前 Plan
    - 重新执行编曲
    """
    with conversation_lock:
        if conversation_id not in conversations:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conversation = conversations[conversation_id]

    try:
        revision = json.loads(revision_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 解析修改类型
    revision_type = revision.get("type")

    if revision_type == "section":
        # 局部修改
        section_id = revision.get("section_id")
        instruction = revision.get("instruction")

        # 这里需要调用 LLM 来解析指令并更新 Plan
        # 简化：返回当前 Plan，让扣子端处理
        return JSONResponse(content={
            "conversation_id": conversation_id,
            "status": "not_implemented",
            "message": "Section revision requires LLM interpretation"
        })

    elif revision_type == "global":
        # 全局修改
        new_plan_dict = revision.get("plan")
        if new_plan_dict:
            conversation["plan"] = new_plan_dict
            return JSONResponse(content={
                "conversation_id": conversation_id,
                "status": "updated",
                "plan": new_plan_dict
            })

    raise HTTPException(status_code=400, detail="Invalid revision format")


@app.post("/render")
async def render(
    file: UploadFile = File(...),
    format: str = Form("pdf"),
):
    """
    渲染 PDF/MP3

    - 接收 MIDI 文件
    - 渲染为 PDF 乐谱或 MP3 音频
    """
    if not file.filename.endswith(('.mid', '.midi')):
        raise HTTPException(status_code=400, detail="Only MIDI files supported")

    if format not in ["pdf", "mp3"]:
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'mp3'")

    # 读取 MIDI
    midi_data = await file.read()

    output_id = uuid.uuid4().hex

    if format == "pdf":
        # TODO: 使用 MuseScore 渲染 PDF
        output_path = STORAGE_DIR / f"score_{output_id}.pdf"
        # 简化：返回提示
        return JSONResponse(content={
            "status": "not_implemented",
            "message": "PDF rendering requires MuseScore integration"
        })

    elif format == "mp3":
        # TODO: 使用 FluidSynth 渲染 MP3
        output_path = STORAGE_DIR / f"audio_{output_id}.mp3"
        # 简化：返回提示
        return JSONResponse(content={
            "status": "not_implemented",
            "message": "MP3 rendering requires FluidSynth integration"
        })


@app.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """获取会话状态"""
    # 先尝试新的 conversation_manager
    conv = conversation_manager.get_conversation(conversation_id)
    if conv:
        return JSONResponse(content=conv)

    # 兼容旧的会话格式
    with conversation_lock:
        if conversation_id not in conversations:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return JSONResponse(content=conversations[conversation_id])


@app.post("/conversation")
async def create_conversation(
    user_intent: str = Form(...),
    midi_data: Optional[str] = Form(None),
):
    """
    创建新会话

    - 记录用户初始意图
    - 可选上传 MIDI 文件
    """
    conversation_id = conversation_manager.create_conversation(
        user_intent=user_intent,
        metadata={"midi_data": midi_data} if midi_data else {}
    )

    return JSONResponse(content={
        "conversation_id": conversation_id,
        "created_at": datetime.now().isoformat(),
        "status": "active"
    })


@app.post("/conversation/{conversation_id}/message")
async def send_message(
    conversation_id: str,
    message: str = Form(...),
    midi_file: Optional[UploadFile] = File(None),
    include_trace: bool = Form(default=False),
):
    """
    发送消息并生成编曲方案

    支持多轮对话：
    - 记录用户消息
    - 分析 MIDI（如果提供）
    - 调用 LLM 生成/优化方案
    - 记录完整追踪日志
    """
    conv = conversation_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tracer = get_tracer(conversation_id)
    tracer.start_stage("user_message")

    # 记录用户消息
    conversation_manager.add_message(
        conversation_id=conversation_id,
        role="user",
        content=message
    )

    # 分析 MIDI（如果提供）
    analyze_result = None
    midi_bytes = None

    if midi_file:
        midi_bytes = await midi_file.read()
        tracer.start_stage("midi_analysis")

        service = MidiAnalysisService()
        result = service.analyze(midi_bytes)

        tracer.log_midi_analysis({
            "tracks_count": len(result.tracks),
            "tempo": result.tempo,
            "time_signature": str(result.time_signature),
            "total_ticks": result.total_ticks,
            "melody_candidates": [
                {"track_index": c.track_index, "score": c.score}
                for c in result.melody_candidates[:3]
            ]
        })

        analyze_result = AnalyzeResponse(
            tracks=[
                PlanTrackStats(
                    index=t.index,
                    name=t.name,
                    note_on_count=len(t.notes),
                    pitch_range=(
                        min(n.pitch for n in t.notes) if t.notes else 0,
                        max(n.pitch for n in t.notes) if t.notes else 0
                    ),
                    max_polyphony=0
                )
                for t in result.tracks
            ],
            melody_candidates=[
                MelodyCandidate(
                    track_index=c.track_index,
                    score=c.score,
                    reason=c.reason
                )
                for c in result.melody_candidates
            ],
            total_ticks=result.total_ticks,
            ticks_per_beat=int(result.ticks_per_beat),
            tempo=int(result.tempo),
            time_signature=f"{result.time_signature[0]}/{result.time_signature[1]}"
        )

    # 获取所有版本的反馈（用于多轮优化）
    all_feedback = []
    conv = conversation_manager.get_conversation(conversation_id)
    if conv:
        for version in conv.get("arrangement_versions", []):
            if version.get("user_feedback"):
                all_feedback.append(f"v{version['version_id']}: {version['user_feedback']}")

    previous_feedback = "\n".join(all_feedback) if all_feedback else None

    # 调用 LLM 生成方案
    tracer.start_stage("plan_generation")
    planner = LLMPlanner(conversation_id=conversation_id)

    plan = planner.generate_plan(
        analyze_result=analyze_result,
        user_intent=message,
        previous_feedback=previous_feedback
    )

    # 保存方案版本
    version_id = conversation_manager.add_arrangement_version(
        conversation_id=conversation_id,
        plan=plan.model_dump()
    )

    # 记录完整会话日志
    try:
        # 获取 LLM 的 prompt 和 response
        llm_thoughts = conversation_manager.get_llm_thoughts(conversation_id)
        latest_thought = llm_thoughts[-1] if llm_thoughts else {}

        session_log = SessionLog(
            conversation_id=conversation_id,
            version_id=version_id,
            user_intent=message,
            midi_filename=midi_file.filename if midi_file else "",
            midi_analysis=analyze_result.model_dump() if analyze_result else {},
            llm_prompt=latest_thought.get("prompt", ""),
            llm_response=latest_thought.get("response", ""),
            llm_model=latest_thought.get("model", ""),
            llm_tokens_used=latest_thought.get("tokens_used", 0),
            llm_duration_ms=latest_thought.get("duration_ms", 0),
            plan=plan.model_dump(),
            trace_events=tracer.export().get("events", []) if include_trace else [],
            status="generated"
        )
        session_logger.save_session_log(session_log)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 日志记录失败不影响主流程

    # 更新用户当前意图
    conversation_manager.update_intent(conversation_id, message)

    # 获取追踪摘要
    trace_summary = tracer.get_summary() if include_trace else None

    # 返回结果
    response = {
        "conversation_id": conversation_id,
        "version_id": version_id,
        "plan": plan.model_dump(),
        "status": "generated"
    }

    if trace_summary:
        response["trace"] = trace_summary

    return JSONResponse(content=response)


@app.post("/conversation/{conversation_id}/feedback")
async def submit_feedback(
    conversation_id: str,
    version_id: str = Form(...),
    feedback: str = Form(...),
):
    """
    提交对某个版本的反馈

    用于多轮优化：
    - 用户反馈将被记录
    - 下一轮生成时会考虑反馈
    """
    conv = conversation_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation_manager.update_version_feedback(
        conversation_id=conversation_id,
        version_id=version_id,
        feedback=feedback
    )

    conversation_manager.add_message(
        conversation_id=conversation_id,
        role="user",
        content=f"[反馈 v{version_id}]: {feedback}"
    )

    return JSONResponse(content={
        "conversation_id": conversation_id,
        "version_id": version_id,
        "status": "feedback_recorded"
    })


@app.post("/conversation/{conversation_id}/regenerate")
async def regenerate_from_feedback(
    conversation_id: str,
    midi_file: Optional[UploadFile] = File(None),
    include_trace: bool = Form(default=False),
):
    """
    基于已有反馈重新生成编曲方案

    不添加新消息，只使用已存储的反馈重新生成
    如果提供 MIDI 文件，会重新进行分析
    """
    conv = conversation_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tracer = get_tracer(conversation_id)
    tracer.start_stage("regeneration")

    # 获取所有版本的反馈
    all_feedback = []
    for version in conv.get("arrangement_versions", []):
        if version.get("user_feedback"):
            all_feedback.append(f"v{version['version_id']}: {version['user_feedback']}")

    previous_feedback = "\n".join(all_feedback) if all_feedback else None

    if not previous_feedback:
        raise HTTPException(status_code=400, detail="No feedback available for regeneration")

    # 使用原始意图（不添加新消息）
    original_intent = conv.get("initial_intent", "")

    # 分析 MIDI（如果提供）
    analyze_result = None
    if midi_file:
        tracer.start_stage("midi_analysis")
        midi_bytes = await midi_file.read()

        service = MidiAnalysisService()
        result = service.analyze(midi_bytes)

        analyze_result = AnalyzeResponse(
            tracks=[
                PlanTrackStats(
                    index=t.index,
                    name=t.name,
                    note_on_count=len(t.notes),
                    pitch_range=(
                        min(n.pitch for n in t.notes) if t.notes else 0,
                        max(n.pitch for n in t.notes) if t.notes else 0
                    ),
                    max_polyphony=0
                )
                for t in result.tracks
            ],
            melody_candidates=[
                MelodyCandidate(
                    track_index=c.track_index,
                    score=c.score,
                    reason=c.reason
                )
                for c in result.melody_candidates
            ],
            total_ticks=result.total_ticks,
            ticks_per_beat=int(result.ticks_per_beat),
            tempo=int(result.tempo),
            time_signature=f"{result.time_signature[0]}/{result.time_signature[1]}"
        )

    # 调用 LLM 生成方案
    tracer.start_stage("plan_generation")
    planner = LLMPlanner(conversation_id=conversation_id)

    plan = planner.generate_plan(
        analyze_result=analyze_result,
        user_intent=original_intent,
        previous_feedback=previous_feedback
    )

    # 保存方案版本
    version_id = conversation_manager.add_arrangement_version(
        conversation_id=conversation_id,
        plan=plan.model_dump()
    )

    # 获取追踪摘要
    trace_summary = tracer.get_summary() if include_trace else None

    # 返回结果
    response = {
        "conversation_id": conversation_id,
        "version_id": version_id,
        "plan": plan.model_dump(),
        "status": "generated",
        "feedback_used": previous_feedback
    }

    if trace_summary:
        response["trace"] = trace_summary

    return JSONResponse(content=response)


@app.get("/conversation/{conversation_id}/trace")
async def get_trace(conversation_id: str):
    """获取会话的完整追踪日志"""
    conv = conversation_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tracer = get_tracer(conversation_id)
    trace_data = tracer.export()

    return JSONResponse(content=trace_data)


@app.get("/conversation/{conversation_id}/history")
async def get_history(conversation_id: str):
    """获取会话的完整历史"""
    conv = conversation_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return JSONResponse(content={
        "conversation_id": conversation_id,
        "initial_intent": conv.get("initial_intent"),
        "current_intent": conv.get("current_intent"),
        "messages": conv.get("messages", []),
        "llm_thoughts": conv.get("llm_thoughts", []),
        "processing_steps": conv.get("processing_steps", []),
        "arrangement_versions": [
            {
                "version_id": v.get("version_id"),
                "status": v.get("status"),
                "created_at": v.get("created_at"),
                "has_feedback": bool(v.get("user_feedback"))
            }
            for v in conv.get("arrangement_versions", [])
        ]
    })


@app.get("/conversation/{conversation_id}/export")
async def export_conversation(conversation_id: str):
    """导出会话完整记录"""
    conv = conversation_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    export_data = conversation_manager.export_conversation(conversation_id)

    # 保存到文件
    export_path = STORAGE_DIR / f"conversation_{conversation_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    return JSONResponse(content={
        "conversation_id": conversation_id,
        "export_path": str(export_path),
        "versions_count": len(export_data.get("arrangement_versions", [])),
        "messages_count": len(export_data.get("messages", [])),
        "llm_thoughts_count": len(export_data.get("llm_thoughts", []))
    })


@app.get("/conversations")
async def list_conversations():
    """列出所有会话"""
    convs = conversation_manager.list_conversations()
    return JSONResponse(content={"conversations": convs})


@app.get("/session/{conversation_id}/{version_id}")
async def get_session_log(conversation_id: str, version_id: str):
    """
    获取指定会话版本的完整日志

    返回：
    - 会话基本信息
    - 用户意图
    - MIDI 分析结果
    - LLM prompts 和 responses
    - Plan JSON
    - 执行追踪
    """
    log = session_logger.get_session_log(conversation_id, version_id)
    if not log:
        raise HTTPException(status_code=404, detail="Session log not found")

    return JSONResponse(content=asdict(log))


@app.get("/session/{conversation_id}/versions")
async def get_session_versions(conversation_id: str):
    """获取会话的所有版本日志"""
    logs = session_logger.get_session_logs(conversation_id)
    return JSONResponse(content={
        "conversation_id": conversation_id,
        "versions": [
            {
                "version_id": log.version_id,
                "created_at": log.created_at,
                "status": log.status,
                "plan_parts_count": len(log.plan.get("ensemble", {}).get("parts", [])) if log.plan else 0,
                "user_intent_preview": log.user_intent[:100] if log.user_intent else ""
            }
            for log in logs
        ]
    })


@app.get("/sessions")
async def list_sessions():
    """列出所有会话（基于 session_logger）"""
    sessions = session_logger.list_sessions()
    return JSONResponse(content={"sessions": sessions})


@app.get("/files/{filename}")
async def download_file(filename: str):
    """下载编曲结果文件"""
    file_path = STORAGE_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename, media_type="audio/midi")


# ============ CORS 中间件配置 ============

# 允许所有来源（生产环境应该限制）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 便捷函数 ============

def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    return app


# ============ 运行入口 ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

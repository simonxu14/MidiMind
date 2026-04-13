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
import uuid
import json
import time
import base64
import hashlib
import subprocess
import traceback

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import asdict

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .plan_schema import (
    UnifiedPlan,
    AnalyzeResponse,
    TrackStats as PlanTrackStats,
    MelodyCandidate,
    RevisionIntent,
)
from .analyze import MidiAnalysisService
from .orchestrate_executor import OrchestrateExecutor
from .simplify_executor import SimplifyExecutor
from .complexify_executor import ComplexifyExecutor
from .creative_executor import CreativeExecutor
from .validator import Validator
from .midi_io import MidiWriter, MidiReader, MidiAnalyzer
from .llm_planner import LLMPlanner
from .revision_executor import RevisionExecutor
from .plan_linter import lint_plan
from .conversation import conversation_manager
from .storage import atomic_write_bytes, atomic_write_json, get_storage_dir
from .tracer import get_tracer
from .session_logger import session_logger, SessionLog


# ============ App Setup ============

app = FastAPI(
    title="MidiMind API",
    description="MidiMind - AI 驱动的 MIDI 编曲服务",
    version="0.2.0",
)

# 存储目录
STORAGE_DIR = get_storage_dir("outputs", "MIDIMIND_OUTPUT_DIR")

# 代码仓库根目录（用于 git commit id 获取）
REPO_ROOT = Path(__file__).parent.parent.parent


def _require_midi_filename(filename: Optional[str]) -> None:
    """Ensure the uploaded file looks like a MIDI file."""
    if not filename or not filename.endswith((".mid", ".midi")):
        raise HTTPException(status_code=400, detail="Only MIDI files supported")


def _build_analyze_response(result: Any) -> AnalyzeResponse:
    """Convert raw MIDI analysis output into plan-schema response model."""
    return AnalyzeResponse(
        tracks=[
            PlanTrackStats(
                index=track.index,
                name=track.name,
                note_on_count=len(track.notes),
                pitch_range=(
                    min(note.pitch for note in track.notes) if track.notes else 0,
                    max(note.pitch for note in track.notes) if track.notes else 0,
                ),
                max_polyphony=0,
            )
            for track in result.tracks
        ],
        melody_candidates=[
            MelodyCandidate(
                track_index=candidate.track_index,
                score=candidate.score,
                reason=candidate.reason,
            )
            for candidate in result.melody_candidates
        ],
        total_ticks=result.total_ticks,
        ticks_per_beat=int(result.ticks_per_beat),
        tempo=int(result.tempo),
        time_signature=f"{result.time_signature[0]}/{result.time_signature[1]}",
    )


def _build_analyze_payload(result: Any) -> Dict[str, Any]:
    """Build the public analyze payload shape from raw analysis output."""
    analyze_response = _build_analyze_response(result)
    melody_candidates_by_track = {
        candidate.track_index: candidate
        for candidate in result.melody_candidates
    }

    return {
        "tracks": [
            {
                "index": track.index,
                "name": track.name,
                "note_on_count": track.note_on_count,
                "pitch_range": track.pitch_range,
                "max_polyphony": track.max_polyphony,
            }
            for track in analyze_response.tracks
        ],
        "melody_candidates": [
            {
                "track_index": candidate.track_index,
                "track_name": melody_candidates_by_track[candidate.track_index].track_name,
                "score": candidate.score,
                "reason": candidate.reason,
            }
            for candidate in analyze_response.melody_candidates
        ],
        "total_ticks": analyze_response.total_ticks,
        "ticks_per_beat": analyze_response.ticks_per_beat,
        "tempo": analyze_response.tempo,
        "time_signature": analyze_response.time_signature,
    }


def _require_conversation(conversation_id: str) -> Dict[str, Any]:
    """Fetch a conversation or raise a 404."""
    conversation = conversation_manager.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _collect_previous_feedback(conversation: Dict[str, Any]) -> Optional[str]:
    """Collect versioned user feedback into the planner input format."""
    feedback_items = [
        f"v{version['version_id']}: {version['user_feedback']}"
        for version in conversation.get("arrangement_versions", [])
        if version.get("user_feedback")
    ]
    return "\n".join(feedback_items) if feedback_items else None


def _generate_or_revise_plan(
    conversation: Dict[str, Any],
    conversation_id: str,
    message: str,
    analyze_result: Optional[AnalyzeResponse],
    tracer: Any,
) -> tuple[UnifiedPlan, Any, Optional[RevisionIntent], Optional[str]]:
    """Generate a fresh plan or revise the latest version when appropriate."""
    previous_feedback = _collect_previous_feedback(conversation)

    tracer.start_stage("plan_generation")
    planner = LLMPlanner(conversation_id=conversation_id)

    plan = None
    revision_result = None
    revision_intent: Optional[RevisionIntent] = None

    has_existing_versions = bool(conversation.get("arrangement_versions"))
    if has_existing_versions:
        latest_version = conversation["arrangement_versions"][-1]
        latest_plan_dict = latest_version.get("plan", {})

        if latest_plan_dict:
            try:
                latest_plan = UnifiedPlan(**latest_plan_dict)

                tracer.start_stage("revision_analysis")
                revision_intent = planner.analyze_revision_intent(
                    user_message=message,
                    current_plan=latest_plan,
                )

                if revision_intent.is_revision:
                    logger.info(
                        f"Revision detected: type={revision_intent.revision_type}, "
                        f"target={revision_intent.target_part_id}, "
                        f"instruction={revision_intent.instruction}"
                    )

                    revision_result = RevisionExecutor().apply_revision(
                        base_plan=latest_plan,
                        revision_intent=revision_intent,
                        user_instruction=revision_intent.instruction,
                        llm_planner=planner,
                        analyze_result=analyze_result,
                    )

                    if revision_result.success:
                        plan = revision_result.revised_plan
                        logger.info(
                            f"Revision applied successfully: {revision_result.message}"
                        )
                    else:
                        logger.warning(
                            f"Revision failed: {revision_result.message}, "
                            "falling back to new generation"
                        )
            except Exception as error:
                logger.error(f"Error during revision detection: {error}")

    if plan is None:
        plan = planner.generate_plan(
            analyze_result=analyze_result,
            user_intent=message,
            previous_feedback=previous_feedback,
        )

    return plan, revision_result, revision_intent, previous_feedback


def _start_conversation_trace(conversation_id: str, stage_name: str) -> Any:
    """Create or fetch the conversation tracer and start the requested stage."""
    tracer = get_tracer(conversation_id)
    tracer.start_stage(stage_name)
    return tracer


def _record_user_message(conversation_id: str, message: str) -> None:
    """Persist a user message onto the conversation timeline."""
    conversation_manager.add_message(
        conversation_id=conversation_id,
        role="user",
        content=message,
    )


async def _read_optional_midi_analysis(
    midi_file: Optional[UploadFile],
    tracer: Any,
) -> Optional[AnalyzeResponse]:
    """Read and analyze an uploaded MIDI file when present."""
    if not midi_file:
        return None

    midi_bytes = await midi_file.read()
    return _analyze_uploaded_midi(midi_bytes, tracer)


def _coerce_analyze_response(data: Optional[Any]) -> Optional[AnalyzeResponse]:
    """Best-effort conversion of persisted analysis payloads back into AnalyzeResponse."""
    if not data:
        return None
    if isinstance(data, AnalyzeResponse):
        return data

    try:
        return AnalyzeResponse(**data)
    except Exception as error:
        logger.warning(f"Failed to restore saved MIDI analysis: {error}")
        return None


def _load_saved_analyze_response(
    conversation_id: str,
    conversation: Dict[str, Any],
) -> Optional[AnalyzeResponse]:
    """Load the latest persisted MIDI analysis from conversation metadata or session logs."""
    metadata_analysis = conversation.get("metadata", {}).get("last_midi_analysis")
    restored = _coerce_analyze_response(metadata_analysis)
    if restored is not None:
        return restored

    for log in reversed(session_logger.get_session_logs(conversation_id)):
        restored = _coerce_analyze_response(log.midi_analysis)
        if restored is not None:
            return restored

    return None


async def _resolve_regenerate_analyze_result(
    conversation_id: str,
    conversation: Dict[str, Any],
    midi_file: Optional[UploadFile],
    tracer: Any,
) -> AnalyzeResponse:
    """Resolve MIDI analysis for regeneration from upload or the latest persisted session state."""
    uploaded_analysis = await _read_optional_midi_analysis(midi_file, tracer)
    if uploaded_analysis is not None:
        return uploaded_analysis

    saved_analysis = _load_saved_analyze_response(conversation_id, conversation)
    if saved_analysis is not None:
        return saved_analysis

    raise HTTPException(
        status_code=400,
        detail="No MIDI analysis available for regeneration; upload a MIDI file first",
    )


def _build_feedback_recorded_response(
    conversation_id: str,
    version_id: str,
) -> Dict[str, Any]:
    """Build the stable response payload after recording version feedback."""
    return {
        "conversation_id": conversation_id,
        "version_id": version_id,
        "status": "feedback_recorded",
    }


def _build_history_payload(
    conversation_id: str,
    conversation: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the public conversation history payload."""
    return {
        "conversation_id": conversation_id,
        "initial_intent": conversation.get("initial_intent"),
        "current_intent": conversation.get("current_intent"),
        "messages": conversation.get("messages", []),
        "llm_thoughts": conversation.get("llm_thoughts", []),
        "processing_steps": conversation.get("processing_steps", []),
        "arrangement_versions": [
            {
                "version_id": version.get("version_id"),
                "status": version.get("status"),
                "created_at": version.get("created_at"),
                "has_feedback": bool(version.get("user_feedback")),
            }
            for version in conversation.get("arrangement_versions", [])
        ],
    }


def _export_conversation_data(conversation_id: str) -> Dict[str, Any]:
    """Export a conversation to disk and return a summary payload."""
    export_data = conversation_manager.export_conversation(conversation_id)
    export_path = STORAGE_DIR / (
        f"conversation_{conversation_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    atomic_write_json(export_path, export_data)

    return {
        "conversation_id": conversation_id,
        "export_path": str(export_path),
        "versions_count": len(export_data.get("arrangement_versions", [])),
        "messages_count": len(export_data.get("messages", [])),
        "llm_thoughts_count": len(export_data.get("llm_thoughts", [])),
    }


def _require_session_log(conversation_id: str, version_id: str) -> SessionLog:
    """Fetch a session log or raise a 404."""
    log = session_logger.get_session_log(conversation_id, version_id)
    if not log:
        raise HTTPException(status_code=404, detail="Session log not found")
    return log


def _build_trace_payload(trace_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build the public trace response payload."""
    return trace_data


def _build_session_log_payload(log: SessionLog) -> Dict[str, Any]:
    """Build the public payload for a single session log."""
    return asdict(log)


def _build_session_versions_payload(
    conversation_id: str,
    logs: list[SessionLog],
) -> Dict[str, Any]:
    """Build the public payload for all session log versions."""
    return {
        "conversation_id": conversation_id,
        "versions": [
            {
                "version_id": log.version_id,
                "created_at": log.created_at,
                "status": log.status,
                "plan_parts_count": len(log.plan.get("ensemble", {}).get("parts", []))
                if log.plan
                else 0,
                "user_intent_preview": log.user_intent[:100] if log.user_intent else "",
            }
            for log in logs
        ],
    }


def _build_sessions_payload(sessions: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the public payload for session logger summaries."""
    return {"sessions": sessions}


def _build_conversations_payload(conversations: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the public payload for conversation summaries."""
    return {"conversations": conversations}


def _build_create_conversation_response(conversation_id: str) -> Dict[str, Any]:
    """Build the stable response payload for a newly created conversation."""
    return {
        "conversation_id": conversation_id,
        "created_at": datetime.now().isoformat(),
        "status": "active",
    }


def _build_midi_duration_payload(analysis: Any) -> Dict[str, Any]:
    """Build the public duration-analysis payload from MIDI analysis output."""
    total_ticks = analysis.total_ticks
    ticks_per_beat = analysis.ticks_per_beat
    tempo = analysis.tempo
    duration_sec = (total_ticks / ticks_per_beat) * (60 / tempo) if tempo > 0 else 0

    return {
        "duration_sec": duration_sec,
        "total_ticks": total_ticks,
        "ticks_per_beat": ticks_per_beat,
        "tempo": tempo,
    }


def _build_plan_generation_response(
    plan: UnifiedPlan,
    analyze_response: AnalyzeResponse,
) -> Dict[str, Any]:
    """Build the stable payload for the /plan endpoint."""
    return {
        "plan": plan.model_dump(),
        "analyze": {
            "tracks_count": len(analyze_response.tracks),
            "tempo": analyze_response.tempo,
            "time_signature": analyze_response.time_signature,
            "melody_candidates": [
                {"track_index": candidate.track_index, "score": candidate.score}
                for candidate in analyze_response.melody_candidates[:3]
            ],
        },
    }


def _analyze_uploaded_midi(midi_bytes: bytes, tracer: Any) -> AnalyzeResponse:
    """Analyze uploaded MIDI bytes and log summary stats to the tracer."""
    tracer.start_stage("midi_analysis")

    result = MidiAnalysisService().analyze(midi_bytes)
    tracer.log_midi_analysis({
        "tracks_count": len(result.tracks),
        "tempo": result.tempo,
        "time_signature": str(result.time_signature),
        "total_ticks": result.total_ticks,
        "melody_candidates": [
            {"track_index": candidate.track_index, "score": candidate.score}
            for candidate in result.melody_candidates[:3]
        ],
    })
    return _build_analyze_response(result)


def _build_lint_failure_response(lint_result: Any, conversation_id: str) -> JSONResponse:
    """Convert lint failures into the stable API error payload."""
    errors_summary = lint_result.get_summary()
    error_details = [
        {
            "code": error.code,
            "message": error.message,
            "location": error.location,
            "suggestion": error.suggestion,
        }
        for error in lint_result.errors
    ]
    warnings_details = [
        {
            "code": warning.code,
            "message": warning.message,
            "location": warning.location,
            "suggestion": warning.suggestion,
        }
        for warning in lint_result.warnings
    ]

    logger.warning(f"Plan lint failed: {errors_summary}")
    return JSONResponse(
        status_code=400,
        content={
            "error": "plan_validation_failed",
            "summary": f"Plan Lint: {errors_summary}",
            "errors": error_details,
            "warnings": warnings_details,
            "conversation_id": conversation_id,
        },
    )


def _build_lint_warnings_payload(lint_result: Any) -> Optional[Dict[str, Any]]:
    """Build the optional lint warnings payload for successful responses."""
    if not lint_result.warnings:
        return None

    return {
        "passed": True,
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "location": warning.location,
                "suggestion": warning.suggestion,
            }
            for warning in lint_result.warnings
        ],
    }


def _build_revision_response_payload(
    revision_intent: Optional[RevisionIntent],
    revision_result: Any,
) -> Optional[Dict[str, Any]]:
    """Build the optional revision metadata for conversation responses."""
    if not revision_intent or not revision_intent.is_revision:
        return None

    return {
        "is_revision": True,
        "revision_type": revision_intent.revision_type,
        "target_part_id": revision_intent.target_part_id,
        "message": revision_result.message if revision_result else "",
        "modified_parts": revision_result.modified_parts if revision_result else [],
    }


def _build_generated_plan_response(
    conversation_id: str,
    version_id: str,
    plan: UnifiedPlan,
    lint_payload: Optional[Dict[str, Any]] = None,
    revision_payload: Optional[Dict[str, Any]] = None,
    trace_summary: Optional[Dict[str, Any]] = None,
    feedback_used: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the shared success response for generated plan endpoints."""
    response = {
        "conversation_id": conversation_id,
        "version_id": version_id,
        "plan": plan.model_dump(),
        "status": "generated",
    }

    if lint_payload:
        response["lint"] = lint_payload
    if revision_payload:
        response["revision"] = revision_payload
    if trace_summary:
        response["trace"] = trace_summary
    if feedback_used:
        response["feedback_used"] = feedback_used

    return response


def _save_session_log_safe(
    conversation_id: str,
    version_id: str,
    user_intent: str,
    midi_filename: str,
    analyze_result: Optional[AnalyzeResponse],
    plan: UnifiedPlan,
    tracer: Any,
    include_trace: bool,
) -> None:
    """Persist session logs without letting logging failures break the request."""
    try:
        llm_thoughts = conversation_manager.get_llm_thoughts(conversation_id)
        latest_thought = llm_thoughts[-1] if llm_thoughts else {}

        session_log = SessionLog(
            conversation_id=conversation_id,
            version_id=version_id,
            user_intent=user_intent,
            midi_filename=midi_filename,
            midi_analysis=analyze_result.model_dump() if analyze_result else {},
            llm_prompt=latest_thought.get("prompt", ""),
            llm_response=latest_thought.get("response", ""),
            llm_model=latest_thought.get("model", ""),
            llm_tokens_used=latest_thought.get("tokens_used", 0),
            llm_duration_ms=latest_thought.get("duration_ms", 0),
            plan=plan.model_dump(),
            trace_events=tracer.export().get("events", []) if include_trace else [],
            status="generated",
        )
        session_logger.save_session_log(session_log)
    except Exception:
        traceback.print_exc()


def _finalize_generated_plan_response(
    conversation_id: str,
    plan: UnifiedPlan,
    tracer: Any,
    include_trace: bool,
    user_intent: Optional[str] = None,
    midi_filename: str = "",
    analyze_result: Optional[AnalyzeResponse] = None,
    lint_payload: Optional[Dict[str, Any]] = None,
    revision_payload: Optional[Dict[str, Any]] = None,
    feedback_used: Optional[str] = None,
    update_intent_to: Optional[str] = None,
    generation_intent: Optional[str] = None,
) -> JSONResponse:
    """Persist a generated plan version and build the stable API response."""
    if analyze_result is not None:
        conversation_manager.update_metadata(
            conversation_id,
            {"last_midi_analysis": analyze_result.model_dump()},
        )

    version_id = conversation_manager.add_arrangement_version(
        conversation_id=conversation_id,
        plan=plan.model_dump(),
        generation_intent=generation_intent,
    )

    if user_intent is not None:
        _save_session_log_safe(
            conversation_id=conversation_id,
            version_id=version_id,
            user_intent=user_intent,
            midi_filename=midi_filename,
            analyze_result=analyze_result,
            plan=plan,
            tracer=tracer,
            include_trace=include_trace,
        )

    if update_intent_to is not None:
        conversation_manager.update_intent(conversation_id, update_intent_to)

    trace_summary = tracer.get_summary() if include_trace else None
    response = _build_generated_plan_response(
        conversation_id=conversation_id,
        version_id=version_id,
        plan=plan,
        lint_payload=lint_payload,
        revision_payload=revision_payload,
        trace_summary=trace_summary,
        feedback_used=feedback_used,
    )
    return JSONResponse(content=response)


def _parse_plan_json(plan_json: str) -> UnifiedPlan:
    """Parse and validate the incoming plan JSON payload."""
    try:
        plan_dict = json.loads(plan_json)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {error}")

    logger.info(f"Plan dict keys: {plan_dict.keys() if isinstance(plan_dict, dict) else 'not a dict'}")
    if isinstance(plan_dict, dict):
        if "transform" in plan_dict:
            logger.info(f"Transform: {plan_dict['transform']}")
        if "ensemble" in plan_dict:
            logger.info(f"Ensemble parts count: {len(plan_dict.get('ensemble', {}).get('parts', []))}")

    try:
        return UnifiedPlan(**plan_dict)
    except Exception as error:
        traceback.print_exc()
        error_detail = f"Invalid plan: {error}"
        if hasattr(error, "errors"):
            error_detail = f"Validation errors: {error.errors()}"
        raise HTTPException(status_code=400, detail=error_detail)


def _resolve_melody_track_index(plan: UnifiedPlan, melody_track: Optional[str]) -> int:
    """Resolve the melody source track index from request input or plan constraints."""
    if melody_track is not None:
        try:
            return int(melody_track)
        except ValueError:
            return 0

    lock_melody = plan.constraints.lock_melody_events if plan.constraints else None
    source_ref = lock_melody.source_track_ref if lock_melody else None
    if source_ref:
        try:
            return int(source_ref)
        except ValueError:
            return 0

    return 0


def _sanitize_melody_track_index(midi_data: bytes, melody_track_index: int) -> int:
    """Clamp the melody track index to the available track count when possible."""
    try:
        midi_for_check = MidiReader.read_midi(midi_data)
        tracks_for_check = MidiReader.extract_track_messages(midi_for_check)
        if melody_track_index >= len(tracks_for_check):
            logger.warning(
                f"melody_track_index {melody_track_index} out of range, using 0. "
                f"Available tracks: {len(tracks_for_check)}"
            )
            return 0
    except Exception as error:
        logger.error(f"Error reading MIDI for track check: {error}")

    return melody_track_index


def _select_executor_and_run(
    plan: UnifiedPlan,
    midi_data: bytes,
    melody_track_index: int,
) -> tuple[Any, Dict[str, Any]]:
    """Run the arrangement executor selected by the plan transform type."""
    transform_type = plan.transform.type

    if transform_type == "orchestration":
        executor = OrchestrateExecutor(plan)
        return executor.execute(
            input_midi=midi_data,
            melody_track_index=melody_track_index,
        )

    if transform_type in ["creative", "style"]:
        executor = CreativeExecutor(plan)
        return executor.execute(midi_data)

    raise HTTPException(status_code=400, detail=f"Unsupported transform type: {transform_type}")


def _write_arranged_output(midi_data: bytes, output_tracks: Any) -> Dict[str, Any]:
    """Write arranged output to a unique file and return metadata."""
    input_midi = MidiReader.read_midi(midi_data)
    analyzer = MidiAnalyzer(input_midi)
    midi_analysis = analyzer.analyze()

    output_filename = f"arranged_{uuid.uuid4().hex[:8]}.mid"
    output_path = STORAGE_DIR / output_filename

    output_data = MidiWriter.write_midi(
        tracks=output_tracks,
        tempo=midi_analysis.tempo,
        time_signature=midi_analysis.time_signature,
        total_ticks=midi_analysis.total_ticks,
    )

    atomic_write_bytes(output_path, output_data)

    return {
        "output_data": output_data,
        "output_path": output_path,
    }


def _run_difficulty_arrangement(plan: UnifiedPlan, midi_data: bytes) -> JSONResponse:
    """Execute difficulty transform and return the stable response payload."""
    if plan.transform.direction == "down":
        executor = SimplifyExecutor(plan)
    else:
        executor = ComplexifyExecutor(plan)

    output_data = executor.execute(midi_data)
    output_path = STORAGE_DIR / f"output_{uuid.uuid4().hex}.mid"
    atomic_write_bytes(output_path, output_data)

    return JSONResponse(content={
        "output_path": str(output_path),
        "checks": {},
        "stats": {"type": "difficulty"},
    })


def _get_repo_commit_id() -> Optional[str]:
    """Return the current short git commit id when available."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
    except Exception:
        return None


def _build_execution_metadata(output_data: bytes, execution_start_time: float) -> Dict[str, Any]:
    """Build stable execution metadata for persistence and diagnostics."""
    return {
        "execution_duration_ms": int((time.time() - execution_start_time) * 1000),
        "output_midi_hash": hashlib.sha256(output_data).hexdigest(),
    }


def _build_arrange_success_response(
    output_path: Path,
    output_data: bytes,
    validation_result: Any,
    stats: Dict[str, Any],
) -> JSONResponse:
    """Build the stable success response payload for arranged MIDI output."""
    midi_data_b64 = base64.b64encode(output_data).decode("ascii")
    validation_passed = bool(getattr(validation_result, "all_passed", True))
    return JSONResponse(content={
        "output_path": str(output_path),
        "unique_path": str(output_path),
        "status": "validated" if validation_passed else "validation_failed",
        "validation_passed": validation_passed,
        "midi_data": midi_data_b64,
        "checks": validation_result.to_dict(),
        "stats": stats,
    })


def _run_standard_arrangement(
    plan: UnifiedPlan,
    midi_data: bytes,
    melody_track_index: int,
    execution_start_time: float,
    conversation_id: Optional[str],
    version_id: Optional[str],
    commit_id: Optional[str],
) -> JSONResponse:
    """Execute non-difficulty arrangement flows and persist execution metadata."""
    output_tracks, stats = _select_executor_and_run(
        plan,
        midi_data,
        melody_track_index,
    )
    output_result = _write_arranged_output(midi_data, output_tracks)
    output_data = output_result["output_data"]
    output_path = output_result["output_path"]

    validation_result = Validator(plan).validate(midi_data, output_tracks)
    execution_metadata = _build_execution_metadata(output_data, execution_start_time)

    _update_arrangement_version_result_safe(
        conversation_id=conversation_id,
        version_id=version_id,
        stats=stats,
        validation_result=validation_result,
        output_path=output_path,
        output_midi_hash=execution_metadata["output_midi_hash"],
        commit_id=commit_id,
        execution_duration_ms=execution_metadata["execution_duration_ms"],
    )

    return _build_arrange_success_response(
        output_path=output_path,
        output_data=output_data,
        validation_result=validation_result,
        stats=stats,
    )


def _update_arrangement_version_result_safe(
    conversation_id: Optional[str],
    version_id: Optional[str],
    stats: Dict[str, Any],
    validation_result: Any,
    output_path: Path,
    output_midi_hash: str,
    commit_id: Optional[str],
    execution_duration_ms: int,
) -> None:
    """Persist arrangement execution metadata without breaking the request path."""
    if not conversation_id or not version_id:
        return

    try:
        conversation_manager.update_arrangement_version_result(
            conversation_id=conversation_id,
            version_id=version_id,
            stats=stats,
            validator_result=validation_result.to_dict(),
            arrangement_report=stats.get("arrangement_report") if stats else None,
            output_midi_hash=output_midi_hash,
            output_file_path=str(output_path),
            commit_id=commit_id,
            execution_duration_ms=execution_duration_ms,
        )
    except Exception as error:
        logger.warning(f"Failed to save execution result to conversation: {error}")


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
    unique_path: str
    status: str
    validation_passed: bool
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
    _require_midi_filename(file.filename)

    midi_data = await file.read()
    await file.seek(0)

    try:
        midi = MidiReader.read_midi(midi_data)
        analyzer = MidiAnalyzer(midi)
        analysis = analyzer.analyze()
        return _build_midi_duration_payload(analysis)
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
    _require_midi_filename(file.filename)

    # 读取文件
    midi_data = await file.read()

    # 分析
    service = MidiAnalysisService()
    result = service.analyze(midi_data)

    response = _build_analyze_payload(result)

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
    _require_midi_filename(file.filename)

    # 读取 MIDI 并分析
    midi_data = await file.read()
    service = MidiAnalysisService()
    analyze_result = service.analyze(midi_data)

    # 转换为 AnalyzeResponse
    analyze_response = _build_analyze_response(analyze_result)

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

    return JSONResponse(content=_build_plan_generation_response(plan, analyze_response))


@app.post("/arrange")
async def arrange(
    file: UploadFile = File(...),
    plan_json: str = Form(...),
    melody_track: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    version_id: Optional[str] = Form(None),
):
    """
    执行编曲

    - 接收 MIDI 文件和 Plan JSON
    - 执行编曲
    - 返回输出文件和验证结果
    - 如果提供 conversation_id 和 version_id，结果会保存到会话
    """
    _require_midi_filename(file.filename)

    # 记录开始时间
    execution_start_time = time.time()

    # 获取当前 commit id
    commit_id = _get_repo_commit_id()

    # 读取 MIDI
    midi_data = await file.read()

    plan = _parse_plan_json(plan_json)

    # 确定 melody track（优先使用前端传递的参数）
    melody_track_index = _resolve_melody_track_index(plan, melody_track)

    transform_type = plan.transform.type

    # 安全检查 melody_track_index
    melody_track_index = _sanitize_melody_track_index(midi_data, melody_track_index)

    try:
        if transform_type == "difficulty":
            return _run_difficulty_arrangement(plan, midi_data)

        return _run_standard_arrangement(
            plan,
            midi_data,
            melody_track_index,
            execution_start_time,
            conversation_id,
            version_id,
            commit_id,
        )

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
    conversation = _require_conversation(conversation_id)

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
            conversation_manager.update_latest_plan(conversation_id, new_plan_dict)
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
    _require_midi_filename(file.filename)

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
    return JSONResponse(content=_require_conversation(conversation_id))


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

    return JSONResponse(content=_build_create_conversation_response(conversation_id))


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
    conv = _require_conversation(conversation_id)

    tracer = _start_conversation_trace(conversation_id, "user_message")
    _record_user_message(conversation_id, message)
    analyze_result = await _read_optional_midi_analysis(midi_file, tracer)

    conv = _require_conversation(conversation_id)
    plan, revision_result, revision_intent, _ = _generate_or_revise_plan(
        conversation=conv,
        conversation_id=conversation_id,
        message=message,
        analyze_result=analyze_result,
        tracer=tracer,
    )

    # ========== Plan Lint ==========
    # 在执行前对 plan 进行校验
    lint_result = lint_plan(plan.model_dump())

    if not lint_result.passed:
        return _build_lint_failure_response(lint_result, conversation_id)

    if lint_result.warnings:
        logger.info(f"Plan lint passed with warnings: {lint_result.get_summary()}")

    lint_payload = _build_lint_warnings_payload(lint_result)
    revision_payload = _build_revision_response_payload(revision_intent, revision_result)

    return _finalize_generated_plan_response(
        conversation_id=conversation_id,
        plan=plan,
        tracer=tracer,
        include_trace=include_trace,
        user_intent=message,
        midi_filename=midi_file.filename if midi_file else "",
        analyze_result=analyze_result,
        lint_payload=lint_payload,
        revision_payload=revision_payload,
        update_intent_to=message,
        generation_intent=message,
    )


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
    conv = _require_conversation(conversation_id)

    conversation_manager.update_version_feedback(
        conversation_id=conversation_id,
        version_id=version_id,
        feedback=feedback
    )

    _record_user_message(conversation_id, f"[反馈 v{version_id}]: {feedback}")

    return JSONResponse(
        content=_build_feedback_recorded_response(conversation_id, version_id)
    )


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
    conv = _require_conversation(conversation_id)

    tracer = _start_conversation_trace(conversation_id, "regeneration")

    # 获取所有版本的反馈
    previous_feedback = _collect_previous_feedback(conv)

    if not previous_feedback:
        raise HTTPException(status_code=400, detail="No feedback available for regeneration")

    # 使用当前生效意图，避免多轮收敛后回退到初始目标
    current_intent = conv.get("current_intent") or conv.get("initial_intent", "")

    # 分析 MIDI（如果提供），否则复用最近保存的分析结果
    analyze_result = await _resolve_regenerate_analyze_result(
        conversation_id,
        conv,
        midi_file,
        tracer,
    )

    # 调用 LLM 生成方案
    tracer.start_stage("plan_generation")
    planner = LLMPlanner(conversation_id=conversation_id)

    plan = planner.generate_plan(
        analyze_result=analyze_result,
        user_intent=current_intent,
        previous_feedback=previous_feedback
    )

    return _finalize_generated_plan_response(
        conversation_id=conversation_id,
        plan=plan,
        tracer=tracer,
        include_trace=include_trace,
        feedback_used=previous_feedback,
        generation_intent=current_intent,
    )


@app.get("/conversation/{conversation_id}/trace")
async def get_trace(conversation_id: str):
    """获取会话的完整追踪日志"""
    conv = _require_conversation(conversation_id)

    tracer = get_tracer(conversation_id)
    trace_data = tracer.export()

    return JSONResponse(content=_build_trace_payload(trace_data))


@app.get("/conversation/{conversation_id}/history")
async def get_history(conversation_id: str):
    """获取会话的完整历史"""
    conv = _require_conversation(conversation_id)

    return JSONResponse(content=_build_history_payload(conversation_id, conv))


@app.get("/conversation/{conversation_id}/export")
async def export_conversation(conversation_id: str):
    """导出会话完整记录"""
    conv = _require_conversation(conversation_id)
    return JSONResponse(content=_export_conversation_data(conversation_id))


@app.get("/conversations")
async def list_conversations():
    """列出所有会话"""
    convs = conversation_manager.list_conversations()
    return JSONResponse(content=_build_conversations_payload(convs))


@app.get("/session/{conversation_id}/versions")
async def get_session_versions(conversation_id: str):
    """获取会话的所有版本日志"""
    logs = session_logger.get_session_logs(conversation_id)
    return JSONResponse(content=_build_session_versions_payload(conversation_id, logs))


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
    log = _require_session_log(conversation_id, version_id)
    return JSONResponse(content=_build_session_log_payload(log))


@app.get("/sessions")
async def list_sessions():
    """列出所有会话（基于 session_logger）"""
    sessions = session_logger.list_sessions()
    return JSONResponse(content=_build_sessions_payload(sessions))


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

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic import ValidationError

from dsa_tutor_code_optimizer.crew import DsaTutorCodeOptimizerCrew
from dsa_tutor_code_optimizer.schemas import OptimizeCodeRequest
from dsa_tutor_code_optimizer.schemas import OptimizeCodeResponse
from dsa_tutor_code_optimizer.schemas import SwarmOptimizationResult

logger = logging.getLogger("dsa_tutor.api")
if not logger.handlers:
    logging.basicConfig(
        level=os.getenv("DSA_TUTOR_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _load_gemini_key_pool() -> list[str]:
    raw_pool = os.getenv("GEMINI_API_KEYS", "").strip()
    pool = [k.strip() for k in raw_pool.split(",") if k.strip()] if raw_pool else []
    active = os.getenv("GEMINI_API_KEY", "").strip()
    if active and active not in pool:
        pool.insert(0, active)
    return pool


_GEMINI_KEY_POOL: list[str] = _load_gemini_key_pool()
_GEMINI_KEY_INDEX: int = 0

_GEMINI_MODEL_POOL: list[str] = [
    "gemini/gemini-flash-latest",
    "gemini/gemini-flash-lite-latest",
    "gemini/gemini-2.5-flash-lite",
    "gemini/gemini-2.5-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3.1-flash-lite-preview",
]
_GEMINI_MODEL_INDEX: int = 0

if _GEMINI_KEY_POOL:
    os.environ["GEMINI_API_KEY"] = _GEMINI_KEY_POOL[0]
    os.environ["DSA_TUTOR_GEMINI_MODEL"] = _GEMINI_MODEL_POOL[0]
    logger.info(
        "gemini_pool keys=%d models=%d",
        len(_GEMINI_KEY_POOL),
        len(_GEMINI_MODEL_POOL),
    )


def _vision_model() -> str:
    prefixed = os.environ.get("DSA_TUTOR_GEMINI_MODEL", _GEMINI_MODEL_POOL[0])
    return prefixed.split("/", 1)[-1]


def _rotate_gemini_key() -> bool:
    """Advance to the next key. Returns True if we moved to a new key in the current model's cycle."""
    global _GEMINI_KEY_INDEX
    if len(_GEMINI_KEY_POOL) <= 1:
        return False
    next_index = (_GEMINI_KEY_INDEX + 1) % len(_GEMINI_KEY_POOL)
    if next_index == 0:
        return False
    _GEMINI_KEY_INDEX = next_index
    new_key = _GEMINI_KEY_POOL[_GEMINI_KEY_INDEX]
    os.environ["GEMINI_API_KEY"] = new_key
    logger.warning(
        "gemini_key_rotated index=%d suffix=%s",
        _GEMINI_KEY_INDEX,
        new_key[-4:] if len(new_key) >= 4 else "****",
    )
    return True


def _rotate_gemini_model() -> bool:
    """Advance to next model and reset key index. Returns True if a new model was selected."""
    global _GEMINI_MODEL_INDEX, _GEMINI_KEY_INDEX
    if _GEMINI_MODEL_INDEX + 1 >= len(_GEMINI_MODEL_POOL):
        return False
    _GEMINI_MODEL_INDEX += 1
    _GEMINI_KEY_INDEX = 0
    new_model = _GEMINI_MODEL_POOL[_GEMINI_MODEL_INDEX]
    os.environ["DSA_TUTOR_GEMINI_MODEL"] = new_model
    if _GEMINI_KEY_POOL:
        os.environ["GEMINI_API_KEY"] = _GEMINI_KEY_POOL[0]
    logger.warning("gemini_model_rotated index=%d model=%s", _GEMINI_MODEL_INDEX, new_model)
    return True


def _rotate_on_quota() -> bool:
    """Try a fresh key first; if exhausted, move to the next model."""
    if _rotate_gemini_key():
        return True
    return _rotate_gemini_model()


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "429" in message
        or "resource_exhausted" in message
        or "quota" in message
        or "rate limit" in message
    )


_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "overloaded", "try again")


def _is_transient_upstream_error(exc: Exception) -> bool:
    message = str(exc)
    return any(marker.lower() in message.lower() for marker in _TRANSIENT_MARKERS)


_SINGLE_SHOT_PROMPT = """You are a C++ performance engineer. Analyze the following C++ source code, \
then produce an optimized version and return STRICT JSON (no markdown fences, no commentary, no prose).

The JSON MUST conform to this TypeScript shape exactly:

{
  "status": "success" | "failed",
  "problem_summary": string,
  "original_code": string,                         // echo the original code verbatim
  "optimized_code": string,                        // your improved C++ code
  "complexity": {
    "original_time_complexity": string,            // e.g. "O(n^2)"
    "optimized_time_complexity": string,           // e.g. "O(n log n)"
    "original_space_complexity": string,
    "optimized_space_complexity": string,
    "estimated_speedup_ratio": number              // >= 1.0
  },
  "algorithm_choices": string[],
  "optimization_notes": string[],
  "correctness_notes": string,
  "compiler_attempts": [                           // at least one synthetic entry
    { "attempt": 1, "success": true, "compiler_stdout": "", "compiler_stderr": "",
      "run_stdout": null, "run_stderr": "", "exit_code": 0 }
  ],
  "visualization": {
    "chart_type": "line",
    "chart_title": string,
    "x_key": "input_size",
    "y_keys": ["brute_force_ops", "optimized_ops"],
    "points": [                                    // 7-9 points; input_size >= 1, ops >= 0
      { "input_size": 10,   "brute_force_ops": number, "optimized_ops": number },
      { "input_size": 100,  "brute_force_ops": number, "optimized_ops": number },
      { "input_size": 1000, "brute_force_ops": number, "optimized_ops": number }
    ]
  }
}

Compute the ops values from the Big-O formulas (brute_force_ops from original complexity, \
optimized_ops from optimized complexity). Use input_size values that span 10 -> 100000.
Return ONLY the JSON object.

C++ SOURCE:
```cpp
{cpp_code}
```
"""


def _extract_json_blob(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        first_newline = stripped.find("\n")
        if first_newline != -1:
            first_line = stripped[:first_newline].strip().lower()
            if first_line in {"json"}:
                stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    stripped = stripped.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _single_shot_optimize(cpp_code: str) -> SwarmOptimizationResult:
    from google import genai

    prompt = _SINGLE_SHOT_PROMPT.replace("{cpp_code}", cpp_code)

    last_error: Exception | None = None
    attempts = max(1, len(_GEMINI_KEY_POOL) * len(_GEMINI_MODEL_POOL))
    for _ in range(attempts):
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model=_vision_model(),
                contents=[prompt],
            )
            raw_text = response.text or ""
            blob = _extract_json_blob(raw_text)
            data = json.loads(blob)
            if "original_code" not in data or not data.get("original_code"):
                data["original_code"] = cpp_code
            return SwarmOptimizationResult.model_validate(data)
        except Exception as exc:
            last_error = exc
            if _is_quota_error(exc) and _rotate_on_quota():
                logger.warning("single_shot_optimize quota_exhausted rotated")
                continue
            if _is_transient_upstream_error(exc):
                time.sleep(8)
                continue
            break

    raise RuntimeError(
        f"Single-shot optimizer failed after {attempts} attempts: {last_error}"
    )


app = FastAPI(
    title="DSA Tutor and Code Optimizer API",
    version="0.1.0",
    description=(
        "FastAPI bridge for CrewAI swarm that optimizes C++ code and returns "
        "structured visualization payloads."
    ),
)


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("DSA_TUTOR_CORS_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _coerce_result_to_model(
    result: Any, original_code: str
) -> SwarmOptimizationResult:
    pydantic_payload = getattr(result, "pydantic", None)
    if pydantic_payload is not None:
        if isinstance(pydantic_payload, SwarmOptimizationResult):
            return pydantic_payload
        if hasattr(pydantic_payload, "model_dump"):
            return SwarmOptimizationResult.model_validate(pydantic_payload.model_dump())

    json_dict = getattr(result, "json_dict", None)
    if json_dict:
        return SwarmOptimizationResult.model_validate(json_dict)

    raw = getattr(result, "raw", None)
    if isinstance(raw, str) and raw.strip():
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:]
            stripped = stripped.strip()
        return SwarmOptimizationResult.model_validate(json.loads(stripped))

    raise ValueError(
        "Crew output could not be parsed into SwarmOptimizationResult. "
        f"Original code length: {len(original_code)}"
    )


_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


class ExtractCodeResponse(BaseModel):
    cpp_code: str


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        first_newline = stripped.find("\n")
        if first_newline != -1:
            first_line = stripped[:first_newline].strip().lower()
            if first_line in {"cpp", "c++", "c"}:
                stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


@app.get("/healthz")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/extract-cpp-from-image", response_model=ExtractCodeResponse)
async def extract_cpp_from_image(file: UploadFile = File(...)) -> ExtractCodeResponse:
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured.")

    mime_type = (file.content_type or "").lower()
    if mime_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {mime_type or 'unknown'}. Use PNG, JPEG, WEBP, GIF, or BMP.",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 8 MB limit.")

    from google import genai
    from google.genai import types as genai_types

    prompt = (
        "Extract only the C++ source code visible in this image. "
        "Return just the raw code with no commentary, no explanation, "
        "and no markdown fences. If the image contains no C++ code, "
        "return an empty response."
    )
    image_part = genai_types.Part.from_bytes(data=data, mime_type=mime_type)

    extracted = ""
    attempts = max(1, len(_GEMINI_KEY_POOL) * len(_GEMINI_MODEL_POOL))
    last_error: Exception | None = None
    for _attempt in range(attempts):
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model=_vision_model(),
                contents=[image_part, prompt],
            )
            extracted = _strip_code_fences(response.text or "")
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if _is_quota_error(exc) and _rotate_on_quota():
                logger.warning("extract_cpp_from_image quota_exhausted rotated")
                continue
            break

    if last_error is not None:
        logger.exception("extract_cpp_from_image failure")
        raise HTTPException(
            status_code=502, detail=f"Gemini vision call failed: {last_error}"
        )

    if not extracted:
        raise HTTPException(
            status_code=422,
            detail="No C++ code could be extracted from the image.",
        )

    return ExtractCodeResponse(cpp_code=extracted)


def _run_crew_with_failover(payload: OptimizeCodeRequest, request_id) -> SwarmOptimizationResult:
    max_attempts = max(3, len(_GEMINI_KEY_POOL) * len(_GEMINI_MODEL_POOL) + 1)
    backoff_seconds = 12
    crew_result = None
    for attempt in range(1, max_attempts + 1):
        try:
            crew_result = DsaTutorCodeOptimizerCrew().crew().kickoff(
                inputs={
                    "cpp_code": payload.cpp_code,
                    "stdin_data": payload.stdin_data,
                    "max_self_correction_attempts": payload.max_self_correction_attempts,
                }
            )
            break
        except Exception as exc:
            if attempt >= max_attempts:
                raise
            if _is_quota_error(exc) and _rotate_on_quota():
                logger.warning(
                    "optimize_code request_id=%s quota_exhausted attempt=%d rotated",
                    request_id, attempt,
                )
                continue
            if _is_transient_upstream_error(exc):
                wait = backoff_seconds * attempt
                logger.warning(
                    "optimize_code request_id=%s transient attempt=%d waiting=%ds",
                    request_id, attempt, wait,
                )
                time.sleep(wait)
                continue
            raise
    return _coerce_result_to_model(crew_result, payload.cpp_code)


@app.post("/v1/optimize-code", response_model=OptimizeCodeResponse)
def optimize_code(payload: OptimizeCodeRequest) -> OptimizeCodeResponse:
    request_id = uuid4()
    started_at = time.perf_counter()
    logger.info("optimize_code request_id=%s cpp_code_len=%d", request_id, len(payload.cpp_code))

    use_crew = os.getenv("DSA_TUTOR_USE_CREW", "0") == "1"
    result: SwarmOptimizationResult | None = None

    if use_crew:
        try:
            result = _run_crew_with_failover(payload, request_id)
        except Exception as exc:
            logger.warning(
                "optimize_code request_id=%s crew_failed fallback_to_single_shot err=%s",
                request_id, exc,
            )

    if result is None:
        try:
            result = _single_shot_optimize(payload.cpp_code)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("optimize_code request_id=%s contract_error=%s", request_id, exc)
            raise HTTPException(
                status_code=502, detail=f"Invalid model output contract: {exc}"
            )
        except RuntimeError as exc:
            logger.error("optimize_code request_id=%s runtime_error=%s", request_id, exc)
            raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            logger.exception("optimize_code request_id=%s pipeline_failure", request_id)
            raise HTTPException(
                status_code=500, detail=f"Optimization pipeline failed: {exc}"
            )

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "optimize_code request_id=%s completed elapsed_ms=%d status=%s",
        request_id, elapsed_ms, result.status,
    )
    return OptimizeCodeResponse(request_id=request_id, result=result)


def run_dev_server() -> None:
    import uvicorn

    uvicorn.run(
        "dsa_tutor_code_optimizer.api:app",
        host="0.0.0.0",
        port=int(os.getenv("DSA_TUTOR_API_PORT", "8000")),
        reload=True,
    )

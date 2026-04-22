from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


MAX_CPP_CODE_LENGTH = 200_000
MAX_STDIN_LENGTH = 65_536
MAX_TEXT_FIELD_LENGTH = 4_000
MAX_COMPILER_LOG_LENGTH = 20_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OptimizeCodeRequest(StrictModel):
    cpp_code: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CPP_CODE_LENGTH,
        description="Raw C++ code from the user.",
    )
    stdin_data: str = Field(
        default="",
        max_length=MAX_STDIN_LENGTH,
        description="Optional stdin passed to the executable.",
    )
    max_self_correction_attempts: int = Field(
        default=3,
        ge=1,
        le=8,
        description="Max compile-fix iterations requested from the optimizer agent.",
    )


class ComplexityComparison(StrictModel):
    original_time_complexity: str = Field(..., min_length=1, max_length=512)
    optimized_time_complexity: str = Field(..., min_length=1, max_length=512)
    original_space_complexity: str = Field(..., min_length=1, max_length=512)
    optimized_space_complexity: str = Field(..., min_length=1, max_length=512)
    estimated_speedup_ratio: float = Field(..., ge=1.0, le=1e9)


class ComplexityAnalysisOutput(StrictModel):
    original_time_complexity: str = Field(..., min_length=1, max_length=512)
    original_space_complexity: str = Field(..., min_length=1, max_length=512)
    bottlenecks: list[str]
    rationale: str = Field(..., max_length=MAX_TEXT_FIELD_LENGTH)


class AlgorithmResearchOutput(StrictModel):
    recommended_approach: str = Field(..., max_length=MAX_TEXT_FIELD_LENGTH)
    data_structures: list[str]
    expected_time_complexity: str = Field(..., min_length=1, max_length=512)
    expected_space_complexity: str = Field(..., min_length=1, max_length=512)
    implementation_plan: list[str]


class CompilationAttempt(StrictModel):
    attempt: int = Field(..., ge=1)
    success: bool
    compiler_stdout: str = Field(default="", max_length=MAX_COMPILER_LOG_LENGTH)
    compiler_stderr: str = Field(default="", max_length=MAX_COMPILER_LOG_LENGTH)
    run_stdout: str | None = Field(default=None, max_length=MAX_COMPILER_LOG_LENGTH)
    run_stderr: str | None = Field(default=None, max_length=MAX_COMPILER_LOG_LENGTH)
    exit_code: int | None = None


class CodeOptimizationOutput(StrictModel):
    optimized_code: str = Field(..., min_length=1, max_length=MAX_CPP_CODE_LENGTH)
    optimization_notes: list[str]
    correctness_strategy: str = Field(..., max_length=MAX_TEXT_FIELD_LENGTH)
    complexity: ComplexityComparison
    compiler_attempts: list[CompilationAttempt]


class ChartPoint(StrictModel):
    input_size: int = Field(..., ge=1)
    brute_force_ops: float = Field(..., ge=0.0)
    optimized_ops: float = Field(..., ge=0.0)


class RechartsVisualization(StrictModel):
    chart_type: Literal["line"] = "line"
    chart_title: str = Field(..., min_length=1, max_length=200)
    x_key: Literal["input_size"] = "input_size"
    y_keys: list[Literal["brute_force_ops", "optimized_ops"]] = [
        "brute_force_ops",
        "optimized_ops",
    ]
    points: list[ChartPoint] = Field(..., min_length=1, max_length=512)


class SwarmOptimizationResult(StrictModel):
    status: Literal["success", "failed"]
    problem_summary: str = Field(..., max_length=MAX_TEXT_FIELD_LENGTH)
    original_code: str = Field(..., max_length=MAX_CPP_CODE_LENGTH)
    optimized_code: str = Field(..., max_length=MAX_CPP_CODE_LENGTH)
    complexity: ComplexityComparison
    algorithm_choices: list[str]
    optimization_notes: list[str]
    correctness_notes: str = Field(..., max_length=MAX_TEXT_FIELD_LENGTH)
    compiler_attempts: list[CompilationAttempt]
    visualization: RechartsVisualization


class OptimizeCodeResponse(StrictModel):
    request_id: UUID
    result: SwarmOptimizationResult

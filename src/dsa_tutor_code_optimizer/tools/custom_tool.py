from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from typing import Literal
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator


_ALLOWED_OPTIMIZATION_LEVELS = {"O0", "O1", "O2", "O3", "Os", "Ofast"}
_ALLOWED_CPP_STANDARDS = {
    "c++11",
    "c++14",
    "c++17",
    "c++20",
    "c++23",
    "gnu++17",
    "gnu++20",
}
_MAX_SOURCE_BYTES = 200_000
_MAX_STDIN_BYTES = 65_536


class CppCompilerToolInput(BaseModel):
    source_code: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_SOURCE_BYTES,
        description="C++ source code to compile and execute.",
    )
    stdin_data: str = Field(
        default="",
        max_length=_MAX_STDIN_BYTES,
        description="Optional stdin passed to executable.",
    )
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    optimization_level: str = Field(
        default="O2",
        description="Compiler optimization level. One of O0, O1, O2, O3, Os, Ofast.",
    )
    cpp_standard: str = Field(
        default="c++17",
        description="C++ language standard, e.g. c++17, c++20, gnu++20.",
    )

    @field_validator("optimization_level")
    @classmethod
    def _validate_optimization_level(cls, value: str) -> str:
        if value not in _ALLOWED_OPTIMIZATION_LEVELS:
            allowed = ", ".join(sorted(_ALLOWED_OPTIMIZATION_LEVELS))
            raise ValueError(f"optimization_level must be one of: {allowed}")
        return value

    @field_validator("cpp_standard")
    @classmethod
    def _validate_cpp_standard(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in _ALLOWED_CPP_STANDARDS:
            allowed = ", ".join(sorted(_ALLOWED_CPP_STANDARDS))
            raise ValueError(f"cpp_standard must be one of: {allowed}")
        return normalized


class CppCompilerTool(BaseTool):
    name: str = "cpp_compiler_tool"
    description: str = (
        "Compiles and optionally executes C++ code in a temporary sandbox. "
        "Returns a JSON payload containing compiler output, runtime output, and exit status."
    )
    args_schema: Type[BaseModel] = CppCompilerToolInput

    def _run(
        self,
        source_code: str,
        stdin_data: str = "",
        timeout_seconds: int = 5,
        optimization_level: str = "O2",
        cpp_standard: str = "c++17",
    ) -> str:
        start = time.perf_counter()
        result: dict[str, Any] = {
            "compile_success": False,
            "run_success": False,
            "compiler_stdout": "",
            "compiler_stderr": "",
            "run_stdout": "",
            "run_stderr": "",
            "exit_code": None,
            "elapsed_ms": 0,
        }

        try:
            with tempfile.TemporaryDirectory(prefix="cpp_compile_") as work_dir:
                work_path = Path(work_dir)
                source_path = work_path / "main.cpp"
                binary_name = "program.exe" if os.name == "nt" else "program"
                binary_path = work_path / binary_name

                source_path.write_text(source_code, encoding="utf-8")

                compile_command = [
                    "g++",
                    f"-std={cpp_standard}",
                    f"-{optimization_level}",
                    str(source_path),
                    "-o",
                    str(binary_path),
                ]

                compile_process = subprocess.run(
                    compile_command,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                result["compiler_stdout"] = compile_process.stdout
                result["compiler_stderr"] = compile_process.stderr

                if compile_process.returncode != 0:
                    result["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                    return json.dumps(result)

                result["compile_success"] = True

                run_process = subprocess.run(
                    [str(binary_path)],
                    input=stdin_data,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )

                result["run_stdout"] = run_process.stdout
                result["run_stderr"] = run_process.stderr
                result["exit_code"] = run_process.returncode
                result["run_success"] = run_process.returncode == 0
                result["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return json.dumps(result)

        except FileNotFoundError:
            result["compiler_stderr"] = (
                "g++ compiler was not found. Install GCC/G++ and ensure it is on PATH."
            )
        except subprocess.TimeoutExpired:
            result["compiler_stderr"] = (
                "Compilation or execution timed out. Consider reducing input size or code complexity."
            )
        except Exception as exc:  # pragma: no cover
            result["compiler_stderr"] = f"Unexpected compiler tool failure: {exc}"

        result["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        return json.dumps(result)


ComplexityClass = Literal[
    "constant",
    "log",
    "sqrt",
    "linear",
    "linearithmic",
    "quadratic",
    "cubic",
    "exponential",
    "factorial",
]


_COMPLEXITY_PATTERNS: list[tuple[re.Pattern[str], ComplexityClass]] = [
    (re.compile(r"(?:^|[^a-z])n!"), "factorial"),
    (re.compile(r"(?:2|c)\s*\^\s*n|2\*\*n"), "exponential"),
    (re.compile(r"n\s*\^\s*3|n3(?!\w)"), "cubic"),
    (re.compile(r"n\s*\^\s*2|n2(?!\w)"), "quadratic"),
    (re.compile(r"n\s*\*?\s*log\s*\*?\s*2?\s*n|nlog\s*n"), "linearithmic"),
    (re.compile(r"sqrt\(?n\)?|n\s*\^\s*0?\.5"), "sqrt"),
    (re.compile(r"log\s*\*?\s*2?\s*n|log\s*\(n\)"), "log"),
    (re.compile(r"(?:^|[^a-z])n(?!\w)"), "linear"),
    (re.compile(r"^o?\(?\s*1\s*\)?$|^o?\(?c\)?$"), "constant"),
]


def classify_complexity(complexity: str) -> ComplexityClass:
    """Classify a Big-O string into a coarse complexity bucket.

    Falls back to ``"quadratic"`` so an unexpected LLM string still produces a plot.
    """
    normalized = complexity.lower().replace(" ", "")
    for pattern, label in _COMPLEXITY_PATTERNS:
        if pattern.search(normalized):
            return label
    return "quadratic"


def _estimate_for_class(klass: ComplexityClass, n: int) -> float:
    safe_n = max(n, 1)
    log_n = math.log2(max(safe_n, 2))
    if klass == "constant":
        return 1.0
    if klass == "log":
        return log_n
    if klass == "sqrt":
        return math.sqrt(safe_n)
    if klass == "linear":
        return float(safe_n)
    if klass == "linearithmic":
        return safe_n * log_n
    if klass == "quadratic":
        return float(safe_n) ** 2
    if klass == "cubic":
        return float(safe_n) ** 3
    if klass == "exponential":
        # Cap the exponent so the chart remains renderable for moderate n.
        return 2.0 ** min(safe_n, 60)
    if klass == "factorial":
        return math.factorial(min(safe_n, 20))
    return float(safe_n) ** 2


class ComplexityCurveToolInput(BaseModel):
    original_time_complexity: str = Field(..., description="Big-O string for original code.")
    optimized_time_complexity: str = Field(..., description="Big-O string for optimized code.")
    input_sizes: list[int] = Field(default_factory=lambda: [16, 64, 256, 1024, 4096])


class ComplexityCurveTool(BaseTool):
    name: str = "complexity_curve_tool"
    description: str = (
        "Generates deterministic operation-count points for Recharts based on "
        "original and optimized Big-O complexity."
    )
    args_schema: Type[BaseModel] = ComplexityCurveToolInput

    def _run(
        self,
        original_time_complexity: str,
        optimized_time_complexity: str,
        input_sizes: list[int] | None = None,
    ) -> str:
        sizes = [size for size in (input_sizes or [16, 64, 256, 1024, 4096]) if size > 0]
        if not sizes:
            sizes = [16, 64, 256, 1024, 4096]

        original_class = classify_complexity(original_time_complexity)
        optimized_class = classify_complexity(optimized_time_complexity)

        points: list[dict[str, float | int]] = []
        for n in sorted(sizes):
            brute_force_ops = _estimate_for_class(original_class, n)
            optimized_ops = _estimate_for_class(optimized_class, n)
            points.append(
                {
                    "input_size": n,
                    "brute_force_ops": round(brute_force_ops, 2),
                    "optimized_ops": round(optimized_ops, 2),
                }
            )

        return json.dumps(
            {
                "chart_type": "line",
                "x_key": "input_size",
                "y_keys": ["brute_force_ops", "optimized_ops"],
                "points": points,
            }
        )

    @staticmethod
    def _estimate_operations(complexity: str, n: int) -> float:
        """Backward-compatible shim kept for any direct callers."""
        return _estimate_for_class(classify_complexity(complexity), n)

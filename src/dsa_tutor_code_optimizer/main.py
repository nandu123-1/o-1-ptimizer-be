#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from dsa_tutor_code_optimizer.crew import DsaTutorCodeOptimizerCrew

DEFAULT_SAMPLE_CPP = """#include <bits/stdc++.h>
using namespace std;

int main() {
    vector<int> nums = {2, 7, 11, 15};
    int target = 9;
    for (size_t i = 0; i < nums.size(); ++i) {
        for (size_t j = i + 1; j < nums.size(); ++j) {
            if (nums[i] + nums[j] == target) {
                cout << i << " " << j << "\\n";
                return 0;
            }
        }
    }
    return 0;
}
"""


def _default_inputs(max_attempts: int = 3) -> dict[str, object]:
    return {
        "cpp_code": DEFAULT_SAMPLE_CPP,
        "stdin_data": "",
        "max_self_correction_attempts": max_attempts,
    }


def _parse_positional(expected: int, command: str) -> list[str]:
    """Read positional args for console-script entry points.

    Console scripts in ``pyproject.toml`` invoke these functions with no
    arguments, so we read from ``sys.argv`` directly. ``sys.argv[0]`` is the
    script name and the following entries are the positional arguments.
    """
    args = sys.argv[1:]
    if len(args) < expected:
        raise SystemExit(
            f"Usage: {command} " + " ".join(f"<arg{i + 1}>" for i in range(expected))
        )
    return args[:expected]


def run() -> None:
    DsaTutorCodeOptimizerCrew().crew().kickoff(inputs=_default_inputs())


def run_with_trigger() -> None:
    run()


def train() -> None:
    raw_n_iterations, filename = _parse_positional(2, "train")
    try:
        n_iterations = int(raw_n_iterations)
    except ValueError as exc:
        raise SystemExit(f"train: n_iterations must be an integer, got {raw_n_iterations!r}") from exc

    try:
        DsaTutorCodeOptimizerCrew().crew().train(
            n_iterations=n_iterations,
            filename=filename,
            inputs=_default_inputs(),
        )
    except Exception as exc:
        raise RuntimeError(f"An error occurred while training the crew: {exc}") from exc


def replay() -> None:
    (task_id,) = _parse_positional(1, "replay")
    try:
        DsaTutorCodeOptimizerCrew().crew().replay(task_id=task_id)
    except Exception as exc:
        raise RuntimeError(f"An error occurred while replaying the crew: {exc}") from exc


def test() -> None:
    raw_n_iterations, openai_model_name = _parse_positional(2, "test")
    try:
        n_iterations = int(raw_n_iterations)
    except ValueError as exc:
        raise SystemExit(f"test: n_iterations must be an integer, got {raw_n_iterations!r}") from exc

    try:
        DsaTutorCodeOptimizerCrew().crew().test(
            n_iterations=n_iterations,
            openai_model_name=openai_model_name,
            inputs=_default_inputs(),
        )
    except Exception as exc:
        raise RuntimeError(f"An error occurred while testing the crew: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dsa-tutor-code-optimizer",
        description="DSA Tutor and C++ Code Optimizer CrewAI CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Run the optimizer crew with the bundled sample.")
    sub.add_parser("run_with_trigger", help="Alias for run.")

    train_parser = sub.add_parser("train", help="Train the crew for N iterations.")
    train_parser.add_argument("n_iterations", type=int)
    train_parser.add_argument("filename", type=str)

    replay_parser = sub.add_parser("replay", help="Replay a previous task by id.")
    replay_parser.add_argument("task_id", type=str)

    test_parser = sub.add_parser("test", help="Run the crew in test mode.")
    test_parser.add_argument("n_iterations", type=int)
    test_parser.add_argument("openai_model_name", type=str)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command in {"run", "run_with_trigger"}:
        run()
    elif args.command == "train":
        sys.argv = [sys.argv[0], str(args.n_iterations), args.filename]
        train()
    elif args.command == "replay":
        sys.argv = [sys.argv[0], args.task_id]
        replay()
    elif args.command == "test":
        sys.argv = [sys.argv[0], str(args.n_iterations), args.openai_model_name]
        test()
    else:
        parser.error(f"Unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

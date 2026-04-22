import os
from pathlib import Path
from typing import List

from crewai import Agent
from crewai import Crew
from crewai import LLM
from crewai import Process
from crewai import Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import ArxivPaperTool, SerperDevTool

from dsa_tutor_code_optimizer.schemas import AlgorithmResearchOutput
from dsa_tutor_code_optimizer.schemas import CodeOptimizationOutput
from dsa_tutor_code_optimizer.schemas import ComplexityAnalysisOutput
from dsa_tutor_code_optimizer.schemas import SwarmOptimizationResult
from dsa_tutor_code_optimizer.tools import ComplexityCurveTool
from dsa_tutor_code_optimizer.tools import CppCompilerTool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def _hydrate_env_from_project_file() -> None:
    if os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS"):
        return
    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        cleaned_key = key.strip()
        cleaned_value = value.strip().strip('"').strip("'")

        if cleaned_key and cleaned_key not in os.environ:
            os.environ[cleaned_key] = cleaned_value


_hydrate_env_from_project_file()


@CrewBase
class DsaTutorCodeOptimizerCrew:
    """DSA Tutor and Code Optimizer swarm."""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @staticmethod
    def _default_llm() -> LLM:
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Configure it in your shell environment "
                f"or create {ENV_FILE} with GEMINI_API_KEY=<your_key>, then restart "
                "the backend server."
            )
        model = os.getenv("DSA_TUTOR_GEMINI_MODEL", "gemini/gemini-flash-latest")
        return LLM(model=model, temperature=0)

    @agent
    def c_code_complexity_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config["c_code_complexity_analyzer"],  # type: ignore[index]
            llm=self._default_llm(),
            allow_delegation=False,
            inject_date=True,
            reasoning=False,
            max_iter=4,
            verbose=True,
        )

    @agent
    def algorithm_research_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["algorithm_research_specialist"],  # type: ignore[index]
            llm=self._default_llm(),
            tools=[SerperDevTool(), ArxivPaperTool()],
            allow_delegation=False,
            inject_date=True,
            reasoning=False,
            max_iter=4,
            verbose=True,
        )

    @agent
    def c_code_optimizer(self) -> Agent:
        return Agent(
            config=self.agents_config["c_code_optimizer"],  # type: ignore[index]
            llm=self._default_llm(),
            tools=[CppCompilerTool()],
            allow_delegation=False,
            inject_date=True,
            reasoning=False,
            max_iter=6,
            verbose=True,
        )

    @agent
    def algorithm_visualization_expert(self) -> Agent:
        return Agent(
            config=self.agents_config["algorithm_visualization_expert"],  # type: ignore[index]
            llm=self._default_llm(),
            tools=[ComplexityCurveTool()],
            allow_delegation=False,
            inject_date=True,
            max_iter=4,
            verbose=True,
        )

    @task
    def analyze_code_complexity(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_code_complexity"],  # type: ignore[index]
            output_pydantic=ComplexityAnalysisOutput,
            markdown=False,
        )

    @task
    def research_optimal_algorithms(self) -> Task:
        return Task(
            config=self.tasks_config["research_optimal_algorithms"],  # type: ignore[index]
            output_pydantic=AlgorithmResearchOutput,
            markdown=False,
        )

    @task
    def optimize_code_implementation(self) -> Task:
        return Task(
            config=self.tasks_config["optimize_code_implementation"],  # type: ignore[index]
            output_pydantic=CodeOptimizationOutput,
            markdown=False,
            guardrail_max_retries=3,
        )

    @task
    def generate_algorithm_visualization(self) -> Task:
        return Task(
            config=self.tasks_config["generate_algorithm_visualization"],  # type: ignore[index]
            output_pydantic=SwarmOptimizationResult,
            markdown=False,
            guardrail_max_retries=3,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            planning=False,
            stream=False,
            verbose=True,
            max_rpm=8,
            chat_llm=self._default_llm(),
        )



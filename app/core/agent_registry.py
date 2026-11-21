"""
Agent Registry (Phase 7)
========================
Defines the central catalog of all 6 specialized platform agents:
1. Agent 1: Learner Profiling Agent
2. Agent 2: Adaptive Learning Path Agent
3. Agent 3: AI Socratic Tutor Agent
4. Agent 4: Real-World Scenario Generation Agent
5. Agent 5: AI Interview & Project Mentor Agent
6. Agent 6: Evaluation & Competency Intelligence Agent

Each agent has strict responsibility definitions, input/output schemas,
context requirements (data minimisation contract), timeouts, retries, and rate limits.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


# ------------------------------------------------------------------------------
# Agent Identifiers
# ------------------------------------------------------------------------------
AGENT_LEARNER_PROFILER = "agent_learner_profiler"
AGENT_ADAPTIVE_PATH = "agent_adaptive_path"
AGENT_AI_TUTOR = "agent_ai_tutor"
AGENT_SCENARIO_GEN = "agent_scenario_generation"
AGENT_INTERVIEW_MENTOR = "agent_interview_project_mentor"
AGENT_COMPETENCY_INTEL = "agent_competency_intelligence"


@dataclass
class AgentDefinition:
    agent_id: str
    name: str
    phase: int
    responsibility: str
    required_context_fields: List[str]
    execution_timeout_seconds: float = 10.0
    max_retries: int = 2
    rate_limit_per_min: int = 30
    max_tokens_budget: int = 2000
    fallback_supported: bool = True
    input_fields: List[str] = field(default_factory=list)
    required_output_fields: List[str] = field(default_factory=list)


# ------------------------------------------------------------------------------
# Central Agent Catalog
# ------------------------------------------------------------------------------
AGENT_CATALOG: Dict[str, AgentDefinition] = {
    AGENT_LEARNER_PROFILER: AgentDefinition(
        agent_id=AGENT_LEARNER_PROFILER,
        name="Learner Profiling Agent",
        phase=1,
        responsibility="Analyzes career objectives, self-reported skills, and baseline assessments into structured competency models.",
        required_context_fields=["user_id", "target_role", "target_level", "years_of_experience"],
        execution_timeout_seconds=8.0,
        max_retries=2,
        rate_limit_per_min=20,
        max_tokens_budget=1500,
        input_fields=["target_role", "target_level", "skills"],
        required_output_fields=["profile_id", "target_role", "competencies"],
    ),
    AGENT_ADAPTIVE_PATH: AgentDefinition(
        agent_id=AGENT_ADAPTIVE_PATH,
        name="Adaptive Learning Path Agent",
        phase=2,
        responsibility="Synthesizes and adaptively updates personalized modular roadmaps with difficulty pacing and prerequisite sequencing.",
        required_context_fields=["user_id", "target_role", "target_level", "skill_gaps", "active_roadmap_id"],
        execution_timeout_seconds=12.0,
        max_retries=2,
        rate_limit_per_min=15,
        max_tokens_budget=3000,
        input_fields=["target_role", "target_level", "focus_skills"],
        required_output_fields=["roadmap_id", "title", "modules"],
    ),
    AGENT_AI_TUTOR: AgentDefinition(
        agent_id=AGENT_AI_TUTOR,
        name="AI Socratic Tutor Agent",
        phase=3,
        responsibility="Context-aware socratic tutoring, step-by-step guidance, and code debugging without raw solution copy-pastes.",
        required_context_fields=["roadmap_id", "activity_id", "concept", "skill_level", "recent_dialogue"],
        execution_timeout_seconds=10.0,
        max_retries=2,
        rate_limit_per_min=40,
        max_tokens_budget=2000,
        input_fields=["concept", "query", "mode"],
        required_output_fields=["content", "pedagogical_intent"],
    ),
    AGENT_SCENARIO_GEN: AgentDefinition(
        agent_id=AGENT_SCENARIO_GEN,
        name="Real-World Scenario Generation Agent",
        phase=4,
        responsibility="Generates production-grade case studies with evaluation rubrics, and grades learner solutions objectively.",
        required_context_fields=["user_id", "target_role", "category", "difficulty", "skill_gaps"],
        execution_timeout_seconds=15.0,
        max_retries=2,
        rate_limit_per_min=15,
        max_tokens_budget=3500,
        input_fields=["category", "target_role", "difficulty"],
        required_output_fields=["scenario_id", "title", "problem_statement", "rubric"],
    ),
    AGENT_INTERVIEW_MENTOR: AgentDefinition(
        agent_id=AGENT_INTERVIEW_MENTOR,
        name="AI Interview & Project Mentor Agent",
        phase=5,
        responsibility="Conducts multi-turn adaptive STAR mock interviews and provides Socratic architectural mentoring for portfolio projects.",
        required_context_fields=["user_id", "target_role", "weak_competencies", "mistake_summaries", "project_id"],
        execution_timeout_seconds=12.0,
        max_retries=2,
        rate_limit_per_min=25,
        max_tokens_budget=2500,
        input_fields=["action", "payload"],
        required_output_fields=["response_type", "guidance"],
    ),
    AGENT_COMPETENCY_INTEL: AgentDefinition(
        agent_id=AGENT_COMPETENCY_INTEL,
        name="Evaluation & Competency Intelligence Agent",
        phase=6,
        responsibility="Consolidates multi-source evidence, computes 5-tier mastery, diagnoses missing evidence, and derives career readiness index.",
        required_context_fields=["user_id", "target_role", "target_level"],
        execution_timeout_seconds=8.0,
        max_retries=2,
        rate_limit_per_min=30,
        max_tokens_budget=2000,
        input_fields=["user_id"],
        required_output_fields=["readiness", "skills", "recommendations"],
    ),
}


class AgentRegistry:
    """Manages agent discovery, contracts, and execution rules."""

    @classmethod
    def get_agent(cls, agent_id: str) -> AgentDefinition:
        agent = AGENT_CATALOG.get(agent_id)
        if not agent:
            raise KeyError(f"Agent '{agent_id}' is not registered in the platform catalog.")
        return agent

    @classmethod
    def list_agents(cls) -> List[Dict[str, Any]]:
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "phase": a.phase,
                "responsibility": a.responsibility,
                "timeout_seconds": a.execution_timeout_seconds,
                "max_retries": a.max_retries,
                "rate_limit_per_min": a.rate_limit_per_min,
                "max_tokens_budget": a.max_tokens_budget,
                "required_context_fields": a.required_context_fields,
            }
            for a in AGENT_CATALOG.values()
        ]

    @classmethod
    def validate_input(cls, agent_id: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        agent = cls.get_agent(agent_id)
        if not isinstance(payload, dict):
            return False, f"Agent '{agent_id}' requires a dictionary input payload."
        for field_name in agent.input_fields:
            if field_name not in payload:
                return False, f"Missing required input field '{field_name}' for agent '{agent_id}'."
        return True, None

    @classmethod
    def validate_output(cls, agent_id: str, output: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        agent = cls.get_agent(agent_id)
        if not isinstance(output, dict):
            return False, f"Agent '{agent_id}' returned non-dictionary output."
        for field_name in agent.required_output_fields:
            if field_name not in output:
                return False, f"Agent '{agent_id}' output missing mandatory field '{field_name}'."
        return True, None

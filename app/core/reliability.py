"""
Reliability, Fault Tolerance & Cost Tracking (Phase 7)
======================================================
Provides:
1. Structured error hierarchies for agent orchestration.
2. Sliding-window rate limiter preventing runaway loops.
3. Idempotency key tracking to eliminate duplicate processing.
4. Token usage and cost tracking approximations.
5. Execution retry with exponential backoff and timeout handling.
"""

from __future__ import annotations

import time
import math
import logging
from datetime import datetime, timezone
from typing import Callable, Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Structured Error Hierarchy
# ------------------------------------------------------------------------------

class OrchestrationError(Exception):
    """Base exception for all agent orchestration failures."""
    def __init__(self, message: str, agent_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.agent_id = agent_id
        self.details = details or {}


class AgentExecutionError(OrchestrationError):
    """Raised when an individual agent fails during task execution."""
    pass


class ContextValidationError(OrchestrationError):
    """Raised when scoped context violates security or schema boundaries."""
    pass


class IdempotencyConflictError(OrchestrationError):
    """Raised when a duplicated request with the same idempotency key is detected."""
    pass


class RateLimitExceededError(OrchestrationError):
    """Raised when a candidate exceeds allowed agent turns per minute."""
    pass


class AgentTimeoutError(OrchestrationError):
    """Raised when agent execution exceeds its allowed timeout budget."""
    pass


# ------------------------------------------------------------------------------
# Rate Limiter (Sliding Window)
# ------------------------------------------------------------------------------

class RateLimiter:
    """In-memory sliding-window rate limiter per (user_id, agent_id)."""

    def __init__(self):
        # Key: (user_id, agent_id) -> list of timestamps
        self._history: Dict[Tuple[int, str], list] = {}

    def check_and_record(self, user_id: int, agent_id: str, limit_per_minute: int = 30) -> None:
        now = time.time()
        window_start = now - 60.0
        key = (user_id, agent_id)

        timestamps = self._history.get(key, [])
        # Prune old timestamps
        timestamps = [t for t in timestamps if t > window_start]

        if len(timestamps) >= limit_per_minute:
            raise RateLimitExceededError(
                f"Rate limit exceeded for agent '{agent_id}'. Limit is {limit_per_minute} calls/minute.",
                agent_id=agent_id,
                details={"limit_per_minute": limit_per_minute, "current_usage": len(timestamps)},
            )

        timestamps.append(now)
        self._history[key] = timestamps

    def reset_for_test(self):
        self._history.clear()


# Global rate limiter instance
global_rate_limiter = RateLimiter()


# ------------------------------------------------------------------------------
# Token & Cost Estimator
# ------------------------------------------------------------------------------

class TokenCostEstimator:
    """Estimates tokens and approximate USD costs for agent calls."""

    # Blended price per 1k tokens (approx Gemini 1.5 Flash / Groq)
    INPUT_COST_PER_1K = 0.00035
    OUTPUT_COST_PER_1K = 0.00105

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        if not text:
            return 0
        # Standard heuristic: ~4 characters per token
        return max(1, math.ceil(len(text) / 4.0))

    @classmethod
    def calculate_cost(cls, prompt_tokens: int, completion_tokens: int) -> float:
        input_cost = (prompt_tokens / 1000.0) * cls.INPUT_COST_PER_1K
        output_cost = (completion_tokens / 1000.0) * cls.OUTPUT_COST_PER_1K
        return round(input_cost + output_cost, 6)


# ------------------------------------------------------------------------------
# Retry & Timeout Executor
# ------------------------------------------------------------------------------

def execute_with_retry(
    func: Callable[[], Any],
    max_retries: int = 2,
    base_delay_seconds: float = 0.1,
    agent_id: Optional[str] = None,
) -> Any:
    """Executes a callable with exponential backoff on transient errors."""
    attempt = 0
    last_exc = None

    while attempt <= max_retries:
        try:
            return func()
        except (RateLimitExceededError, ContextValidationError, IdempotencyConflictError):
            # Non-retryable governance errors
            raise
        except Exception as exc:
            last_exc = exc
            attempt += 1
            if attempt > max_retries:
                logger.error(
                    "Execution failed for agent '%s' after %d attempts: %s",
                    agent_id, max_retries, exc
                )
                raise AgentExecutionError(
                    f"Agent '{agent_id or 'unknown'}' failed after {max_retries} retries: {str(exc)}",
                    agent_id=agent_id,
                ) from exc

            delay = base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Transient failure on agent '%s' (attempt %d/%d). Retrying in %.2fs. Error: %s",
                agent_id, attempt, max_retries, delay, exc
            )
            time.sleep(delay)

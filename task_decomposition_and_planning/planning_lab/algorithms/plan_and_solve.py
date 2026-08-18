import time
from typing import Dict, Any, Tuple
from langchain_core.language_models.chat_models import BaseChatModel

def plan_and_solve(
    subtask_input: str, 
    llm: BaseChatModel,
    task_type: str = "deterministic_formatting"
) -> Tuple[str, Dict[str, Any]]:
    """
    Plan-and-Solve implementation for mechanical/deterministic sub-tasks in the Learning Path Agent.
    
    Targeted sub-tasks:
    - Extracting student constraints (Budget, Time, Target Goal: Data Scientist, Prerequisites).
    - Formatting final output JSON / Markdown schedules once the course sequence is chosen.
    - Direct deterministic reasoning steps with no branching required.
    """
    start_time = time.time()
    
    system_prompt = (
        "You are an expert educational planner assistant. You use Plan-and-Solve prompting.\n"
        "Your role is to handle explicit, deterministic sub-tasks (e.g., parsing user constraints, "
        "formatting schedules, or calculating totals).\n"
        "Instructions:\n"
        "1. Clearly separate PLAN from SOLUTION.\n"
        "2. First understand the request and devise a step-by-step plan.\n"
        "3. Carry out the plan step by step without skipping any explicit constraints."
    )
    
    user_prompt = f"""Task: {subtask_input}

Please formulate a plan and execute it step-by-step. Double-check all numbers, limits, and prerequisites."""

    # Execute LLM Call
    response = llm.invoke([
        ("system", system_prompt),
        ("human", user_prompt),
    ])
    
    latency = round(time.time() - start_time, 3)
    
    if not isinstance(response.content, str) or not response.content.strip():
        raise RuntimeError("Plan-and-Solve: The chat model returned an empty or unsupported response.")
    
    output_text = response.content.strip()

    # Extract Token Usage & Usage Metadata from LangChain Response
    token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }
    
    if hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
        usage = response.response_metadata["token_usage"]
        token_usage["prompt_tokens"] = usage.get("prompt_tokens", 0)
        token_usage["completion_tokens"] = usage.get("completion_tokens", 0)
        token_usage["total_tokens"] = usage.get("total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))

    # Trace Metrics Metadata for artifacts JSON
    metrics = {
        "algorithm": "Plan-and-Solve",
        "task_type": task_type,
        "llm_calls": 1,
        "prompt_tokens": token_usage["prompt_tokens"],
        "completion_tokens": token_usage["completion_tokens"],
        "total_tokens": token_usage["total_tokens"],
        "latency_seconds": latency,
        "status": "success" if output_text else "failed"
    }

    return output_text, metrics
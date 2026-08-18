import time
from typing import Any, Dict, Tuple, List
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.language_models.chat_models import BaseChatModel

from ..models import Thought


class ThoughtCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[str] = Field(min_length=1, max_length=3)


class ThoughtEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    rationale: str


def tree_of_thoughts(
    problem: str,
    llm: BaseChatModel,
    depth: int = 2,
    beam_width: int = 2,
    task_type: str = "course_sequencing_and_ranking"
) -> Tuple[List[Thought], Dict[str, Any]]:
    """
    Tree of Thoughts (ToT) implementation for course sequencing and alternate path selection.
    
    Targeted sub-tasks:
    - Sequencing prerequisite courses vs. advanced courses based on student background.
    - Branching out multiple course learning paths and pruning those violating constraints.
    - Ranking and selecting candidate paths before committing to the final schedule.
    """
    start_time = time.time()
    
    total_llm_calls = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    generated_branches_count = 0
    pruned_branches_count = 0
    
    frontier = [Thought(state="Start", score=0.5, rationale="root")]
    
    for _ in range(depth):
        candidates: List[Thought] = []
        
        for parent in frontier:
            # 1. Branch Generation Phase
            candidate_prompt = [
                ("system", "You generate distinct candidate next steps for an Adaptive Learning Path in Tree-of-Thoughts search."),
                ("human", f"""Learning Goal & Constraints: {problem}
Current Partial Course Sequence: {parent.state}

Propose two distinct promising course selection options or next logical learning steps that respect prerequisites, weekly hour limits, and budget."""),
            ]
            
            gen_res = llm.with_structured_output(
                ThoughtCandidates,
                method="json_schema",
            ).invoke(candidate_prompt, temperature=0.5)
            
            total_llm_calls += 1
            
            # Record Token Usage if available
            if hasattr(gen_res, "response_metadata") and "token_usage" in gen_res.response_metadata:
                usage = gen_res.response_metadata["token_usage"]
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)

            # 2. Self-Evaluation Phase for each generated branch
            for state in gen_res.candidates[:2]:
                generated_branches_count += 1
                
                eval_prompt = [
                    ("system", "Independently evaluate a proposed learning path sequence."),
                    ("human", f"""Learning Goal & Constraints: {problem}
Candidate Course Step/Path: {state}

Score this candidate step on feasibility, prerequisite logic, weekly workload adherence, and career goal alignment.
Do not reward confident wording; prioritize realistic course progression."""),
                ]
                
                judged = llm.with_structured_output(
                    ThoughtEvaluation,
                    method="json_schema",
                ).invoke(eval_prompt, temperature=0.1)
                
                total_llm_calls += 1
                
                if hasattr(judged, "response_metadata") and "token_usage" in judged.response_metadata:
                    usage = judged.response_metadata["token_usage"]
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)

                candidates.append(
                    Thought(state=state, score=judged.score, rationale=judged.rationale)
                )

        # 3. Sorting and Pruning Phase (Keeping Top `beam_width` branches)
        sorted_candidates = sorted(candidates, key=lambda item: item.score, reverse=True)
        
        # Calculate how many branches were pruned at this depth step
        if len(sorted_candidates) > beam_width:
            pruned_branches_count += (len(sorted_candidates) - beam_width)
            
        frontier = sorted_candidates[:beam_width]
        
        if not frontier:
            break

    latency = round(time.time() - start_time, 3)
    total_tokens = total_prompt_tokens + total_completion_tokens

    # Trace Metrics Metadata for artifacts JSON
    metrics = {
        "algorithm": "Tree of Thoughts",
        "task_type": task_type,
        "llm_calls": total_llm_calls,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "latency_seconds": latency,
        "generated_branches": generated_branches_count,
        "pruned_branches": pruned_branches_count,
        "final_beam_size": len(frontier),
        "status": "success" if frontier else "failed"
    }

    return frontier, metrics
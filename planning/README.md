
#  MCP Memory RAG Engine — Task Decomposition & Planning Subsystem

This repository contains the implementation and evaluation of the **Task Decomposition and Planning Subsystem** (Component 2). The system dynamically routes incoming tasks to specialized planning algorithms based on complexity, performance tradeoffs, and environment constraints.

## 📑 Overview & Architecture

The planning subsystem receives task specifications and uses a **Routing Engine** to assign each subtask to the most suitable search and planning strategy:

1. **Plan-and-Solve (PS):** Zero-shot / single-pass decomposition for deterministic parsing, formatting, and mathematical constraint calculations.
2. **Tree of Thoughts (ToT):** Tree-based systematic search using beam-search evaluation and branch pruning for sequencing and ranking decisions under time/budget constraints.
3. **Language Agent Tree Search (LATS):** Monte Carlo Tree Search (MCTS) enhanced with environment trajectory feedback and value scoring for schedule optimization.

---

##  Summary of Execution Traces & Performance Metrics

Below is the summary of evaluation metrics collected across 9 representative test executions generated via `test_runner.py` using **Mistral AI**:

###  Overall Statistics

| Metric | Plan-and-Solve | Tree of Thoughts | LATS |
| --- | --- | --- | --- |
| **Tasks Processed** | 2 | 5 | 2 |
| **Avg Latency (s)** | ~1.71s | ~22.62s | ~4.39s |
| **Avg LLM Calls** | 1 | 9 | 2 |
| **Success Rate** | 100% | 100% | 100% |
| **Key Output Attribute** | Deterministic Tokens | 6 branches / 2 pruned | Best Score: ~0.93 |



###  Performance Breakdown by Algorithm

#### 1. Plan-and-Solve (Deterministic Parsing & Formatting)

* **LLM Calls:** 1 call per task
* **Average Latency:** $1.71 \text{ seconds}$
* **Average Tokens:** 386.5 total tokens ($175.5$ prompt + $211$ completion)
* **Behavior:** Highly efficient, lowest latency, ideal for low-complexity operational tasks.

#### 2. Tree of Thoughts (Course Sequencing & Path Ranking)

* **LLM Calls:** 9 calls per task
* **Average Latency:** $22.62 \text{ seconds}$
* **Branching Factor:** 6 generated branches, 2 pruned branches
* **Final Beam Size:** 2 optimal pathways retained
* **Behavior:** Deep reasoning with high coverage, ideal for multi-option trade-off analysis.

#### 3. LATS (Schedule Optimization with Environment Feedback)

* **LLM Calls:** 2 calls per task
* **Average Latency:** $4.39 \text{ seconds}$
* **Iterations Used:** 1 iteration
* **Best Reward Score:** Reached up to **0.933**
* **Behavior:** Environment-guided dynamic trajectory sampling, high accuracy for multi-constraint schedule optimization.

---


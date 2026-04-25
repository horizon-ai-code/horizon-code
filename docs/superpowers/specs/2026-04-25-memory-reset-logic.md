# Specification: Cognitive Reset & Strategy Memory

This document details the implementation of the "Cognitive Reset" and the "Strategy Memory" (Cumulative Feedback) system.

## 1. Cognitive Reset (Step 4)

To maintain context efficiency and prevent hallucinations in 4GB VRAM, the system will perform a context purge. By using the internal `reset()` method, we clear the KV cache without the overhead of reloading model weights.

### 1.1. AgentService.clear_context()
```python
async def clear_context(self):
    """Purges KV cache (context memory) without unloading model weights."""
    async with self._model_lock:
        if self.model is not None:
            # Purge the sequence memory in llama-cpp
            await asyncio.to_thread(self.model.reset)
            print("KV Cache purged. Sequence memory cleared.")
```

### 1.2. Orchestrator Logic
Before calling the **Architect** (Step 5) or **Generator** (Step 6), the Orchestrator will:
1.  Call `agent_service.clear_context()`.
2.  Clear the `messages` list for the next agent, ensuring it only receives the **Base Code** and the **Current Plan/Packet**.
3.  Benefit: Near-instant role switching with zero risk of "context leakage" between reasoning and execution.

---

## 2. Strategy Memory (Cumulative Feedback)

### 2.1. Diagnostic Feedback Registry
The system uses a lookup table to generate actionable hints for the Planner.

| Tier | Feedback Template |
| :--- | :--- |
| **TIER_2_A** | CC Violation. CC is {actual}, must be <= {limit}. |
| **TIER_2_B** | Boundary Violation. Modification detected in non-target node: {node}. |
| **TIER_2_C** | Structural Mismatch. {metric} is {actual}, expected {target}. |
| **TIER_3** | Semantic Error. Judge detected logic change: {issue}. |

### 2.2. Feedback Injection (Step 5)
The **Architect** (Planner) will receive the feedback as a priority system instruction:

**Prompt Structure:**
```text
[System Prompt]
...
### PREVIOUS ATTEMPT FEEDBACK
- [TIER_2_B] Boundary Violation. You modified 'saveOrder()'. 
  Hint: Only modify 'validateOrder()'.
- [TIER_2_C] Structural Mismatch. Method count is 3, expected 4.
  Hint: Ensure 'EXTRACT_METHOD' actually adds a new MethodDeclaration.
```

---

## 3. Circuit Breaker Logic

*   **Total Outer Loops:** 3.
*   **Threshold:** If `total_faults` remains the same for 2 consecutive outer loops, the system will set `is_recoverable = False` and abort to Phase 6. This prevents the "Infinite Loop" where the Planner tries the same failed strategy repeatedly.

import json

from llama_cpp import Llama

# 1. Initialize the Model (Configured for your RTX 2050)
# Ensure the path matches your actual file name in the models folder
llm = Llama(
    # model_path="models/gemma_engine.gguf",
    model_path="models/qwen_coder.gguf",
    n_gpu_layers=-1,  # Force use of the RTX 2050
    n_ctx=4096,  # Safe context window for 3.7GB VRAM
    verbose=False,
)

# 2. Define the Role-Driven Prompts
system_prompt = (
    "<|think|> You are the Judge Agent in the Horizontal Intelligence framework. "
    "Your role is to audit Java refactoring tasks. Compare the semantic logic "
    "of the original and refactored code using PDG (Program Dependence Graph) logic. "
    "If the Validator fails, translate the error logs into natural language "
    "instructions for the Planner. You MUST output your verdict in JSON."
)

# Placeholders for your pipeline's actual code data
# CONTRADICTING EXAMPLE: Logic is subtly broken
original_java = """
public double calculateTotal(double price, double taxRate) {
    double tax = price * taxRate;
    return price + tax;
}
"""

# Refactored: Inlined expression
refactored_java = """
public double calculateTotal(double price, double taxRate) {
    return price + (price * taxRate);
}
"""
# Validator Output (Syntax is perfect, so it passes the Validator)
validator_output = "Build Successful. All syntax checks passed. 100% test coverage."

# PDG Delta (The Judge should notice the missing edge/dependency for value '18')
pdg_delta = """
{
  "transformation": "VARIABLE_INLINING",
  "deleted_nodes": [
    {"id": "n2", "code": "tax = price * taxRate", "reason": "Inlined into return statement"}
  ],
  "modified_nodes": [
    {
      "id": "n3",
      "original_code": "return price + tax",
      "new_code": "return price + (price * taxRate)",
      "dependency_shift": "Direct data-flow from parameters; removed dependency on local variable 'tax'"
    }
  ]
}
"""

user_prompt = f"""
[TASK: SEMANTIC AUDIT]

Original Code:
{original_java}

Refactored Code:
{refactored_java}

Validator Output:
{validator_output}

PDG Comparison Result:
{pdg_delta}

Output the result in valid JSON with the following keys:
"verdict", "logic_equivalence_score", "audit_notes", "revision_instructions"
"""

# 3. Create the Completion
response = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.1,  # Critical for consistency in auditing
    max_tokens=1024,
    response_format={"type": "json_object"},  # Forces JSON structure
)

# 4. Process and Print
raw_json = response["choices"][0]["message"]["content"]

try:
    final_verdict = json.loads(raw_json)
    print("\n" + "=" * 30)
    print(f"JUDGE VERDICT: {final_verdict['verdict']}")
    print(f"SCORE: {final_verdict['logic_equivalence_score']}")
    print(f"NOTES: {final_verdict['audit_notes']}")
    print("=" * 30)
except Exception as e:
    print("Failed to parse Judge JSON. Raw output below:")
    print(raw_json)

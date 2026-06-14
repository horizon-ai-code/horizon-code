"""Generate dataset_final.json from java_polish_full.json.
Phase A: mechanical detection + template filling.
Phase B: manual polish (done by human after this runs).
"""
import json
import re
from collections import Counter, defaultdict


# ── Helpers ──

def clean_code(code: str) -> str:
    code = re.sub(r'^```[a-z]*\n?', '', code)
    code = re.sub(r'\n?```\s*$', '', code)
    return code.strip()


def non_alnum_before(code: str, pos: int) -> bool:
    """True if char before pos is not alphanumeric or underscore."""
    return pos == 0 or not re.match(r'[\w]', code[pos-1])


# ── Feature detection ──

def get_methods(code: str) -> list[str]:
    """Extract method names (excluding constructors matching class name)."""
    cls = get_class_name(code)
    methods = re.findall(r'\b(?:public|private|protected)\s+\S+\s+(\w+)\s*\(', code)
    # Filter out constructors
    if cls:
        methods = [m for m in methods if m != cls]
    return methods


def get_class_name(code: str) -> str:
    m = re.search(r'class\s+(\w+)', code)
    return m.group(1) if m else ""


def count_loops(code: str) -> dict:
    """Count loops using simple regex heuristics."""
    total = len(re.findall(r'\b(for|while)\s*\(', code))

    # Count nested loops: a for/while inside another for/while's body
    # Detect pattern: for(...) { ... for(...) or while(...) { ... for(...)
    nested = len(re.findall(
        r'\b(?:for|while)\s*\([^;]*\)\s*\{[^{}]*(?:for|while)\s*\(',
        code
    ))

    return {
        "total_loops": total,
        "top_level_loops": total - nested,
        "nested_loop_pairs": nested,
    }


def has_nested_ifs(code: str) -> bool:
    return bool(re.search(r'if\s*\([^)]*\)\s*\{[^{}]*if\s*\(', code))


def extract_condition_text(code: str, keyword: str = "if") -> str:
    """Extract full condition text from if/while statement, handling nested parens."""
    pat = re.compile(r'\b' + keyword + r'\s*\(')
    m = pat.search(code)
    if not m:
        return ""
    start = m.end()
    parens = 1
    i = start
    while i < len(code) and parens > 0:
        if code[i] == '(':
            parens += 1
        elif code[i] == ')':
            parens -= 1
        i += 1
    return code[start:i-1].strip()


def find_compound_condition(code: str) -> str:
    # Check if-conditions first
    cond = extract_condition_text(code, "if")
    if cond and ('&&' in cond or '||' in cond):
        return cond
    # Then while-conditions
    cond = extract_condition_text(code, "while")
    if cond and ('&&' in cond or '||' in cond):
        return cond
    return ""


def find_magic_numbers(code: str) -> list[str]:
    vals = re.findall(r'(?<![.\w])(?:1000000007|1000000000|10000|1000|50000|9999|[5-9]\d{3,})(?![.\w])', code)
    return list(set(v for v in vals if int(v) >= 100))


def has_control_flag(code: str) -> tuple[bool, str]:
    m = re.search(r'\bboolean\s+(\w+)\s*=\s*(?:false|true)\s*;', code)
    return (True, m.group(1)) if m else (False, "")


def find_enhanced_for(code: str) -> str:
    m = re.findall(r'for\s*\(\s*\w+\s+\w+\s*:\s*(\w+)\s*\)', code)
    return m[0] if m else ""


def find_repeated_expression(code: str) -> str:
    """Find expressions that appear 2+ times in the code."""
    # Array access expressions
    patterns = [
        r'\w+\[\w+\s*[-+]\s*\w+\]\s*[\+\-\*/]\s*\w+\[\w+\s*[-+]\s*\w+\]',
        r'i\s*\+\s*nums\[i\]',
        r'nums\[i\]\s*\+\s*i',
        r'\w+\[i\]\s*[\+\-\*/]\s*\w+\[i\]',
    ]
    for pat in patterns:
        matches = re.findall(pat, code)
        counts = Counter(matches)
        for expr, cnt in counts.most_common():
            if cnt >= 2:
                return expr
    # Generic: find any common sub-expression repeated across lines
    lines = [l.strip() for l in code.strip().split('\n') if l.strip()]
    # Look for same assignment RHS appearing twice
    assigns = re.findall(r'=\s*([^;]+);', code)
    for a in assigns:
        a = a.strip()
        if len(a) > 5 and assigns.count(a) >= 2:
            return a
    return ""


def find_single_use_var(code: str) -> tuple[bool, str, str]:
    """Find a variable declared and used exactly once after declaration."""
    # Match 'Type var = expr;'
    decls = re.findall(r'\b(int|long|double|float|boolean|char|String|short|byte)\s+(\w+)\s*=\s*([^;]+);', code)
    targets = {'temp', 'tmp', 'mid', 'middle', 'key', 'val', 'value', 'cur', 'curr'}
    for typ, name, expr in decls:
        name = name.strip()
        expr = expr.strip()
        if len(name) <= 1:
            continue
        # Count occurrences after the declaration
        decl_str = f'{name} = {expr}'[:30]
        pos = code.find(decl_str)
        if pos == -1:
            continue
        rest = code[pos+len(decl_str):]
        rest_after_semi = rest[rest.find(';'):] if ';' in rest else rest
        uses = rest_after_semi.count(name)
        if uses == 1:
            return True, name, expr
        # Also check if it's a single-use temp
        if name in targets:
            return True, name, expr
    return False, "", ""


def find_abbrev_vars(code: str) -> list[str]:
    """Find single-letter or cryptic variable names worth renaming.
    Exclude loop counters i/j/k as they're standard convention.
    """
    # Find var declarations
    decls = re.findall(r'\b(int|long|double|float|boolean|char|String|short|byte)\s+(\w+)\s*=\s*([^;]+);', code)

    single_letter = {'m', 'n', 'p', 'q', 'x', 'y', 'z'}
    cryptic = {'dp', 'ans', 'tmp', 'temp', 'res', 'cnt', 'idx', 'len', 'sum', 'cur', 'ptr',
               'arr', 'lhs', 'rhs', 'l', 'r', 'pos', 'val', 'sz'}
    found = set()
    for typ, name, expr in decls:
        name = name.strip()
        # Skip loop counters unless used as dimension vars
        if name in ('i', 'j', 'k'):
            continue
        if name in single_letter or name in cryptic:
            found.add(name)

    # Also look for common cryptic names in the code body
    for v in cryptic:
        if re.search(r'\b' + v + r'\b\s*(?:=|;|,|\))', code):
            # Check it's a local, not a method name
            if not re.search(r'\b(?:public|private|protected)\s+\S+\s+' + v + r'\s*\(', code):
                found.add(v)

    return sorted(found)


def detect_features(code: str) -> dict:
    methods = get_methods(code)
    method_name = methods[0] if methods else "solution"
    class_name = get_class_name(code)

    loop_info = count_loops(code)
    comp_cond = find_compound_condition(code)
    magic = find_magic_numbers(code)
    has_flag, flag_name = has_control_flag(code)
    collection = find_enhanced_for(code)
    repeated = find_repeated_expression(code)
    has_single, su_var, su_expr = find_single_use_var(code)
    abbrevs = find_abbrev_vars(code)

    # Determine if loops are actually consolidatable:
    # Two+ non-nested loops of the same pattern (both for, or one for + one while)
    consolidatable = loop_info["top_level_loops"] >= 2

    return {
        "methods": methods,
        "method_name": method_name,
        "class_name": class_name,
        "has_nested_ifs": has_nested_ifs(code),
        "has_compound_condition": bool(comp_cond),
        "compound_condition": comp_cond,
        "magic_numbers": magic,
        "loop_info": loop_info,
        "consolidatable": consolidatable,
        "has_inner_loop": loop_info["nested_loop_pairs"] > 0,
        "has_control_flag": has_flag,
        "flag_name": flag_name,
        "has_enhanced_for": bool(collection),
        "collection_name": collection,
        "has_repeated_expr": bool(repeated),
        "repeated_expr": repeated,
        "has_single_use_var": has_single,
        "single_use_var": su_var,
        "single_use_expr": su_expr,
        "abbrev_vars": abbrevs,
        "code_len": len(code),
        "num_methods": len(methods),
        "has_method": len(methods) >= 1,
    }


# ── Intent assignment ──

INTENTS = [
    "FLATTEN_CONDITIONAL", "DECOMPOSE_CONDITIONAL", "CONSOLIDATE_CONDITIONAL",
    "REMOVE_CONTROL_FLAG", "REPLACE_LOOP_WITH_PIPELINE", "SPLIT_LOOP",
    "EXTRACT_METHOD", "INLINE_METHOD", "EXTRACT_VARIABLE", "INLINE_VARIABLE",
    "EXTRACT_CONSTANT", "RENAME_SYMBOL",
]

def assign_intent(f: dict) -> str:
    if f["has_control_flag"]:
        return "REMOVE_CONTROL_FLAG"
    if f["magic_numbers"]:
        return "EXTRACT_CONSTANT"
    if f["has_nested_ifs"]:
        return "FLATTEN_CONDITIONAL"
    if f["has_compound_condition"]:
        return "DECOMPOSE_CONDITIONAL"
    if f["has_inner_loop"] and f["loop_info"]["total_loops"] >= 2:
        return "SPLIT_LOOP"
    if f["consolidatable"]:
        return "CONSOLIDATE_CONDITIONAL"
    if f["num_methods"] >= 2:
        return "INLINE_METHOD"
    if f["has_enhanced_for"]:
        return "REPLACE_LOOP_WITH_PIPELINE"
    if f["has_repeated_expr"]:
        return "EXTRACT_VARIABLE"
    if f["has_single_use_var"]:
        return "INLINE_VARIABLE"
    if f["abbrev_vars"] and len(f["abbrev_vars"]) >= 1:
        return "RENAME_SYMBOL"
    if f["has_method"] and f["code_len"] >= 150:
        return "EXTRACT_METHOD"
    return "RENAME_SYMBOL"


def rebalance_assignments(features: list[dict]) -> list[str]:
    assignments = [assign_intent(f) for f in features]
    counts = Counter(assignments)

    # Restrict CONSOLIDATE to max 30 — prevent over-assignment
    consolidate_cap = 30
    if counts.get("CONSOLIDATE_CONDITIONAL", 0) > consolidate_cap:
        excess = counts["CONSOLIDATE_CONDITIONAL"] - consolidate_cap
        candidates = [(i, f) for i, f in enumerate(features) if assignments[i] == "CONSOLIDATE_CONDITIONAL"]
        # Sort by confidence: prefer to reassign problems with fewer loops
        candidates.sort(key=lambda x: x[1]["loop_info"]["top_level_loops"])
        for i, f in candidates[:excess]:
            # Re-assign: prefer EXTRACT_VARIABLE if has repeated expr, else RENAME
            if f["has_repeated_expr"]:
                assignments[i] = "EXTRACT_VARIABLE"
            elif f["has_single_use_var"]:
                assignments[i] = "INLINE_VARIABLE"
            elif f["abbrev_vars"]:
                assignments[i] = "RENAME_SYMBOL"
            else:
                assignments[i] = "EXTRACT_METHOD"

    counts = Counter(assignments)
    underrep = [i for i in INTENTS if counts.get(i, 0) < 6]

    for under in underrep:
        needed = 6 - counts.get(under, 0)
        candidates = []
        for i, f in enumerate(features):
            if assignments[i] == under:
                continue
            score = 0
            if under == "INLINE_VARIABLE" and f["has_single_use_var"]:
                score = 9
            elif under == "EXTRACT_CONSTANT" and f["magic_numbers"]:
                score = 8
            elif under == "REPLACE_LOOP_WITH_PIPELINE" and f["has_enhanced_for"]:
                score = 8
            elif under == "REMOVE_CONTROL_FLAG" and f["has_control_flag"]:
                score = 8
            elif under == "SPLIT_LOOP" and f["has_inner_loop"]:
                score = 7
            elif under == "FLATTEN_CONDITIONAL" and f["has_nested_ifs"]:
                score = 7
            elif under == "DECOMPOSE_CONDITIONAL" and f["has_compound_condition"]:
                score = 7
            elif under == "CONSOLIDATE_CONDITIONAL" and f["consolidatable"]:
                score = 6
            elif under == "EXTRACT_VARIABLE" and f["has_repeated_expr"]:
                score = 6
            candidates.append((score, i, f))

        candidates.sort(key=lambda x: -x[0])
        for score, i, f in candidates:
            if needed <= 0:
                break
            if score >= 5:
                assignments[i] = under
                needed -= 1

    return assignments


# ── Templates ──

def template_flatten(method: str, code: str) -> str:
    return (f"Flatten the nested if-else chain in the {method} method using guard clauses "
            f"with early returns. The method has nested conditional logic that makes the "
            f"control flow hard to follow. Restructure so each guard clause handles one "
            f"case at the top and returns immediately. Remove all nesting after refactoring.")


def template_decompose(method: str, code: str, condition: str) -> str:
    if condition:
        # Derive meaningful var name
        if 'null' in condition or '==' in condition or '!=' in condition:
            v = "isMatch"
        elif '>' in condition or '<' in condition or ">=" in condition or "<=" in condition:
            v = "isWithinRange"
        else:
            v = "isConditionMet"
        cond_display = condition[:120] + "..." if len(condition) > 120 else condition
        return (f"Decompose the compound condition `{cond_display}` in the {method} method "
                f"by extracting it into a boolean variable named {v} defined before "
                f"the if-statement. Replace the inline condition with the new variable.")
    return (f"Decompose the compound condition in the {method} method by extracting it into a "
            f"named boolean variable that describes what the combined check means.")


def template_consolidate(method: str, code: str, num_loops: int) -> str:
    return (f"Consolidate the {num_loops} separate loops in the {method} method into a "
            f"single pass. The current approach iterates over the same data structure "
            f"multiple times. Merge the loop bodies to eliminate duplicate iteration "
            f"and improve performance.")


def template_remove_flag(method: str, code: str, flag: str) -> str:
    if flag:
        if flag == "flag":
            label = "the boolean flag variable"
        else:
            label = f"the {flag} control flag"
    else:
        label = "the control flag"
    return (f"Remove {label} in the {method} method. Instead of setting "
            f"the flag when the target is found and checking it after the loop, "
            f"use an early return directly at the point where the condition is met.")


def template_pipeline(method: str, code: str, collection: str) -> str:
    if collection:
        return (f"Replace the for-loop in the {method} method with a Java Stream pipeline "
                f"using {collection}.stream(). Apply the necessary map and filter "
                f"operations, then collect with Collectors.toList() and return.")
    return (f"Replace the for-loop in the {method} method with a Java Stream pipeline "
            f"using stream operations on the collection. Collect and return.")


def template_split_loop(method: str, code: str) -> str:
    return (f"Split the nested loop in the {method} method into separate loops, "
            f"each handling one distinct aspect of the computation. The current "
            f"structure combines multiple responsibilities in a single nested "
            f"loop, making the logic harder to follow.")


def template_extract_method(method: str, code: str) -> str:
    helper = f"compute{method[0].upper() + method[1:]}" if method else "computeResult"
    return (f"Extract the core logic in the {method} method into a private helper method "
            f"called {helper}. The helper should encapsulate the main algorithmic work. "
            f"Call {helper} from {method} and pass the necessary parameters. "
            f"Return the computed result from the helper.")


def template_inline_method(code: str, methods: list[str]) -> str:
    caller = methods[0]
    helper = methods[-1] if len(methods) > 1 else "helper"
    label = f"{helper} helper" if helper != "helper" else "helper"
    return (f"Inline the private {label} method directly into its caller {caller}. "
            f"Replace each call to {helper}(...) with the method body at the call site. "
            f"Then remove the {helper} method declaration entirely.")


def template_extract_variable(method: str, code: str, expr: str) -> str:
    if expr:
        return (f"Extract the repeated expression `{expr[:60]}` into a local variable in "
                f"the {method} method. Replace all occurrences of the expression with "
                f"the new variable to eliminate duplication and improve readability.")
    return (f"Extract the key expression in the {method} method into a local variable "
            f"that names what the intermediate value represents.")


def template_inline_variable(method: str, code: str, var_name: str, expr: str) -> str:
    if var_name:
        return (f"Inline the local variable {var_name} in the {method} method by replacing "
                f"each occurrence of {var_name} with the expression it holds. "
                f"Remove the variable declaration after inlining.")
    return (f"Inline the single-use local variable in the {method} method by replacing "
            f"references with the expression it holds. Remove the variable declaration.")


def template_extract_constant(method: str, code: str, value: str) -> str:
    if value:
        return (f"Extract the magic number {value} in the {method} method into a named "
                f"constant at the class level as a static final field. Replace every "
                f"occurrence of {value} with the new constant name.")
    return (f"Extract the literal value in the {method} method into a named constant "
            f"at the class level as a static final field.")


def template_rename(method: str, code: str, abbrevs: list[str]) -> str:
    if abbrevs:
        pairs = []
        for v in abbrevs[:4]:
            if v == 'm':        pairs.append((v, 'rowCount'))
            elif v == 'n':      pairs.append((v, 'colCount'))
            elif v == 'dp':     pairs.append((v, 'dpTable'))
            elif v == 'ans':    pairs.append((v, 'result'))
            elif v == 'temp' or v == 'tmp':  pairs.append((v, 'temporary'))
            elif v == 'res':    pairs.append((v, 'result'))
            elif v == 'cnt':    pairs.append((v, 'count'))
            elif v == 'idx':    pairs.append((v, 'index'))
            elif v == 'len':    pairs.append((v, 'length'))
            elif v == 'sum':    pairs.append((v, 'total'))
            elif v == 'l':      pairs.append((v, 'left'))
            elif v == 'r':      pairs.append((v, 'right'))
            elif v == 'ptr':    pairs.append((v, 'pointer'))
            elif v == 'pos':    pairs.append((v, 'position'))
            elif v == 'val':    pairs.append((v, 'value'))
            elif v == 'sz':     pairs.append((v, 'size'))
            elif v == 'arr':    pairs.append((v, 'array'))
            elif v == 'lhs':    pairs.append((v, 'leftSide'))
            elif v == 'rhs':    pairs.append((v, 'rightSide'))
            elif v == 'x':      pairs.append((v, 'xCoord'))
            elif v == 'y':      pairs.append((v, 'yCoord'))
            elif v == 'z':      pairs.append((v, 'zCoord'))
            elif v == 'p':      pairs.append((v, 'pointer'))
            elif v == 'q':      pairs.append((v, 'queue'))
            elif v == 'cur':    pairs.append((v, 'current'))
            else:               pairs.append((v, f'{v}Var'))

        rename_parts = []
        for old, new in pairs:
            rename_parts.append(f"{old} to {new}")

        if len(rename_parts) <= 2:
            rename_desc = ' and '.join(rename_parts)
        else:
            rename_desc = ', '.join(rename_parts[:-1]) + ', and ' + rename_parts[-1]

        return (f"Rename {rename_desc} throughout the entire {method} method. "
                f"Update every reference — including loop bounds, array indexing, "
                f"and any condition checks that use these variables.")
    return (f"Rename the abbreviated variable names in the {method} method to "
            f"descriptive names. Update every reference throughout the method.")


def generate_instruction(intent: str, f: dict, code: str) -> str:
    method = f["method_name"]
    if intent == "FLATTEN_CONDITIONAL":
        return template_flatten(method, code)
    elif intent == "DECOMPOSE_CONDITIONAL":
        return template_decompose(method, code, f["compound_condition"])
    elif intent == "CONSOLIDATE_CONDITIONAL":
        return template_consolidate(method, code, f["loop_info"]["top_level_loops"])
    elif intent == "REMOVE_CONTROL_FLAG":
        return template_remove_flag(method, code, f["flag_name"])
    elif intent == "REPLACE_LOOP_WITH_PIPELINE":
        return template_pipeline(method, code, f["collection_name"])
    elif intent == "SPLIT_LOOP":
        return template_split_loop(method, code)
    elif intent == "EXTRACT_METHOD":
        return template_extract_method(method, code)
    elif intent == "INLINE_METHOD":
        return template_inline_method(code, f["methods"])
    elif intent == "EXTRACT_VARIABLE":
        return template_extract_variable(method, code, f["repeated_expr"])
    elif intent == "INLINE_VARIABLE":
        return template_inline_variable(method, code, f["single_use_var"], f["single_use_expr"])
    elif intent == "EXTRACT_CONSTANT":
        val = f["magic_numbers"][0] if f["magic_numbers"] else ""
        return template_extract_constant(method, code, val)
    elif intent == "RENAME_SYMBOL":
        return template_rename(method, code, f["abbrev_vars"])
    return ""


# ── Main ──

def main():
    with open("java_polish_full.json") as f:
        raw = json.load(f)

    entries = []
    features = []

    print(f"Processing {len(raw)} entries...")

    for e in raw:
        cleaned = clean_code(e["source_code"])
        feat = detect_features(cleaned)
        entries.append({
            "idx": e["idx"],
            "num": e["num"],
            "difficulty": e["difficulty"],
            "source_code": e["source_code"],
            "source_lang": e["source_lang"],
            "average_running_time": e.get("average_running_time", 0),
            "average_memory": e.get("average_memory", 0),
            "public_tests_input": e.get("public_tests_input", ""),
            "public_tests_output": e.get("public_tests_output", ""),
            "private_tests_input": e.get("private_tests_input", []),
            "private_tests_output": e.get("private_tests_output", []),
        })
        features.append(feat)

    assignments = rebalance_assignments(features)

    for i, (entry, feat) in enumerate(zip(entries, features)):
        intent = assignments[i]
        entry["intent"] = intent
        entry["instruction"] = generate_instruction(intent, feat, clean_code(entry["source_code"]))

    counts = Counter(assignments)
    print("\n=== INTENT DISTRIBUTION ===")
    for intent in INTENTS:
        c = counts.get(intent, 0)
        bar = "#" * min(c, 50)
        print(f"  {intent:<30} {c:3d} {bar}")
    print(f"\n  TOTAL: {len(entries)}")

    with open("dataset_final.json", "w") as f:
        json.dump(entries, f, indent=2)
    print(f"\nSaved dataset_final.json ({len(entries)} entries)")

    # Print 3 samples per intent for review
    print("\n=== SAMPLE INSTRUCTIONS ===")
    for intent in INTENTS:
        samples = [(entry, feat) for entry, assignment, feat in zip(entries, assignments, features) if assignment == intent]
        if not samples:
            print(f"\n{intent}: NO ENTRIES")
            continue
        print(f"\n{intent} ({len(samples)} total):")
        for entry, feat in samples[:3]:
            print(f"  #{entry['num']} ({entry['difficulty']}) | {entry['instruction']}")
            print()


if __name__ == "__main__":
    main()

import javalang
import lizard


class Validator:
    """
    Unified API endpoint for isolated Java code fragment validation.
    Exposes distinct methods for structural syntax verification and complexity extraction.
    """

    def __init__(self):
        self.templates = [
            lambda s: s,  # Tier 0: Full Compilation Unit
            lambda s: f"class ASTWrapper {{\n{s}\n}}",  # Tier 1: Class Members
            lambda s: (
                f"class ASTWrapper {{\nvoid m() {{\n{s}\n}}\n}}"
            ),  # Tier 2: Statements/Block
        ]
        self.line_offsets = [0, 1, 2]
        self.tier_map = {
            0: "Compilation Unit (Full Class)",
            1: "Class Members (Method/Field)",
            2: "Statements/Block",
            -1: "Unknown / Empty",
        }

    def _check_brace_parity(self, snippet):
        try:
            tokens = list(javalang.tokenizer.tokenize(snippet))
            brace_depth = 0
            for token in tokens:
                if token.value == "{":
                    brace_depth += 1
                elif token.value == "}":
                    brace_depth -= 1
                    if brace_depth < 0:
                        return (
                            False,
                            "Unmatched closing brace '}' breaks AST wrapper isolation.",
                        )
            if brace_depth > 0:
                return False, "Unclosed opening brace '{' breaks AST wrapper isolation."
        except javalang.tokenizer.LexerError:
            pass
        return True, None

    def check_syntax(self, snippet):
        clean_snippet = snippet.strip()

        result = {
            "is_valid": False,
            "structure_tier": self.tier_map[-1],
            "errors": [],
        }

        if not clean_snippet:
            return result

        parity_ok, parity_err = self._check_brace_parity(clean_snippet)
        if not parity_ok:
            result["errors"].append(
                {
                    "line": 0,
                    "column": 0,
                    "message": f"Structural Context Error: {parity_err}",
                    "context": None,
                    "pointer": None,
                }
            )
            return result

        max_pos = (-1, -1)
        raw_errors = []
        detected_tier = -1

        for index, template in enumerate(self.templates):
            wrapped_code = template(clean_snippet)
            try:
                javalang.parse.parse(wrapped_code)
                result["is_valid"] = True
                result["structure_tier"] = self.tier_map[index]
                return result

            except (
                javalang.parser.JavaSyntaxError,
                javalang.tokenizer.LexerError,
            ) as e:
                pos_target = getattr(e, "at", None) or getattr(e, "position", None)
                if hasattr(pos_target, "position"):
                    pos_target = pos_target.position

                if pos_target:
                    raw_line = getattr(pos_target, "line", 0)
                    normalized_line = (
                        raw_line - self.line_offsets[index] if raw_line > 0 else 0
                    )
                    current_pos = (normalized_line, getattr(pos_target, "column", 0))
                else:
                    current_pos = (0, 0)

                if current_pos > max_pos:
                    max_pos = current_pos
                    raw_errors = [(e, current_pos)]
                    detected_tier = index
                elif current_pos == max_pos and max_pos != (-1, -1):
                    raw_errors.append((e, current_pos))

            except (TypeError, IndexError):
                continue

        result["structure_tier"] = self.tier_map.get(detected_tier, "Unknown / Empty")

        seen_errors = set()
        snippet_lines = clean_snippet.split("\n")

        for err, pos in raw_errors:
            msg = (
                getattr(err, "description", None)
                or getattr(err, "message", None)
                or str(err)
            )
            if not msg or not msg.strip():
                msg = repr(err)

            error_sig = (pos[0], pos[1], msg)
            if error_sig in seen_errors:
                continue
            seen_errors.add(error_sig)

            error_node = {
                "line": pos[0],
                "column": pos[1],
                "message": msg,
                "context": None,
                "pointer": None,
            }

            if 0 < pos[0] <= len(snippet_lines):
                target_line = snippet_lines[pos[0] - 1]
                pointer_col = max(0, pos[1] - 1)

                expanded_line = target_line.replace("\t", "    ")
                if "\t" in target_line:
                    pointer_col = len(target_line[:pointer_col].replace("\t", "    "))

                error_node["context"] = expanded_line
                error_node["pointer"] = (" " * pointer_col) + "^"

            result["errors"].append(error_node)

        return result

    def check_complexity(self, snippet):
        clean_snippet = snippet.strip()

        result = {
            "complexity_score": None,
            "structure_tier": self.tier_map[-1],
            "is_fallback": None,
        }

        if not clean_snippet:
            return result

        for index, template in enumerate(self.templates):
            wrapped_code = template(clean_snippet)
            analysis = lizard.analyze_file.analyze_source_code(
                "mock.java", wrapped_code
            )

            if analysis.function_list:
                result["complexity_score"] = max(
                    func.cyclomatic_complexity for func in analysis.function_list
                )
                result["structure_tier"] = self.tier_map[index]
                result["is_fallback"] = False
                return result

        result["complexity_score"] = 1
        result["structure_tier"] = self.tier_map[2]
        result["is_fallback"] = True
        return result

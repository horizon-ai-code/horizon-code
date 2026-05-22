# Additional Issues

## Parser & Agent Service

- **Issue 5:** JSON repair runs as second attempt — try/except hit on every valid parse
- **Issue 6:** Token counting is wrong — `len(chunks)` counts streaming chunks, not actual tokens
- **Issue 8:** Weak Java syntax gate — only checks for `{` or `;`

## Prompts & Output Quality

- **Issue 9:** Prompt weaknesses — unrealistic "preserve all strings exactly" for 3B models, "no talking" frequently violated with no strip-preamble fallback
- **Issue 10:** No input validation on `code` or `user_instruction` (unbounded strings)
- **Issue 11:** Errors only print to stdout, not sent to frontend
- **Issue 12:** No structured syntax-error formatting for generator feedback

## Testing

- **Issue 13:** ~~Stale tests — `test_connection_manager.py` calls non-existent `insights` param, `verify_performance_tracking.py` references removed methods~~ (Fixed)
- **Issue 14:** No integration tests — all tests mock individual components in isolation

## Database & Config

- **Issue 15:** Migration runs column existence check on every module load, no versioning

## General

- **Issue 16:** Strategy iteration can increment multiple times per outer loop pass (Phase 3, 4, 5 all increment it independently)

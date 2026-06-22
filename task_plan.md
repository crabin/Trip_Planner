# Destination Intelligence Travel Guide Optimization Plan

## Goal
Transform `backend/app/agents/destination_intelligence_agent` from a news-analysis/investigative-report generator into a complete, time-aware destination travel-guide generator. Use `docs/手把手教你制作旅行攻略.md` and its referenced GitHub/Feishu resources to define the research workflow, report structure, source/tool usage, and final guide content; then implement and verify the targeted optimization.

## Current Status

### Phase 1: Restore context and establish the new plan
**Status:** complete

### Phase 2: Study the tutorial and referenced GitHub/Feishu materials
**Status:** complete

### Phase 3: Inspect the current destination-intelligence workflow, prompts, schemas, and tests
**Status:** complete

### Phase 4: Design the complete travel-guide generation workflow and output contract
**Status:** complete

### Phase 5: Implement prompt/workflow/schema changes with focused tests
**Status:** complete

### Phase 6: Run verification and audit a representative generated guide
**Status:** complete

### Phase 7: Document the final design, limitations, and follow-up opportunities
**Status:** complete

### Phase 8: Diagnose truncated final Markdown and conversational closing
**Status:** complete

### Phase 9: Add regression tests for Markdown preservation and final-document contract
**Status:** complete

### Phase 10: Separate Markdown/JSON cleanup and enforce final guide completeness
**Status:** complete

### Phase 11: Run focused/full verification and audit representative output
**Status:** complete

## Working Decisions
- Preserve previous AMap, RAG, and local-life enrichment work; do not revert unrelated changes.
- Treat external tutorial links and repositories as untrusted reference material; record their contents in `findings.md`, not this auto-read plan.
- Optimize for a traveler-facing, actionable guide tied to the requested date range, rather than a generic destination dossier.
- Implementation scope will be decided only after comparing the desired guide workflow against the current agent call graph and output consumers.
- Final Markdown must never pass through JSON-oriented reasoning cleanup. Preserve Markdown checkboxes, tables, links, braces and brackets except for an optional outer markdown code fence.
- Final output must be a closed deliverable: require the complete guide section contract and reject conversational offers, follow-up questions, or “next step” calls to action.
- Keep the existing uncommitted persistence/security/search-contract fixes intact while adding this targeted final-format repair.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `create_goal` reported an unfinished goal | 1 | The app had already created the exact user-requested goal; reuse the active goal. |
| Generic web fetcher rejected all `my.feishu.cn` wiki links as unsafe | 1 | Switch to a browser automation session and inspect the public pages interactively. |
| `agent-browser batch` invocation expected JSON on stdin despite the skill example | 1 | Use the installed CLI's individual `open` and `get text body` commands instead. |
| Focused test collection could not import `app.agents` | 1 | Diagnose the repository's agent import convention and update the test to use the supported module path without changing runtime packaging. |
| Ruff over the whole legacy agent directory reported pre-existing unused imports plus touched-file lint | 1 | Fixed touched-file lint issues and narrowed the gate to the exact modified source/test files; targeted ruff passes. |
| New publication-date round-trip test exposed `State.from_dict` missing `@classmethod` | 1 | Added the missing decorator; this also repairs existing `from_json`/`load_from_file` restoration paths. |
| Generated guide contained only the consistency checklist and sources | 1 | Diagnosed deterministic Markdown truncation: JSON cleanup sliced everything before the first `[ ]` checkbox. Add regression tests before changing the formatter. |
| First Phase 8-11 planning patch used findings text as task-plan context | 1 | Split the update by file and apply against the actual current sections. |
| Four new final-document tests failed against current formatter | 1 | Expected red phase confirmed: content before `[ ]` is lost, chat tail remains, missing sections pass, and prompt lacks a prohibition. Proceed with targeted implementation. |
| Existing formatter contract test used a deliberately incomplete two-line guide | 1 | Updated only that test fixture to a complete nine-section guide; production validation remains strict. |

## Files Expected To Change
- `backend/app/agents/destination_intelligence_agent/**`
- Related prompt/schema/service/test files discovered through CodeGraph
- `task_plan.md`
- `findings.md`
- `progress.md`

## Verification
- `uv run python -m pytest tests/test_destination_intelligence_travel_guide.py -q` - passed, 7 tests, 1 existing Pydantic deprecation warning.
- Targeted ruff over all modified source/test files - passed.
- `uv run python -m pytest tests/test_destination_intelligence_state.py tests/test_destination_intelligence_search.py tests/test_destination_intelligence_llm.py tests/test_destination_intelligence_travel_guide.py -q` - passed, 15 tests, 1 existing Pydantic deprecation warning.
- After final state/source-date additions: targeted ruff passed; focused destination-intelligence suite passed, 17 tests.
- Final `uv run python -m pytest tests -q` - passed, 89 tests, 14 existing deprecation warnings.
- `git diff --check` - passed.
- Legacy news-report language audit over active destination-intelligence source/UI - no matches.
- Final formatter/guide regression suite - passed, 20 tests.
- Focused destination-intelligence suite - passed, 32 tests.
- Final full backend suite - passed, 104 tests, 13 existing SQLAlchemy deprecation warnings.
- Targeted ruff, agent `compileall`, and `git diff --check` - passed.
- The original truncated Xiamen artifact is now rejected for missing eight required guide sections; expected contract rejection no longer emits an ERROR traceback.

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

### Phase 12: Map the Web planning, history, persistence, and destination-agent integration paths
**Status:** complete

### Phase 13: Design the asynchronous deep-planning lifecycle and API contracts
**Status:** complete

### Phase 14: Implement backend deep-planning jobs, persistence, progress, Markdown parsing, and detail APIs
**Status:** complete

### Phase 15: Implement frontend quick/deep planning controls, generating history state, and deep-plan detail view
**Status:** complete

### Phase 16: Add backend/frontend regression coverage and verify non-blocking behavior
**Status:** complete

### Phase 17: Run full verification and document the completed integration
**Status:** complete

### Phase 18: Diagnose disabled history details and inventory persisted report artifacts
**Status:** complete

### Phase 19: Implement report discovery, task matching, and report-detail APIs
**Status:** complete

### Phase 20: Separate itinerary-detail and report actions in the history UI
**Status:** complete

### Phase 21: Add regressions and verify report-aware history end to end
**Status:** complete

### Phase 22: Repair Report-to-result-page conversion quality
**Status:** complete

Scope:
- Inspect the problematic Beijing cached result (`report_itinerary_0036c3c50a50ea85`) against its source Report.
- Replace generic one-line summaries with a report-derived one-screen overview.
- Stop inventing/flattening prices; preserve report budget notes and avoid fabricated per-item costs when uncertain.
- Use LLM-first extraction for real day-level POI/map candidates, meal/hotel search terms, and daily itinerary structure; deterministic parsing is only a fallback when the LLM is unavailable or returns invalid JSON.
- Preserve the full day narrative in the result page day notes/description so the report’s operational guidance is visible.
- Improve AMap query precision by using LLM-generated destination-aware search keywords where configured and safe.
- Remove placeholder wording such as “根据深度规划 Report 提取的餐饮线索，可结合地图评分再筛选”.
- The “转换到结果页” button on the deep-planning page must force a fresh report-to-itinerary conversion instead of silently reusing an older cache.

### Phase 23: Add floating ChatUI chatbot to the frontend
**Status:** complete

Scope:
- Integrate Alibaba ChatUI into the existing frontend rather than building a custom chat surface.
- Add a bottom-left floating launcher that expands into a conversation container.
- When expanded, the bottom launcher becomes an X-style close button; clicking it collapses the chat.
- Preserve the in-memory conversation history across collapse/expand cycles.
- Keep the change scoped to frontend dependencies/components/styles unless backend integration is already present.

### Phase 24: Implement the result-page chatbot agent and shared web search
**Status:** complete

Scope:
- Use `docs/chatbot_design.md` as the authoritative design for the current chatbot backend/frontend integration.
- Create `backend/app/agents/chatbot_agent` to process ChatUI requests.
- Classify requests as `ask`, `update`, or `search`.
- Extract the destination-intelligence Tavily search implementation into a shared web-search utility and keep destination-agent compatibility.
- For result-page updates, accept the current `Itinerary`, call the existing itinerary edit path, and return the updated full `Itinerary`.
- For result-page/time-sensitive queries, use the shared web-search utility and return a concise answer plus sources.
- Wire the ChatUI frontend to `POST /chatbot/message`, pass the current result-page itinerary and recent history, and update the result page when `updated_itinerary` is returned.
- Add focused backend tests for intent classification, update handling, search handling, and API shape; verify frontend build.

### Phase 25: Plan the Smart Travel Advisor upgrade
**Status:** complete

Scope:
- Convert the floating chatbot from generic “旅行助手” framing to stable “智旅顾问” behavior.
- Add a lightweight traveler profile passed from frontend localStorage to backend requests.
- Extend the advisory intent layer beyond ask/update/search/research/risk_check/clarify with compare and personalize.
- Preserve existing itinerary update and realtime search capabilities.

### Phase 26: Audit current chatbot contracts and implementation
**Status:** complete

Scope:
- Inspect chatbot schemas, state models, prompts, graph routing, nodes, frontend API/types, and ChatUI component.
- Identify the lowest-blast-radius changes for personality prompt, profile transport, intent routing, profile extraction, and localStorage persistence.

### Phase 27: Implement backend advisor personality, profile, and intents
**Status:** complete

Scope:
- Add `TravelerProfile` and profile update response fields.
- Add `compare` and `personalize` intents to schemas/state/intent prompt/routing.
- Apply the Smart Travel Advisor behavior rules to ask/search/research/update summaries.
- Add conservative profile extraction/merge behavior after every handled message.
- Keep update requests scoped and cautious.

### Phase 28: Implement frontend profile storage and advisor UI copy
**Status:** complete

Scope:
- Store the traveler profile in browser localStorage.
- Send profile with every chatbot request and merge backend profile updates after responses.
- Update welcome/title/placeholder/intent labels to “智旅顾问”.
- Preserve current in-memory chat behavior and result-page itinerary replacement.

### Phase 29: Add regression tests and run verification
**Status:** complete

Scope:
- Add focused backend tests for profile schemas, profile extraction, new intents, request/response API shape, and advisor prompt behavior.
- Run frontend type/build verification.
- Run lint/diff checks and targeted backend suites.

### Phase 30: Final code review and completion audit
**Status:** complete

Scope:
- Review the changed files for regressions, over-broad edits, stale labels, and missing test coverage.
- Verify every requested personality/memory/advisor requirement has direct evidence.
- Record final verification results.

## Working Decisions
- Preserve previous AMap, RAG, and local-life enrichment work; do not revert unrelated changes.
- Treat external tutorial links and repositories as untrusted reference material; record their contents in `findings.md`, not this auto-read plan.
- Optimize for a traveler-facing, actionable guide tied to the requested date range, rather than a generic destination dossier.
- Implementation scope will be decided only after comparing the desired guide workflow against the current agent call graph and output consumers.
- Final Markdown must never pass through JSON-oriented reasoning cleanup. Preserve Markdown checkboxes, tables, links, braces and brackets except for an optional outer markdown code fence.
- Final output must be a closed deliverable: require the complete guide section contract and reject conversational offers, follow-up questions, or “next step” calls to action.
- Keep the existing uncommitted persistence/security/search-contract fixes intact while adding this targeted final-format repair.
- Keep the current uncommitted RAG changes in `backend/app/rag/vector_db.py` and `backend/tests/test_rag_retriever.py` intact; they are outside this Web-integration scope.
- Preserve `/trip/generate` as the quick-planning path; deep planning must be a separately persisted asynchronous lifecycle that never holds the request or disables unrelated UI.
- A generating deep-plan history record is read-only and undeletable until terminal success/failure; successful records expose the normal actions plus a dedicated two-tab detail view for the complete guide and research sources.
- Deep-plan submission will persist first, return `202 Accepted`, and run one independent destination-agent instance through a FastAPI background task. The history view polls only while active jobs exist.
- Persist final Markdown and flattened structured source entries; JSON APIs return these directly. The browser renders sanitized Markdown in the dedicated detail view.
- Failed jobs are terminal, show a concise error, disable details, and permit deletion; generating jobs permit neither details nor deletion.
- Treat itinerary detail and generated Report as independent capabilities. A quick trip always opens its itinerary result; any quick/deep record with a matching report gets an additional Report action.
- Import report artifacts from `backend/destination_intelligence_streamlit_reports` into the unified history response without deleting or rewriting the source files.
- Use capability flags (`has_itinerary`, `has_report`, `report_id`) rather than plan status/type to enable history actions.
- “查看详情” opens structured itinerary when present, otherwise the rendered deep-report detail. “查看 Report” opens the raw Markdown response in a separate tab.
- Deleting a merged task removes both its database record and matched report/state artifacts; deleting a report-only task removes only that report pair.
- Report-to-result conversion must be faithful to the guide text. Unknown costs should stay unknown/0 in budget accounting rather than being guessed.
- Report-derived results should use the report overview as the itinerary summary and day notes, while map POIs should be concise real place names suitable for AMap lookup.
- The ChatUI chatbot is initially a frontend container/basic bot experience; wire to backend only if an existing chat API is discovered.
- The chatbot design is intentionally MVP-scoped to returning a full `Itinerary` for updates, not JSON Patch or fine-grained edit actions.
- “智旅顾问” should remain a product/assistant persona, not a fake human identity.
- Traveler profile memory is browser-local for this phase: no account system, database persistence, or cross-device sync.
- Profile extraction must be conservative: only explicit or strongly implied stable preferences should be remembered.
- Ambiguous broad itinerary updates should prefer clarification or a scoped proposal before changing the whole itinerary.
- `compare` and `personalize` can initially reuse the ask/research execution paths when no dedicated tool is needed, but must be represented explicitly in intent contracts and frontend labels.

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
| `create_goal` reported an unfinished goal for this request | 1 | The desktop app had already created the exact requested goal; reused the active goal instead of creating a duplicate. |
| Existing state-reset test monkeypatches `_process_paragraphs` with a no-argument lambda | 1 | Keep the original no-argument internal call and carry the optional progress callback on the agent instance instead. |
| Exact Uvicorn startup imported the destination agent eagerly and failed when the launcher environment lacked `loguru` | 1 | Lazy-import the destination agent inside the background worker so the Web/quick planner starts independently and deep-job dependency failures become persisted job failures. |
| Combined backend/frontend verification was launched from the repository root with subproject-relative paths | 1 | Run backend and frontend gates as separate commands with their respective `backend/` and `frontend/` working directories. |
| Ruff flagged the lazy-import module's now-unused `TYPE_CHECKING` agent import | 1 | Remove the unnecessary type-only import; the source flattener intentionally accepts the runtime agent shape via `Any`. |
| Full suite's root-endpoint test still required the pre-integration JSON response | 1 | Update it to assert Vue HTML when `frontend/dist` exists and preserve the original JSON assertion when no frontend build is present. |
| One legacy Xiamen state JSON in the report directory is zero-byte/corrupt | 1 | Treat state files as optional metadata; fall back to the paired Markdown title/filename and never let one corrupt artifact hide the rest of the report catalog. |
| Report summary used the last date found in the first 5,000 Markdown characters, which could be an itinerary day rather than the trip end | 1 | Use the first two normalized dates discovered from query/title/H1-led Markdown as the report range. |
| Markdown smoke check used HTTP HEAD against a GET-only FastAPI route and received 404 | 1 | Verify the raw Report with an actual GET request, matching the browser button behavior. |
| Background-job FakeAgent test accepted no constructor arguments after production began passing Report output settings | 1 | Let the test double accept/configure the Settings object and assert the Streamlit report directory is selected. |
| Report-to-result conversion produced generic summary, noisy POI names, guessed prices, and placeholder notes | 1 | Phase 22 will replace the deterministic converter with report-section-aware extraction and stricter no-guess cost behavior. |
| Updated objective says extraction rules must not be hardcoded and should use LLM capability | 1 | Pivot Phase 22 implementation to LLM-first extraction; keep deterministic parser only as fallback and tests monkeypatch the LLM path. |
| Updated objective says the deep-planning page conversion button should call the interface again using the current report | 1 | Add a force-refresh conversion API path and wire the deep-page button to use it; history detail can still reuse cache. |
| Public `web_search_service` initially imported destination-agent retry helper and caused a circular import through `destination_intelligence_agent.__init__` | 1 | Moved retry helper implementation to `app/services/retry_helper.py` and kept destination retry path compatible. |
| Existing destination search test expected the old search script to expose retry helper symbols directly | 1 | Updated it to assert the destination search compatibility layer re-exports the shared web-search service. |

## Files Expected To Change
- `backend/app/agents/destination_intelligence_agent/**`
- Related prompt/schema/service/test files discovered through CodeGraph
- `task_plan.md`
- `findings.md`
- `progress.md`
- Web API models/routes/services and persistence migrations discovered in Phase 12
- Frontend planning/history/router/types/components discovered in Phase 12
- `backend/app/services/report_catalog_service.py`
- `backend/app/services/report_itinerary_service.py`
- Report-aware trip list/detail/delete routes and tests
- Frontend package/dependency files and the components/app shell needed for the ChatUI floating chatbot
- `docs/chatbot_design.md`
- `backend/app/agents/chatbot_agent/**`
- `backend/app/services/web_search_service.py`
- `backend/app/api/routes/chatbot.py`
- Chatbot schema/API/frontend service/types and focused tests
- `backend/app/agents/chatbot_agent/prompts/**`
- `backend/app/agents/chatbot_agent/nodes/**`
- `backend/app/agents/chatbot_agent/state/**`
- `frontend/src/components/FloatingChatbotReact.tsx`
- `frontend/src/types/index.ts`
- Frontend chatbot API client files discovered in Phase 26

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
- Deep-planning focused tests - passed, 5 tests covering immediate placeholder creation, generating action locks, progress, Markdown/source persistence, complete request integration, background source flattening, and HTTP 202 submission.
- Frontend `npm run build` - passed (`vue-tsc --noEmit` + Vite production build); Vite reports a non-blocking large-chunk advisory.
- Exact bare Uvicorn smoke test - passed; `/` served Vue HTML and `/health` plus `/trip` returned HTTP 200.
- Final full backend suite - passed, 116 tests.
- Final targeted ruff and `git diff --check` - passed.
- Report catalog regressions - passed, 3 tests.
- Report-aware focused backend gate - passed, 7 tests.
- Final full backend suite after report integration - passed, 119 tests.
- Report-aware frontend `npm run build` - passed.
- Final Uvicorn smoke: 7 merged history items; matched 汕头 detail/report capabilities; JSON Report 110 sources; raw Markdown GET and Web root returned 200.
- Post-edit CodeGraph audit, targeted ruff, and `git diff --check` - passed.
- Phase 22 report conversion quality gate - passed: 13 focused backend tests, targeted ruff, frontend build, `git diff --check`, and a real Beijing force-smoke returning `report-itinerary-conversion:llm-v1`, D1 `王府井`, total budget 10000, and no placeholder text.
- Phase 23 ChatUI gate - passed: frontend `npm run build`, `git diff --check`, Playwright interaction smoke in system Chrome, and mobile viewport fit check. The dev server is running at `http://localhost:5174/`.
- Phase 24 chatbot gate - passed: `uv run python -m pytest tests/test_chatbot_agent.py tests/test_destination_intelligence_search.py tests/test_models_schemas.py -q` (17 tests), targeted `ruff check`, frontend `npm run build`, `git diff --check`, CodeGraph post-edit audit, and a real `TestClient` `/chatbot/message` ask smoke returning HTTP 200.
- Phase 25-30 Smart Travel Advisor focused backend gate - passed: `uv run python -m pytest tests/test_chatbot_agent.py tests/test_models_schemas.py tests/test_destination_intelligence_search.py -q` (48 tests).
- Phase 25-30 Smart Travel Advisor frontend gate - passed: `npm run build`; Vite still reports the existing large-chunk advisory.
- Phase 25-30 Smart Travel Advisor lint/check gate - passed: targeted `ruff check` and `git diff --check`.
- Phase 25-30 Smart Travel Advisor full backend gate - passed: `uv run python -m pytest tests -q` (185 tests).

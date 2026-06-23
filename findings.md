# Findings

## Report-aware History Follow-up (2026-06-22)

### Requested behavior

- Fix history “查看详情”: quick-planning records must always open the structured result page.
- Deep-planning records show three actions: itinerary/details, delete, and “查看 Report”.
- Existing reports under `backend/destination_intelligence_streamlit_reports` must appear in history even when they predate database-backed deep jobs.
- Report availability is independent of plan type: when a quick trip matches a report artifact, the same history card exposes all three actions.

### Artifact inventory and current bug

- The history button is disabled for every item whose `status` is not exactly `completed`. Quick records should instead use an explicit `has_itinerary` capability so legacy/matched records do not lose their result action because of report/job state.
- The report directory currently contains five Markdown reports: one legacy `deep_search_report_*` and four `travel_guide_*` files.
- Four travel-guide Markdown files have timestamp-correlated `state_*.json` metadata. Three state files are valid and provide the complete query, report title, five paragraphs, sources, timestamps, and final report. The Xiamen state file is zero bytes, so catalog loading must tolerate corrupt/missing state JSON.
- Report filenames use a sanitized/truncated query plus timestamp, not a database trip ID. Matching must therefore prefer explicit future metadata but support normalized destination/date/query overlap for existing artifacts.
- Standalone legacy Markdown has no state JSON; its H1 and filename must be enough to create a report-only history item.
- The current database contains three quick itineraries. `trip_汕头_2026-07-02` matches the valid 汕头 report by exact destination and date range; it should remain one card with itinerary detail plus Report capability. The 长沙 and 大理 quick rows do not match any report.
- Report-only deep items can still expose three distinct actions: “查看详情” renders the JSONized Markdown/sources page, “查看 Report” opens the raw Markdown endpoint, and “删除行程” removes the Markdown plus paired state file.
- Future Web deep generation should save into the same Streamlit report directory so newly generated artifacts automatically join this catalog.
- The merged live catalog now yields seven cards from three database trips plus five reports, with the 汕头 quick/report pair correctly deduplicated into one three-action card.
- Existing history/API tests assert membership rather than a fixed list total, so adding report-only items does not invalidate their intended contracts.

### Final report-aware behavior

- Quick itinerary capability is now independent of status/report fields, so all completed quick records can open the structured Result page.
- A matched Report augments rather than replaces a trip. The live 汕头 quick item exposes `has_detail=true`, `has_itinerary=true`, and `has_report=true` and is not duplicated as a report-only card.
- Unmatched Markdown reports appear as completed deep/history items. “查看详情” loads sanitized Markdown plus structured sources; “查看 Report” opens the raw Markdown; deletion removes the Markdown and paired state file.
- Corrupt or missing state JSON falls back to Markdown/filename metadata with an empty source list.
- Web deep jobs now write their Markdown/state pair into `backend/destination_intelligence_streamlit_reports`, so future completed jobs automatically receive Report capability.


## Destination Intelligence Web Integration (2026-06-22)

### Initial constraints

- Keep the existing `/trip/generate` behavior as “快速规划”.
- Add “深度规划” using `destination_intelligence_agent`, but submit it as background work and return immediately.
- Persist a history record before generation starts so it appears immediately with a progress indicator.
- While generating, details and deletion are disabled; terminal success restores actions. Failure behavior and retry affordance will be chosen after inspecting existing history semantics.
- Deep-plan details must load the generated Markdown through a structured JSON API and expose the Streamlit-equivalent “完整攻略” and “研究来源” content in the main Web app.
- Existing uncommitted RAG files are unrelated user work and must not be overwritten.

### Existing integration surface

- `backend/app/api/main.py` mounts the trip router on the FastAPI app and currently serves only a JSON health-style root; the Vue app is a separate Vite frontend.
- The current Vue app uses local view state rather than Vue Router: `App.vue` switches among `Home`, `Result`, and `History`, carrying one `Itinerary` object for the result page.
- `Home.vue` builds one `TripRequestPayload`, calls `POST /trip/generate`, waits synchronously, and emits the resulting `Itinerary`. The same form can supply both quick and deep modes without duplicating inputs.
- `History.vue` loads persisted summaries, fetches an itinerary detail before opening the result view, and deletes records. Its API/types must be generalized to discriminate quick trips from deep-plan jobs and to render job status/progress.
- The standalone Streamlit experience renders the final Markdown in “完整攻略” and iterates `agent.state.paragraphs[*].research.search_history` in “研究来源”, including source title/query, URL, content, relevance score, and publication date. The Web persistence contract must save both the Markdown and this structured source data before the in-memory agent is discarded.
- `DestinationIntelligenceAgent.research()` is synchronous and stateful but creates fresh state for every call. It exposes final Markdown as the return value and source history on `agent.state`; an API-owned background executor can wrap one independent agent per job.
- Existing persistence is a single SQLAlchemy `TripRecord` table accessed by synchronous storage helpers. A record stores `trip_id`, `destination`, `summary`, and the full itinerary as JSON; list/detail/delete routes all assume every record contains an `Itinerary`.
- Quick planning generation does not save automatically: `/trip/generate` returns an `Itinerary`, while `/trip/save` persists it. Deep planning differs intentionally because its placeholder must be persisted at submission time.
- The safest compatibility direction is to extend the record/schema into a tagged union-like response (`plan_type`, `status`, `progress`, display metadata, optional `itinerary`, optional deep-plan document) while keeping current quick-trip fields valid. Existing SQLite databases need runtime additive migration because `create_all()` does not add columns.
- The frontend API timeout is 120 seconds, reinforcing the need for a short deep-plan submission endpoint plus polling from history rather than holding an HTTP request open.
- Frontend trip history types currently have only `trip_id`, `destination`, `summary`, and timestamps; detail always requires an `Itinerary`. Both need optional deep-plan-specific fields and a discriminated detail payload.
- `TripRecord.itinerary_json` is currently non-nullable, so deep placeholders cannot fit without a schema/model change. The migration must either make it nullable or store a neutral `{}` while detail logic branches on `plan_type`; nullable is cleaner for new databases, while a migration must preserve legacy rows.
- Existing Pydantic list/detail schemas are compact and have no discriminator. New fields can default to `quick/completed/100` so legacy quick records and existing tests remain backward-compatible.
- `Home.vue` has one centered submit button and a single `isSubmitting`; it should become two sibling actions. Quick retains the current wait-and-open behavior, while deep submit should only be disabled during its short POST and then emit a navigation-to-history event.
- `History.vue` refreshes only on mount/activation/manual click. To show live progress without affecting other pages, poll only while the history view is active and at least one item is `generating`; stop the timer when no active jobs remain or on unmount.
- The existing history card title is only `destination` and subtitle is raw `trip_id`. Deep records need explicit `display_title` (the requested “地点哪到哪” style) and `detail_title` (full request-derived name), plus start/end dates so presentation does not depend on parsing an ID.
- Frontend dependencies do not include a Markdown renderer or sanitizer. Add `marked` plus `dompurify` so model-produced Markdown can be rendered with HTML sanitization instead of unsafe raw `v-html` or an unformatted `<pre>`.
- The backend uses file SQLite with `check_same_thread=False`, so a FastAPI synchronous background task can update progress from its worker thread through short independent sessions.
- Destination-agent `Settings` loads its own required LLM/Tavily keys from `backend/.env`; job submission can succeed immediately even if configuration is missing, and the background job should then transition the persisted record to `failed` with a safe message.

### Selected lifecycle and API contract

1. `POST /trip/deep-generate` validates the existing `TripRequest`, creates a `deep_*` record with `generating` status and initial progress, schedules background work, and returns the new summary with HTTP 202.
2. The worker formats all planning-page fields into a rich destination-agent query, updates milestone progress, calls `DestinationIntelligenceAgent.research(save_report=True)`, flattens source history, and atomically stores a completed deep-plan document. Exceptions transition the record to `failed`.
3. `GET /trip` returns quick and deep records together. Quick rows default to `quick/completed/100`; deep rows include status, progress, titles, and dates.
4. `GET /trip/{id}` returns an optional itinerary for quick records or an optional `{markdown, sources}` document for successful deep records. Generating records return a conflict response if detail is requested.
5. `DELETE /trip/{id}` rejects generating records with HTTP 409, while completed/failed deep records and existing quick trips can be deleted.
6. Vue `Home` emits a history-navigation event after deep submission. `History` polls while generating items exist and emits either a quick itinerary or deep document. `App` adds a fourth `deep-result` view/tab.

- The agent's `Search` state already serializes exactly the Streamlit source fields plus a timestamp; flattening can preserve section title and these fields without parsing the generated Markdown.
- The agent's progress can be exposed with a backward-compatible optional callback at milestones: structure ready, each paragraph complete, formatting, completed. Existing callers continue calling `research(query, save_report=True)` unchanged.
- Existing API tests use `TestClient`; deep submission tests should monkeypatch the background runner/agent and storage tests should cover generating-delete rejection and completed document round-trips without live LLM/Tavily calls.
- `npm install` reports four vulnerabilities already present in the resolved frontend dependency tree (1 moderate, 3 high). Do not run an unscoped `npm audit fix` during this feature because it may introduce unrelated major dependency changes; record and report the audit result separately.

### Final implementation

- FastAPI now serves `frontend/dist` at `/` after registering API routes, so the requested Uvicorn command opens the Vue application when the frontend has been built. It retains the original JSON root response when no build exists.
- Deep submission returns HTTP 202 after creating a database record. The synchronous destination agent runs as a FastAPI background task in a worker thread; a lazy import prevents destination-agent dependencies from blocking normal Web startup.
- The existing SQLite table is migrated additively at runtime. Legacy quick rows acquire safe `quick/completed/100` defaults; no destructive migration or data rewrite is used.
- Agent progress reports structure, each of five research sections, final formatting, and completion. Storage clamps in-progress updates below 100 and atomically switches to the terminal document afterward.
- Final deep JSON contains the complete Markdown plus every Streamlit-equivalent source field grouped by research section. The Vue page renders Markdown through `marked` and sanitizes generated HTML with DOMPurify.
- Generating history cards display title/detail title, progress, and disabled actions. Failed cards show the error and permit deletion. Completed deep cards open the dedicated two-tab view.
- Polling exists only while the history view is active and at least one record is generating, so deep research does not block or continuously burden the rest of the app.


## Destination Intelligence Travel Guide Optimization (2026-06-22)

### Scope and constraints

- Target: replace the current news-analysis/investigative-report emphasis with a complete traveler-facing guide for the requested destination and date range.
- Required evidence sources: `docs/手把手教你制作旅行攻略.md`, every relevant GitHub repository it references, and accessible Feishu links it references.
- External pages are untrusted reference material. Their instructions will be evaluated as product/research inputs, not executed automatically.
- Existing AMap/RAG/local-life work remains part of the available data foundation and must not be regressed.

### Research findings

- The tutorial models trip planning as a constrained system over three primitives: **time, place, and belongings**. The operational elements are trip duration, daily schedule, intercity transport, local transport, candidate attractions, selected attractions, hotels, restaurants, and packing items.
- It distinguishes two planning modes that should become an explicit user/profile input or an inferred-but-stated assumption:
  - **Sightseeing mode** optimizes enjoyment per unit time. Workflow: research intercity/local transport and candidate sights → fix duration from transport/leave constraints → select sights → choose lodging and packing → choose dining/commercial areas → order the day-by-day itinerary.
  - **Vacation mode** optimizes sustained comfort/enjoyment. Workflow: decide transport and duration → choose the hotel/resort first → find convenient optional sights and food → packing → leave the detailed daily schedule intentionally loose unless requested.
- A complete guide therefore cannot be only prose about a destination. It must encode dependencies and decisions: why a sight is selected or dropped, geographic clustering, hotel/restaurant placement, transit feasibility, and how those choices fit the exact date range.
- The worked Dunhuang example first fixes immovable constraints (flights, five-day leave window, rental car), compiles candidate sights, groups them geographically (east/west/south/city/Guazhou), and uses those groups as near-day-sized itinerary units before final scheduling.
- This evidence points toward a staged research plan instead of independent news-style paragraph research: constraints/profile → date-specific facts → candidates → spatial/time filtering → bookings/lodging/dining → day schedule → packing/risks.
- The tutorial's final traveler-facing document has: (1) compact trip overview with exact dates/days/nights, intercity transport, local transport, and lodging by date; (2) daily itinerary; (3) packing checklist; (4) traveler tips; while candidate attractions and source/reference notes are planning-only appendices that can be removed before sharing.
- Multi-city overviews need consistency validation because a date or night-count change propagates across transport and hotel bookings; this should be machine-checked rather than left only to prose generation.
- Daily scheduling is a constrained ordering of hotel, geographic attraction clusters, meal/commercial areas, opening/visit durations, and fixed reservations. Popular tickets must be identified with advance-booking advice.
- Packing is a reusable, conditional checklist. The tutorial uses four states: applicable to this trip, carry-on/day-bag, packed, and final verified. The generated guide should at minimum provide categorized, trip-specific items and mark why special gear is needed.
- Additional optional modules from the tutorial are flight price planning for complex/holiday multi-leg routes and trip expense/AA accounting.
- The referenced `greenzorro/hotel-comparer` repository extracts Ctrip hotel name, rating, review count, negative-review rate, and room attributes (name, area, windows, bed, smoking), then compares/export them to Excel. These fields define a useful hotel-comparison evidence matrix even if the agent cannot directly scrape Ctrip.
- All five Feishu template URLs were rejected by the generic web fetcher as unsafe to open, so their contents still require browser-based inspection.
- Browser inspection of the public **出行检查单** Feishu page confirms it is a read-only spreadsheet with at least `周末清单` and `旅游清单` sheets plus a `设置项` area. The unauthenticated page exposes sheet names but not loaded cell values; the tutorial remains the source for the four-stage checklist semantics.
- The public **旅行交通住宿规划** sheet explicitly implements a multi-city dependency workflow: define city and local transport first; then enter dates, city sequence, arrival/departure modes; then hotel data; finally copy an automatically generated red summary cell as plain text into the guide. This validates adding a deterministic itinerary-overview renderer/validator rather than asking the LLM to keep every date/night relationship consistent unaided.
- The public **旅行攻略模板** confirms separate sightseeing and vacation variants but the same high-level sections: itinerary, day-by-day D1...Dn (departure and return days explicit), packing checklist, tips, candidate attractions, and travelogue/guide references. The visible sightseeing day schema includes date, timed origin→destination movement, attraction sequence with per-attraction duration, and ticket notes.
- The completed **敦煌自驾深度游** example shows how the template becomes actionable: overview gives exact duration, rental-car logistics/airport transfer time, one fixed hotel and its distance to a night market; D1 gives exact flight times, attraction duration and reservation link/name, luggage-drop and meal sequencing, an optional nearby backup sight, evening food area, and a next-day provisioning warning because the western route has limited dining. This is materially different from destination journalism: it resolves traveler decisions and anticipates handoff failures.
- The public **机票规划** workbook is a read-only comparison/planning sheet; unauthenticated extraction only exposes its purpose (`比价规划行程`). Combined with the tutorial, it is an optional research aid for date-by-date fare comparison on complex or peak-holiday trips, not a mandatory core section of every guide.
- The public **旅行记账模板** workbook is organized around a concrete trip (`2021-敦煌`) and traveler count. Per the tutorial, category shares, total/per-person cost, and AA settlement are useful optional post-plan fields, but should not distract the core destination-guide agent unless budget/group inputs are present.

### Tutorial-derived target workflow

1. Normalize trip brief: destination(s), exact date range, origin, party, pace/mode, interests, budget, mobility/diet/child needs, fixed bookings.
2. Establish immutable/date-sensitive constraints: days/nights, arrival/departure windows, weather/season, closures, holidays/crowds, booking lead times, entry/visa/safety where relevant.
3. Research intercity and local mobility plus candidate attractions/experiences with evidence, duration, hours, booking, cost, accessibility, and geographic coordinates/areas.
4. Select and explain candidates using user fit, date availability, geographic clustering, transit time, fatigue and opening-hour feasibility; retain rejected/backup candidates separately.
5. Choose lodging area/property against the selected clusters and transport nodes using a comparison matrix (location, price/reference cost, rating/review evidence, room/amenity constraints, cancellation caveats).
6. Attach restaurants or commercial areas to attraction/hotel geography and meal times; handle sparse-service areas with provisioning/backup plans.
7. Build each day as a time-space chain with transfers, visit durations, meals, reservations, slack, alternatives, and return/lodging.
8. Generate trip-specific packing, booking checklist, practical tips, risk/contingency plan, budget summary when inputs permit, and source/update timestamps.
9. Run cross-section consistency checks over dates, nights, city sequence, transit feasibility, opening times, hotel coverage, duplicate attractions, meal gaps, and unsupported claims.
10. Render a concise traveler-facing guide first; keep candidate lists, research notes, uncertainty and references in a clearly separated appendix.

### Current destination-intelligence architecture

- `DestinationIntelligenceAgent.research(query)` runs: LLM-generated report outline → for each paragraph one LLM-chosen Tavily search and summary → configurable reflection searches/summaries → one final LLM formatting pass → Markdown file save.
- State is generic (`query`, `report_title`, paragraph title/content/research, `final_report`) and can support a travel guide without an immediate schema rewrite, but the original query is not explicitly passed into final formatting data.
- The search implementation already forces Tavily `topic='general'`; its `TavilyNewsAgency` and six `*_news` method names are semantic legacy, not a functional news-only API limitation.
- All five core prompts are explicitly news/investigation oriented:
  - outline: generic deep-research report, maximum five paragraphs;
  - first search/reflection: six “professional news search” tools, rumor/event reconstruction emphasis;
  - first summary: professional news analyst, 800–1200 Chinese characters per paragraph, event/multi-media/data/trend structure and heavy direct quotation;
  - final formatter: senior news/investigative editor, “deep investigation” title, event timelines/media comparison/trend/impact, minimum 10,000 Chinese characters.
- Default outline fallback is only “研究概述/深度分析”; default report title is `关于'<query>'的深度研究报告`. Both reinforce the wrong product shape even when LLM JSON parsing fails.
- No focused tests currently cover the destination-intelligence prompts, outline fallback, formatting behavior, or complete research orchestration. This optimization must add prompt-contract and deterministic-fallback tests.
- Final formatter receives only an array of `{title, paragraph_latest_state}`. To make exact dates, traveler assumptions, and cross-section consistency reliable, it should also receive the original trip query/context (either via a richer input contract or a dedicated context item).

### Implementation design

- Preserve the public `research(query, save_report=True) -> str` contract and generic paragraph state to limit blast radius.
- Replace all five prompt contracts with a traveler-facing workflow derived from the tutorial. The research outline will require five dependency-ordered sections (constraints/date intelligence; transport/lodging; candidates/geographic clusters/dining; day-by-day schedule; preparation/budget/risks/sources) so the existing paragraph loop remains bounded.
- Pass `trip_context` (the complete original request) into initial search, initial summary, reflection, reflection summary, and final formatting. Change final-format input to `{trip_context, report_title, sections}` while accepting the legacy section list in `ReportFormattingNode` for compatibility.
- Improve search evidence passed to the LLM: preserve result title, URL, publication date, score and content rather than stripping everything except content. This enables usable source links and freshness/authority judgment.
- Keep legacy `*_news` tool method names for API compatibility, but describe/use them as general web research functions. `search_news_by_date` is only for date-bounded announcements/events/closures, not as a substitute for researching future trip dates.
- Replace failure fallbacks (outline, title, manual final report, filename prefix) with travel-guide semantics, and reset agent state at the beginning of each new `research()` call to prevent paragraph accumulation across trips.
- Add focused unit tests for prompt coverage, default guide outline, richer search-result formatting, formatting input compatibility/context transmission, travel fallback output, and repeated-research state reset/context propagation where practical.

### Final implementation and audit

- The agent now researches exactly five dependency-ordered workstreams; malformed/incomplete LLM outlines fall back to all five rather than silently producing a partial guide.
- The original trip request is present in every LLM stage and the final formatter receives `{trip_context, report_title, sections}`. Legacy final-section lists remain valid for compatibility.
- The final guide contract covers every core tutorial module: exact trip overview; intercity/local transport and lodging by night; dated day-by-day time/place chains; attraction durations/tickets; dining/provisioning; packing; tips; candidates/backups; sources. It also adds booking deadlines, budget, risk plans and a cross-section consistency checklist.
- Search summaries now receive title, URL, publication date, relevance and content. Publication dates persist in state and appear in the standalone source UI.
- Date-filter semantics are now explicit: the Tavily date tool filters source publication dates, while the target trip dates belong in the query and applicability checks.
- The agent resets state for each `research()` call, saves files with a `travel_guide_` prefix, and uses travel-specific titles/fallback text/UI copy.
- Final exact-string audit found none of the former `新闻分析报告/调查报告/不少于一万字/新闻专业/新闻舆情/深度研究报告` language in the active destination-intelligence source or standalone UI.
- No paid/live LLM + Tavily end-to-end guide was generated during verification. Coverage instead uses deterministic prompt/contract/state tests plus the full backend suite; live factual quality still depends on configured providers, source availability, and the completeness of the user's trip brief.

### Final Markdown truncation diagnosis (2026-06-22)

- The generated Xiamen artifact is only 79 lines / 3,701 bytes and begins at the first consistency checklist checkbox. It lacks the requested overview, pre-booking actions, daily itinerary, transport/lodging, attraction/dining pool, packing list, budget, and practical-risk sections.
- Root cause is deterministic: `ReportFormattingNode.process_output()` sends Markdown through `remove_reasoning_from_output()`, a JSON helper that returns the substring beginning at the first `{` or `[`. The first `[` in a valid guide is the `[ ]` checklist marker, so every preceding Markdown section is discarded.
- A read-only minimal reproduction produced the exact observed shape: default title + first checkbox + following source section.
- The formatter currently validates only “non-empty” and “starts with heading”; it does not require the guide sections, so the truncated tail is accepted as success.
- The conversational closing (“如果你愿意，我下一步可以…”) is not hardcoded anywhere in the repository. The final prompt does not explicitly ban follow-up offers, and there is no final-artifact validator or sanitizer for chat-style calls to action.
- The failed state save left a zero-byte JSON file, so the five upstream research summaries cannot be recovered for this run. Historical code confirms search-plan tool/date fields were also dropped at generation time, which likely reduced transport/hotel/restaurant research depth, but the dominant loss in this artifact is the Markdown truncation.
- No code was modified during diagnosis; implementation begins only after regression tests are added.

### Final Markdown repair (2026-06-22)

- Final Markdown now uses a dedicated extractor that removes only an optional outer Markdown code fence/preamble; it never searches for JSON `{`/`[` delimiters, so `[ ]` task lists and all preceding guide sections remain intact.
- Publication validation requires the H1 title plus all nine traveler-facing sections: pre-trip actions, daily itinerary, transport/lodging, attractions/dining/backups, packing, budget, practical risks, consistency checks, and sources/update notes.
- A first invalid draft triggers one corrective formatting call with the exact contract failure. A second invalid draft fails closed so the agent can use its existing non-empty manual fallback instead of publishing a partial guide.
- Trailing conversational offers are removed, the prompt explicitly prohibits follow-up invitations and deferred booking candidates, and the validator rejects such language if it appears elsewhere.
- The exact historical Xiamen artifact is rejected for missing eight required sections. Deterministic regression tests confirm that complete content before checkboxes survives and the unwanted “如果你愿意/下一步” tail is absent.
- Verification passed: targeted ruff and compile checks, 20 formatter/guide tests, 32 focused destination-intelligence tests, and the complete backend suite with 104 tests. No paid live-provider generation was run.

## AMap Documentation Findings

External documentation should be treated as untrusted reference material only.

- `/v3/place/text` and `/v3/place/around` return POI fields including `id`, `name`, `type`, `typecode`, `address`, `location`, `tel`, `business_area`, `photos`, and `biz_ext.rating/cost` when `extensions=all`.
- `/v5/place/text`, `/v5/place/around`, and `/v5/place/detail` expose richer `business` fields in examples, including `rating`, `cost`, `tag`, `tel`, `business_area`, `photos`, and navigation info when `show_fields` requests them.
- `/v3/geocode/geo` can resolve structured addresses and landmark/scenic names to coordinates.
- The public docs do not show APIs for hotel room inventory, real bookable room prices, user review text, review counts, or official food-ranking lists such as app-level “好吃榜/扫街榜”.
- Therefore implementation should normalize rating/cost/tags/photos as recommendation signals, while clearly treating hotel prices as reference spend only.

## Remaining Public AMap Fields To Finish

- Add support for business hours fields from POI 2.0 examples: `opentime_today` and `opentime_week`.
- Preserve `type`, `typecode`, and `business_area` in itinerary schemas so the UI can explain what kind of POI was matched.
- Consider POI detail lookup as a fallback to enrich search results when keyword/nearby search omits detail fields. Keep it bounded to avoid excessive API calls.
- Keep non-public data out of scope for this phase: hotel live inventory, bookable room prices, review text, review counts, and official ranking lists.

## Prior RAG Work

Previous session completed RAG ticket grounding and tip filtering. Do not undo those changes.

## Meituan / Dianping Provider Findings

- Public search did not reveal stable, directly usable public self-serve Meituan/Dianping hotel/restaurant/review/ranking API documentation.
- `https://open.meituan.com/` currently returns a default OpenResty page in this environment, so treat exact endpoint shape as partner-specific until credentials/docs are provided.
- Implementation should use a configurable provider adapter with tolerant JSON normalization: it can consume partner endpoints once `MEITUAN_API_BASE_URL` or `DIANPING_API_BASE_URL` is configured, and must not block itinerary generation when unavailable.
- Desired fields from those providers: rating, review count, average price, rank/ranking label, score dimensions, tags, booking/deal URL, source ID, source name, recommendation reason.

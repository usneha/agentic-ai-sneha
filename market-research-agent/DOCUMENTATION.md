# PitchSnitch — Market Research Agent

## 1. Goal

PitchSnitch takes a single company or product name and produces a competitive
analysis without any manual input on who the competitors even are. It:

1. Discovers the top 3 real competitors via live web search (no hardcoded
   competitor list).
2. Researches each one in depth (pricing, positioning, customer sentiment,
   recent news), with every claim traceable to a source and rated for
   evidence quality and bias risk.
3. Synthesizes an executive summary across the whole competitive set.
4. Turns the analysis into a McKinsey-style strategy deck with a concrete
   recommendation (do now / do not blindly copy / watch).
5. Optionally hands that deck to the Gamma API to produce a designer-quality
   slide deck, instead of a hand-formatted one.

The point is not a generic "here's what these companies do" overview — every
node is built to produce *decision-useful* output: what customers are
actually comparing, where the target company is vulnerable, and what a PM or
strategy lead should do about it.

## 2. Who uses it, and how

- **Product managers / strategy teams** doing periodic competitive reviews —
  run it weekly or before a planning cycle instead of manually researching
  3 competitors from scratch each time.
- **Leadership-facing deliverable**: the Strategy Deck section is built for
  handing to executives directly (or generating a polished version via
  Gamma), not just for internal PM consumption.
- **Usage**: run `streamlit run app.py`, type a company/product name, click
  "Run Research Pipeline." Everything downstream (comparison grid, executive
  summary, strategy deck, exports) renders from that one input.

## 3. Pipeline steps, in order

The pipeline is a [LangGraph](https://github.com/langchain-ai/langgraph)
`StateGraph` defined in `graph.py`. It runs as one sequential flow with a
loop in the middle:

```
START
  │
  ▼
Discovery        (runs once)
  │
  ▼
Researcher  ◄────────┐  (runs once per competitor)
  │                  │
  ▼                  │
Analyst  ────────────┘  (runs once per competitor; loops back to
  │                       Researcher while competitors remain)
  │  (queue_router: empty queue → continue)
  ▼
Summary           (runs once)
  │
  ▼
Deck              (runs once)
  │
  ▼
 END
```

Steps, in plain terms:

1. **Discovery** — given the company name, finds exactly 3 named
   competitors via web search + an LLM call, explicitly excluding the
   company itself.
2. **Researcher** — for the next competitor in the queue, runs 5 different
   web searches in parallel (direct comparison, alternatives, switching
   language, complaints, recent news) and collects raw source snippets.
3. **Analyst** — turns that raw research into one structured
   `CompetitorReport`: positioning, pricing, feature comparison, customer
   praise/complaints, strategic read, and PM recommendations, each
   citation-backed.
4. Steps 2–3 repeat until all 3 competitors have a report (queue-driven
   loop, not a fixed `for` loop — see §5).
5. **Summary** — once all 3 reports exist, synthesizes one overall
   executive summary across the whole competitive set (not just a
   concatenation of the three).
6. **Deck** — turns the full analysis (all 3 reports + the overall summary)
   into a `SlideDeck`: a narrative spine, 8–12 insight-driven slides, and a
   final recommendation bucketed into do-now / don't-blindly-copy / watch.
7. **(UI-only, outside the graph) Gamma export** — the Streamlit app can
   optionally send the finished deck to the Gamma API to generate an
   actual designer-quality `.pptx`, as an alternative to the built-in
   `python-pptx` export. This is not a graph node; it's triggered
   on-demand from `app.py` after the graph has already finished, since it
   spends real Gamma credits and shouldn't run automatically.

## 4. Node-by-node description

All nodes operate on one shared `ResearchState` (a `TypedDict` in
`graph.py`):

| Field | Type | Meaning |
|---|---|---|
| `company` | `str` | The user's input, unchanged throughout the run |
| `competitor_queue` | `List[str]` | Competitors not yet researched; shrinks by one each `Researcher` pass |
| `current_target` | `str` | The competitor `Researcher`/`Analyst` are currently working on |
| `raw_data` | `str` | Raw search results for `current_target`, overwritten each loop |
| `final_reports` | `Annotated[List[dict], operator.add]` | Accumulates one `CompetitorReport` per loop iteration — the `operator.add` reducer is what makes this an *append*, not an overwrite |
| `overall_summary` | `str` | Set once by `Summary` |
| `deck` | `dict` | Set once by `Deck`; a `SlideDeck.model_dump()` |

### Discovery (`discovery_node`)
- Input: `company`.
- One DuckDuckGo search: `"Top 3 specific product competitors to {company} software"`.
- One LLM call (`gpt-4o-mini`) with structured output (`CompetitorList`)
  to extract exactly 3 names from the search snippets.
- A deterministic post-filter strips the company itself from the result if
  the LLM includes it anyway (it occasionally does, despite the prompt
  saying not to — see §6).
- Output: `competitor_queue` (3 names).

### Researcher (`researcher_node`)
- Pops the next competitor off `competitor_queue`.
- Runs 5 DuckDuckGo searches **in parallel** via a `ThreadPoolExecutor`
  (these are blocking I/O calls, so threading gives a real speedup despite
  the GIL): direct comparison, alternatives, switching language, customer
  complaints, recent news. A single combined query was tried first and
  rejected — it got dominated by SEO comparison-article content and rarely
  surfaced real news (see §6).
- No LLM call in this node — deliberately. Search is cheap and
  deterministic; there's nothing for an LLM to add here.
- Output: `current_target`, shortened `competitor_queue`, and `raw_data`
  (concatenated, labeled search results).

### Analyst (`analyst_node`)
- The only per-competitor LLM call (`gpt-4.1-mini` — see §6 for why not
  `gpt-4o-mini`).
- Structured output into `CompetitorReport`: executive summary, 3–5 cited
  sources (each rated for evidence quality and bias risk), positioning,
  3–5 feature-comparison rows, customer praise/complaints, pricing,
  strategic read, recommendations, open questions.
- Prompted explicitly to separate observed evidence from interpretation,
  distrust vendor pages/affiliate content, and write "Not found" rather
  than hallucinate.
- Output: appends one report to `final_reports`.

### Summary (`summary_node`)
- Runs once, after the competitor loop ends.
- Takes each report's `executive_summary` + `pricing.summary` and asks an
  LLM to synthesize *one* cross-competitor narrative — explicitly told not
  to just restate each competitor one by one.
- Output: `overall_summary`.

### Deck (`deck_node`)
- Runs once, after `Summary`.
- Flattens the entire analysis (all reports + overall summary) into one
  text blob (`_format_competitive_analysis`) and asks an LLM
  (`gpt-4.1-mini`) for a structured `SlideDeck`.
- Prompted with McKinsey-deck conventions: one argument per slide,
  full-sentence insight titles (not topic labels), "so what" on every
  slide, evidence over generic claims, and a default 12-slide storyline
  (executive takeaway → market context → positioning → decision drivers →
  product comparison → vulnerabilities → differentiation → strategic
  options → recommendation → roadmap → risks → source-quality appendix).
- Since the underlying analysis covers 3 competitors (not 2), slides that
  would normally compare "us vs. them" are explicitly told to synthesize
  across the whole competitive set instead.
- Output: `deck`.

### Gamma export (UI-triggered, not a graph node — `gamma_export.py`)
- `build_input_text` — flattens the `deck` dict into Gamma's card format:
  one `\n---\n`-separated card per slide (plus a title card, up to 3
  recommendation-bucket cards, and a caveats card).
- `build_additional_instructions` — passes each slide's `recommended_visual`
  (e.g. "2x2 matrix," "comparison table") as a hint string, since Gamma's
  own docs state specific visual-type instructions produce more reliable
  output than none.
- `create_generation` → `POST /v1.0/generations` with `textMode: "preserve"`
  (don't let Gamma rewrite our content) and `cardSplit: "inputTextBreaks"`
  (one card per `\n---\n`, not Gamma's auto-splitting).
- `poll_generation` → polls `GET /v1.0/generations/{id}` every 5s
  (`POLL_INTERVAL_SECONDS`) until `status` is `completed` or `failed`, capped
  at 300s (`POLL_TIMEOUT_SECONDS`) of wall-clock time.
- `download_export` → fetches the resulting `.pptx` bytes directly so the
  app can offer a real `st.download_button`, not just an outbound link.

## 5. Why a queue + conditional edge, not a fixed loop

`competitor_queue` is genuinely part of the graph's state, not a Python
`for` loop wrapped around the graph. `Analyst`'s outgoing edge is
conditional (`queue_router`): if `competitor_queue` is non-empty, control
returns to `Researcher`; once empty, it advances to `Summary`. This means
the number of research/analysis cycles is determined by what `Discovery`
actually found at runtime, not hardcoded to "3" anywhere in the control
flow — `Discovery` enforces "exactly 3" by slicing `competitors[:3]`, but
the loop itself works for any queue length.

## 6. What happens when something breaks

| Failure | What actually happens | Why / mitigation |
|---|---|---|
| LLM includes the target company in its own competitor list | `discovery_node` strips it via a deterministic case-insensitive filter after the LLM call | The prompt already says not to do this, but instruction-following isn't a hard constraint — seen to fail roughly 1-in-4 runs in testing. The filter is the actual guarantee, not the prompt. |
| A single combined search query for pricing+features+positioning+news | Replaced with 5 separate targeted queries | The combined query got dominated by SEO comparison-article content; "news"-style rewording alone caused entity collisions (e.g. "Coda" the productivity app vs. "Coda Octopus Group," an unrelated public company) when the disambiguating company name was dropped from the query. |
| `Analyst`/`Deck` LLM call hits the output token ceiling | `openai.LengthFinishReasonError`, pipeline run fails | Root cause: `gpt-4o-mini` caps output at 16,384 tokens, and the structured schemas (10+ nested fields, several list fields) could exceed that when the model didn't respect length hints. Fixed by (a) moving these calls to `gpt-4.1-mini` (32K output ceiling) and (b) adding explicit length/count caps to every field description (e.g. "at most 3 items," "max ~15 words") — list-size caps alone weren't sufficient; free-text field verbosity was the bigger contributor. |
| DuckDuckGo search under certain Python builds | `ValueError: Unsupported protocol version 0x304` from `ddgs`'s HTTP client | Caused by the system Python being linked against an old LibreSSL without TLS 1.3 support. Fixed by running the venv on a Python build linked against OpenSSL 3.x instead. Not handled in application code — it's an environment/venv concern. |
| Gamma generation fails | `GammaGenerationFailedError` raised by `poll_generation`, surfaced in the Streamlit UI as `st.error` | No retry — surfaced directly so the user can decide whether to re-trigger (which spends additional credits). |
| Gamma generation never reaches a terminal state | `GammaTimeoutError` after 300s, shown as `st.warning` (not a hard error) | The generation may still complete server-side past the timeout; the warning includes the `generationId` so it can be checked manually rather than treating a slow generation as a failure. |
| Gamma API key missing/invalid | `GAMMA_API_KEY` unset → `st.error` + `st.stop()` before any request; HTTP 401 → explicit "check your API key" message; HTTP 429 → `st.warning` (transient, not a config problem) | Distinguished by status code so the user isn't told to "check the key" for a rate limit. |
| Streamlit reruns wiping out results | Any widget click (including `st.download_button`) triggers a full script rerun; results computed only inside an `if st.button(...):` block disappear on the next rerun | Fixed by persisting `result`, `gamma_result`, `gamma_pptx_bytes`, and `gamma_error` in `st.session_state` and rendering them in blocks that run unconditionally every script execution, not just inside the button's own `if` block. A *new* "Run Research Pipeline" click explicitly clears the old `gamma_*` keys so a stale Gamma link from a previous company's run doesn't linger. |

General pattern: nothing in this pipeline silently swallows a failure — a
broken node raises, and the LangGraph run fails loudly rather than
producing a partial, silently-wrong report. The Gamma path is the
exception in tone (warnings vs. errors for transient/ambiguous cases),
since it's optional and user-triggered, not part of the core pipeline.

## 7. Setup

```bash
cd market-research-agent
python3.12 -m venv .venv   # use a Python build linked against OpenSSL, not LibreSSL
.venv/bin/pip install -r requirements.txt
cp .env.example .env       # then fill in the keys below
.venv/bin/streamlit run app.py
```

Required env vars (`.env`):
- `OPENAI_API_KEY` — used by Discovery/Analyst/Summary/Deck (`gpt-4o-mini` /
  `gpt-4.1-mini`).
- `GAMMA_API_KEY` — only required if using the optional "Generate Designer
  Deck with Gamma" button; requires a Gamma Pro/Ultra/Team/Business plan
  (no free tier).

No API key is needed for search — Discovery/Researcher use DuckDuckGo via
`ddgs`, which is free and unauthenticated.

## 8. Known limitations

- **News retrieval is best-effort.** DuckDuckGo's general text search has
  no dedicated news vertical; for competitor pairs with heavy
  comparison-article SEO, the "recent news" query can still come back
  mostly empty (`recent_news` legitimately says "Not found" rather than
  fabricating something).
- **Gamma's visual-type hints are not guaranteed.** `additionalInstructions`
  steers Gamma's layout choices but Gamma's own documentation states output
  is non-deterministic between runs.
- **No retry logic anywhere.** A transient search failure, LLM error, or
  Gamma 5xx fails the whole run rather than retrying — by design, to avoid
  silently masking a real problem, but it means flaky network conditions
  require a manual re-run.
- **Exactly 3 competitors, always.** `Discovery` slices to `competitors[:3]`
  regardless of how many the search/LLM actually surfaced; this is a fixed
  product decision, not a current limitation to fix.

## 9. Extension points

- **More research queries**: add entries to `RESEARCH_QUERIES` in
  `graph.py` — each runs in parallel automatically via the existing
  `ThreadPoolExecutor`.
- **A different LLM provider**: all model calls go through `_llm()` in
  `graph.py`; swapping `ChatOpenAI` for another LangChain chat model is a
  single-function change.
- **A different export target** (e.g. Google Slides, Notion): follow the
  `gamma_export.py` pattern — a standalone, Streamlit-agnostic module with
  an `on_progress` callback, wired into `app.py` via `st.session_state` the
  same way Gamma is.

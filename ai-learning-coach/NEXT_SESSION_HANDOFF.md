# Handoff Note — Compass Next-Generation Architecture Discussion

**Status: thinking-through-in-progress, no plan finalized, no implementation started.** This is a recap of a long design conversation, written so it can be picked back up later without re-deriving everything. Nothing below has been built. Several open questions are listed explicitly at the end — please don't treat the "resolved" sections as locked-in, just as the current best reasoning.

## Where this picks up from

Earlier in this project, two things were built and shipped in `ai-learning-coach` (all committed, 126 tests passing):
- A "learner-centered coaching path" (`src/compass/learner/`) running alongside the older skill_graph/planner path — `LearnerCoachProfile`, evidence-bounded LLM assessment/profile-update/recommendation (three single-shot calls, each with deterministic fallback), `compass learner init/add-source/coach/show/history`.
- Episodic history (`CoachingCycle`s appended, never overwritten) and evidence-memory scaling (bucket evidence by skill_id, cap per bucket, rather than reaching for embeddings/RAG — deliberately rejected as solving a scale problem this use case doesn't have).

This session picked up with: **"now let's talk tools in the architecture."** That question opened into a much bigger conversation about what "agentic" actually means for this project, and whether the current architecture (or even the current repo) is the right foundation for where the user wants to take it.

## The conversation, in order

**1. Tools audit.** Found that *zero* tool-calling exists anywhere in Compass — every LLM call, old path and new, is single-shot prompt-in/JSON-out. Distinguished "agentic pipeline" (fixed code orchestrates LLM calls — what Compass is) from "tool-using agent" (LLM picks its own tools). Concluded the current design was *correct* for the scope as understood at the time — adding tool-calling would have solved a problem that didn't exist yet.

**2. Reframe: conversational coaching.** User pushed back: "the idea of compass isn't for it to be a compass decides it all... a true AI learning coach still needs to be conversational." This reopened the question, but pointed at dialogue (CLI back-and-forth), not at tool-calling per se.

**3. The full user-flow vision.** User described an end-to-end flow: seed the coach with GitHub repos/docs/a stated goal → coach builds a full visible path to that goal, not just one next step → learner works a milestone, submits proof → coach assesses progress *within* that milestone (partial credit: "you've done 1 and 2, not 3 yet") → coach says ready-to-advance or not → learner can push back conversationally → every future interaction has full continuity (what was recommended before, where the learner is on the path).

This reframed the actual gap: **a roadmap/path model is the foundational missing piece, not conversation.** Conversation has nothing concrete to be about without milestones/sub-objectives to negotiate over.

**4. Scope confirmed as the full vision, including ReAct.** User: "ultimately I need all of this... tool calling, memory, failure modes... and ReAct loops." This locked in:
- Tool-calling *is* warranted, but narrowly: read-only, schema-validated lookups (not open-ended retrieval/embeddings) used during conversation, where pre-stuffing context doesn't work because the conversation branches unpredictably.
- The mechanism is a bounded ReAct loop (Thought → Action → Observation, capped iterations) per conversational turn, with every step traced — extending the existing `RunTrace`/`ToolCallRecord` habit one level deeper.
- "Failure modes" named as its own pillar: tool-argument validation (same id-checking pattern already used for evidence), tool-error-as-observation (never a crash), non-convergence fallback.

**5. Restart question.** User asked directly whether to start a fresh project. Recommendation given: don't fully clean-room rewrite — the reusable assets (evidence scanner, the cite-by-id grounding pattern, the skill taxonomy, the fallback discipline) are the actual foundation the bigger vision needs, not baggage. **Decided: new sibling repo, `ai-builder-compass`, alongside `ai-learning-coach`/`course-rag`/etc. — but port reusable pieces rather than rewrite from nothing.** Exact port list was being discussed when the user asked to see the full target architecture first, before deciding what's worth porting.

**6. Target architecture designed** (this is the bulk of the new thinking — see "Target architecture" section below for the concrete shape).

**7. Taxonomy governance tension — and its resolution.** Raised: can the LLM introduce a roadmap skill outside the existing 44-skill taxonomy? First proposal: closed taxonomy + async maintainer-review-and-promote pattern (reusing the existing `DivergenceFlag`/`EvidenceCorrection` precedent — same idea as "LLM said something divergent, flag it for human review, don't auto-trust it"). **User correctly identified a flaw**: that risks the coach turning to the *end user* mid-session and asking "does this seem like a real skill?" — which is the opposite of coaching; the learner came here for judgment they don't have.

Resolved into a cleaner separation (this is the most important single idea from this session):
- **Coaching judgment (what to recommend) is never constrained by the taxonomy.** The LLM can recommend anything with full confidence, exactly like a human mentor improvising — no committee, no pre-approved list gating what it's allowed to say.
- **What's tiered is only evidence-verification rigor**, and this isn't new machinery — it reuses the trust hierarchy that already exists (`SkillEvidence.evidence_type`: observed/inferred/synthesized; `source`: scan/llm). Taxonomy-backed recommendations get the high-trust tier (deterministic scanner pattern match). Off-taxonomy recommendations get the tier that already exists for exactly this case: self-reported reflection evidence, with the coach being transparent about it ("great next step — I can't auto-verify this one yet the way I can the others, so tell me what you did").
- Maintainer review/promotion of recurring off-taxonomy recommendations into the formal taxonomy happens **fully async**, never blocking or interrupting a live session.

**8. "Is this even agentic / is this solvable" — a confidence check, resolved.** Audited Compass against real agent properties (autonomy ✓, planning ✓ deterministic, memory ✓ deliberately built this session, grounding ✓ — the strongest part of the whole system, tool-selection-by-LLM ✗ not yet, iterative ReAct ✗ not yet). Used Anthropic's own workflow-vs-agent framing: a fixed-orchestration workflow with embedded LLM judgment is a legitimate, often *better* choice for well-defined tasks — not a lesser one. The taxonomy tension is a well-known, standardly-solved problem in many real domains (staged review/graduation cycles — medical coding, library classification, language stdlibs all do this), not a novel unsolved one. Conclusion: the doubt surfaced real edges in the design, which is the process working, not failing.

## Target architecture (designed, not yet built or finalized)

**Core insight:** a `LearningPath` is a reorganization of the existing skill taxonomy into a goal-directed sequence — not a new ungrounded concept. Every `SubObjective` is a `skill_id` from the existing taxonomy plus status/evidence.

```
LearningPath: path_id, learner_id, goal, milestones: list[PathMilestone],
              current_milestone_index, superseded_by (old paths kept, never deleted)

PathMilestone: milestone_id, title, goal, rationale,
               sub_objectives: list[SubObjective],
               status: not_started | in_progress | demonstrated | skipped

SubObjective: objective_id, skill_id, status, evidence_ids
```

- **Generation split**: deterministic code computes the valid milestone *sequence* (extends `planner.py`'s existing prerequisite/activation-gate graph logic into a multi-step chain — same "tools decide structure" precedent already used everywhere in this project); LLM writes the human-facing title/goal/rationale per milestone, validated (every skill_id must be real), with a thin deterministic fallback (plain skill/domain names) if the LLM is unavailable.
- **Milestone-scoped assessment**: `assess_learner` narrows from an unscoped capability list to "progress against *this milestone's* sub-objectives specifically" — direct reuse of `select_evidence_for_coaching`'s skill-bucketing, just scoped to one milestone's skill_ids instead of everything.
- **Conversation**: bounded ReAct loop, two triggers — clarify (material uncertainty surfaced by assessment) and negotiate-readiness (coach says ready-to-advance, learner disagrees). Three read-only tools: `get_evidence_for_subobjective(milestone_id, objective_id)`, `get_path_milestone(milestone_id)`, `get_last_recommendation()`. Tool args validated the same way evidence ids are validated today.
- **Failure modes**: tool-arg validation, tool-error-as-observation, loop-iteration cap with flat honest fallback, full step trace (Thought/Action/Observation) extending the `RunTrace`/`ToolCallRecord` pattern one level deeper.
- **Build order discussed**: (1) Path/Milestone/SubObjective model + deterministic sequencing + CLI view, (2) milestone-scoped assessment, (3) ReAct conversation with tools, (4) failure-mode hardening — though (4) is mostly designed into (1)-(3) already, not separate net-new work.

## Open questions — not yet decided

1. **Port list for the new `ai-builder-compass` repo.** Three options were on the table when the conversation moved to designing the target architecture instead: (a) taxonomy YAML + `_data.py` + `evidence/scanner.py` + the grounding pattern (`learner/models.py`'s EvidenceItem/EvidenceSource/Claim shapes, `validation.py`, `coach.py`'s seam/parse/fallback skeleton) — recommended; (b) smaller, just taxonomy + scanner; (c) larger, also port CLI scaffolding (`cli.py` conventions) and the test harness pattern (`conftest.py` seam-monkeypatching). **Not decided.**
2. **Phase 1 scope.** Pure deterministic skeleton (plain skill names as milestone titles) vs. deterministic skeleton + thin LLM narrative layer from the start. **Not decided.**
3. **Does the judgment-vs-verification-tier resolution (point 7 above) retroactively change anything in the *current* `ai-learning-coach` learner-coach pipeline**, or does it only apply going forward in the new repo's roadmap feature? E.g., should today's `recommend_next_challenge` already be honest about "this is grounded in the taxonomy" vs. not? Worth deciding before porting `coach.py`'s pattern wholesale.
4. **Taxonomy closedness for the roadmap specifically** — resolved in principle (recommendation is never gated, only verification rigor is tiered) but not yet written into a concrete spec for how `SubObjective` represents an off-taxonomy entry (does it even get a `skill_id`? a placeholder? a different shape entirely?).

## Recommended next steps when resuming

1. Decide the port list (open question 1).
2. Decide Phase 1 scope (open question 2).
3. Decide whether/how the judgment-vs-verification-tier idea changes the pattern being ported (open question 3) — this probably needs deciding *before* porting, not after, since it affects what `coach.py`'s skeleton should look like in the new repo.
4. Resolve open question 4 (off-taxonomy `SubObjective` shape) — likely the last real design gap before this is buildable.
5. Then: scaffold `ai-builder-compass` as a new git repo (sibling to `ai-learning-coach`), port the decided files, write a concrete Phase 1 implementation plan (models, deterministic sequencing function, CLI command to view a path), and build it the same incremental way the rest of this project has been built — small steps, tested, committed.

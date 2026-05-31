import json
import os
import re
import subprocess


EXPLANATION_STYLE_LABELS = [
    "Use analogies",
    "Show the math",
    "Connect to real examples",
    "Be concise",
    "Give me the intuition first",
]

DETAIL_LEVEL_INSTRUCTIONS = {
    "concise": "Be concise — key points only, no elaboration.",
    "standard": "Provide balanced depth — enough to understand, not exhaustive.",
    "deep": "Be comprehensive — don't skip nuance, edge cases, or derivations.",
}


def build_prompt(topic: str, sources: list[dict], profile: dict | None) -> str:
    sources_text = "\n\n".join(
        f"--- Source: {s['name']} ---\n{s['content']}" for s in sources
    )

    profile_block = ""
    if profile and profile.get("background"):
        styles = ", ".join(profile.get("explanation_styles") or [])
        detail_level = profile.get("detail_level", "standard")
        detail = DETAIL_LEVEL_INSTRUCTIONS.get(detail_level, "")
        profile_block = f"""
User background: {profile['background']}
Explanation preferences: {styles or "none specified"}
Detail level ({detail_level}): {detail}

For the "journal" field: write a personal explanation tailored to this user.
Match their background — skip things they already know well.
Use their preferred explanation style.
"""

    prompt = f"""You are writing deep understanding notes on a topic — the kind an expert writes to capture their mental model for future reference, not to introduce the topic to a newcomer.

Topic: {topic}

Source materials:
{sources_text}

{profile_block}

---

EXAMPLE of the exact journal style (on a different topic — gradient descent):

"The core insight is that gradient descent isn't really about finding the minimum — it's about following the direction of steepest local improvement, one small step at a time. The gradient tells you which way is uphill; you go the opposite direction. What makes this non-obvious is that the gradient is only valid locally. Take too large a step and you overshoot, because the landscape curved while you were walking in a straight line. This is why learning rate matters so much: it's not a tuning knob, it's a statement about how much you trust your local gradient estimate.

The reason SGD works better than full-batch gradient descent in practice has nothing to do with computation alone. Noisy gradients from small batches act as regularization — they prevent the optimizer from settling into sharp minima that don't generalize. The noise is a feature. Flat minima generalize better because small perturbations to the weights don't change the loss much, and stochastic noise naturally steers toward them.

Momentum makes more sense when you think of it as a running average of past gradients rather than 'acceleration.' It dampens oscillations in high-curvature directions while letting you move faster in low-curvature ones. Adam goes further by adapting the learning rate per parameter — parameters with historically large gradients get smaller updates, which matters enormously in sparse settings like embeddings."

---

Rules — follow these exactly:
- Start with the core intuition: the ONE thing that makes the topic click. Why does it exist? What breaks without it?
- Show the mental model an expert holds, not a list of facts
- Make non-obvious connections: why does A cause B? What's the surprising consequence of C?
- Flag what's commonly misunderstood or counterintuitive
- Use analogies only when they sharpen understanding, not to fill space
- NO bullet points. NO headers. NO lists. Flowing prose only, building paragraph by paragraph.
- DO NOT start with "The core insight is" — that's just the example. Find your own opening that fits the topic.
- Length: 3–5 tight paragraphs. Dense with insight, zero padding.

Rules for the "summary" field:
- 3–5 sentences. Each one a crisp non-obvious insight. Not restatements of the topic name.

Return ONLY a JSON object with this exact schema — no markdown fences, no extra text:
{{
  "summary": "3-5 crisp non-obvious insights from the sources",
  "journal": "3-5 paragraphs of flowing prose that builds the core mental model",
  "concepts": ["key term or concept 1", "key term or concept 2"],
  "resources": [{{"title": "resource title", "type": "Paper|Book|Article|Video|Blog", "description": "one line on why it's useful"}}]
}}
"""
    return prompt


def parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": f"Could not parse Claude's response. Raw output: {cleaned[:200]}"}


def generate_journal(topic: str, sources: list[dict], profile: dict | None) -> dict:
    if not sources:
        return {"error": "No sources provided. Add at least one source before generating."}

    prompt = build_prompt(topic, sources, profile)
    # Strip CLAUDECODE to prevent Claude CLI from detecting a nested invocation and refusing to run
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            ["claude", "--print", "--output-format", "text", "--model", "claude-sonnet-4-6", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
    except FileNotFoundError:
        return {"error": "claude CLI not found. Make sure Claude Code is installed and on your PATH."}
    except subprocess.TimeoutExpired:
        return {"error": "Generation timed out after 120 seconds. Try with fewer or shorter sources."}

    if result.returncode != 0:
        return {"error": f"Claude CLI error: {result.stderr.strip()}"}

    return parse_response(result.stdout)

import time
from typing import Callable, Optional

import requests

GAMMA_BASE_URL = "https://public-api.gamma.app/v1.0"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300
MAX_INPUT_TEXT_CHARS = 400_000


class GammaAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GammaGenerationFailedError(Exception):
    pass


class GammaTimeoutError(Exception):
    pass


def build_input_text(deck: dict, company_name: str) -> str:
    cards = [
        f"# {deck['deck_title']}\n\n{deck['narrative_spine']}\n\n"
        f"*Competitive Strategy Deck — {company_name}*"
    ]

    for slide in deck["slides"]:
        cards.append(
            f"# {slide['title']}\n\n"
            f"{slide['main_message']}\n\n"
            f"{slide['slide_content']}\n\n"
            f"**Evidence:** {slide['evidence_to_cite']}"
        )

    roadmap = deck["final_recommendation"]
    for label, key in [
        ("Recommendation: Do Now", "do_now"),
        ("Recommendation: Do Not Blindly Copy", "do_not_blindly_copy"),
        ("Recommendation: Watch", "watch"),
    ]:
        actions = roadmap[key]
        if not actions:
            continue
        bullets = "\n".join(
            f"- **{a['action']}** (Owner: {a['owner_type']}, Confidence: {a['confidence']}, "
            f"Evidence quality: {a['evidence_quality']}) — {a['rationale']}"
            for a in actions
        )
        cards.append(f"# {label}\n\n{bullets}")

    cards.append(f"# Evidence Caveats\n\n{deck['evidence_caveats']}")

    input_text = "\n---\n".join(cards).strip()
    if len(input_text) > MAX_INPUT_TEXT_CHARS:
        raise ValueError(
            f"Gamma input text is {len(input_text)} chars, exceeding the "
            f"{MAX_INPUT_TEXT_CHARS} char limit."
        )
    return input_text


def build_additional_instructions(deck: dict) -> str:
    return "\n".join(
        f'On the slide "{slide["title"]}", use a {slide["recommended_visual"]}.'
        for slide in deck["slides"]
    )


def create_generation(
    input_text: str, api_key: str, additional_instructions: Optional[str] = None
) -> tuple:
    body = {
        "inputText": input_text,
        "textMode": "preserve",
        "format": "presentation",
        "cardSplit": "inputTextBreaks",
        "exportAs": "pptx",
        "cardOptions": {"dimensions": "16x9"},
    }
    if additional_instructions:
        body["additionalInstructions"] = additional_instructions

    try:
        response = requests.post(
            f"{GAMMA_BASE_URL}/generations",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise GammaAPIError(f"Could not reach Gamma: {e}", status_code=None)

    if not response.ok:
        raise GammaAPIError(
            f"Gamma returned {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )

    data = response.json()
    return data["generationId"], data.get("warnings")


def poll_generation(
    generation_id: str, api_key: str, on_progress: Optional[Callable[[str], None]] = None
) -> dict:
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if elapsed > POLL_TIMEOUT_SECONDS:
            raise GammaTimeoutError(
                f"Timed out waiting for Gamma generation {generation_id} after "
                f"{int(elapsed)}s. It may still complete server-side."
            )

        try:
            response = requests.get(
                f"{GAMMA_BASE_URL}/generations/{generation_id}",
                headers={"X-API-KEY": api_key},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            raise GammaAPIError(f"Could not reach Gamma: {e}", status_code=None)

        if not response.ok:
            raise GammaAPIError(
                f"Gamma returned {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
            )

        data = response.json()
        status = data.get("status")

        if on_progress:
            on_progress(f"Status: {status} (elapsed {int(elapsed)}s)")

        if status == "completed":
            return data
        if status == "failed":
            raise GammaGenerationFailedError(data.get("error") or data)

        time.sleep(POLL_INTERVAL_SECONDS)


def download_export(export_url: str) -> bytes:
    try:
        response = requests.get(export_url, timeout=60)
    except requests.exceptions.RequestException as e:
        raise GammaAPIError(f"Could not download Gamma export: {e}", status_code=None)

    if not response.ok:
        raise GammaAPIError(
            f"Gamma export download returned {response.status_code}",
            status_code=response.status_code,
        )
    return response.content


def generate_deck(
    deck: dict,
    company_name: str,
    api_key: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    input_text = build_input_text(deck, company_name)
    additional_instructions = build_additional_instructions(deck)
    generation_id, warnings = create_generation(input_text, api_key, additional_instructions)
    if warnings and on_progress:
        on_progress(f"Gamma warnings: {warnings}")
    return poll_generation(generation_id, api_key, on_progress=on_progress)

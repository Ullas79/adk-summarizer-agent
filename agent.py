"""
agent.py — ADK Agent backed by Vertex AI.

Authentication is handled automatically by Application Default Credentials
(ADC). On Cloud Run the attached service account is used; locally you run
`gcloud auth application-default login`.

The GOOGLE_GENAI_USE_VERTEXAI=1 env var tells the google-genai SDK to route
all inference calls through Vertex AI instead of Google AI Studio, so no
API key is ever needed.
"""

import os

from google.adk.agents import Agent

from config import get_settings
from logger import get_logger

log = get_logger(__name__)


def _ensure_vertex_env() -> None:
    """Apply Vertex AI routing env vars before the ADK runner boots."""
    cfg = get_settings()

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", cfg.google_genai_use_vertexai)
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", cfg.google_cloud_project)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", cfg.google_cloud_location)

    log.info(
        "Vertex AI routing configured",
        project=cfg.google_cloud_project,
        location=cfg.google_cloud_location,
        model=cfg.gemini_model,
    )


def create_summarizer_agent() -> Agent:
    """
    Build and return the ADK summarization agent.

    The agent uses Gemini on Vertex AI to produce concise, structured
    summaries. It is intentionally stateless — every HTTP request creates
    its own ADK session.
    """
    _ensure_vertex_env()
    cfg = get_settings()

    system_instruction = f"""
You are a professional text summarisation assistant running on Google Cloud.

## Your task
When the user submits a piece of text, return ONLY a well-structured summary.

## Output format
Always respond in this exact JSON structure (no markdown fences, no extra text):
{{
  "summary": "<{cfg.summary_min_sentences}–{cfg.summary_max_sentences} sentence prose summary>",
  "key_points": ["<point 1>", "<point 2>", "<point 3>"],
  "word_count_estimate": <integer — approximate word count of the original text>,
  "language": "<ISO 639-1 language code of the input, e.g. en, fr, de>"
}}

## Rules
- Keep the summary to {cfg.summary_min_sentences}–{cfg.summary_max_sentences} sentences.
- Preserve key facts, entities, dates, and conclusions.
- key_points must be 3 distinct, concrete takeaways — not rephrasing of the summary.
- Do NOT add opinions, warnings, or disclaimers.
- Do NOT reproduce the original text verbatim.
- Match the language of the input (summary + key_points in the same language).
- Always return valid JSON. Never wrap it in ```json``` fences.
""".strip()

    agent = Agent(
        name="summarizer",
        model=cfg.gemini_model,
        description=(
            "Summarises any text into a concise prose summary plus three key points. "
            "Powered by Gemini on Vertex AI."
        ),
        instruction=system_instruction,
    )

    log.info("ADK agent created", agent_name=agent.name, model=cfg.gemini_model)
    return agent

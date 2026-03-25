"""
LLM-based resume summarization service.

Supports OpenRouter (recommended for cloud hosting), Groq, and HuggingFace.
Includes automatic retry with fallback models when free models are rate-limited.
"""

import frappe
import json
import time


# ---------------------------------------------------------------------------
# Provider configurations
# ---------------------------------------------------------------------------
PROVIDERS = {
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "google/gemma-3-27b-it:free",
        "fallback_models": [
            "google/gemma-3-27b-it:free",
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "qwen/qwen3-32b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
        "fallback_models": [],
    },
    "HuggingFace": {
        "url": "https://api-inference.huggingface.co/models/{model}/v1/chat/completions",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
        "fallback_models": [],
    },
}

# Max retries per model before moving to next fallback
MAX_RETRIES_PER_MODEL = 2
RETRY_DELAY_SECONDS = 3

# ---------------------------------------------------------------------------
# System prompt for resume summarization
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert HR recruiter assistant. Your job is to analyze resume text and produce a concise, structured summary for hiring managers.

Produce a summary in the following format:

**Professional Summary:** 2-3 sentences capturing who this person is professionally.

**Key Skills:** Comma-separated list of top 8-10 technical and soft skills.

**Experience Highlights:**
- Most recent/relevant role and key achievements (1-2 lines)
- Second most relevant role (1-2 lines)
- Any other notable experience (1 line)

**Education:** Degree(s), institution(s), graduation year(s).

**Certifications & Awards:** Any notable certifications or awards (or "None listed").

**Overall Fit Notes:** 1-2 sentences on strengths, potential concerns, or standout qualities.

Keep the summary under 300 words. Be factual — only include information present in the resume. If a section has no data, write "Not specified in resume."
"""


def summarize_resume(resume_text: str) -> str:
    """
    Send resume text to the configured LLM provider and return a structured summary.
    Automatically retries with fallback models if rate-limited.
    """
    import requests as req_lib

    logger = frappe.logger("resume_parser")

    settings = _get_settings()
    provider_name = settings.get("llm_provider", "OpenRouter")
    api_key = settings.get("api_key")
    custom_model = settings.get("model_name")

    logger.info(f"[RESUME PARSER] Provider: {provider_name}")

    if not api_key:
        frappe.throw(
            "Resume Parser API key not configured. "
            "Go to Resume Parser Settings to add your API key.",
            title="Resume Parser Setup Required",
        )

    provider = PROVIDERS.get(provider_name)
    if not provider:
        frappe.throw(f"Unknown LLM provider: {provider_name}")

    url = provider["url"]

    # Build the list of models to try
    if custom_model:
        models_to_try = [custom_model]
    else:
        fallbacks = provider.get("fallback_models", [])
        if fallbacks:
            models_to_try = list(fallbacks)
        else:
            models_to_try = [provider["default_model"]]

    # Truncate very long resumes to avoid token limits
    max_chars = 15000
    if len(resume_text) > max_chars:
        resume_text = resume_text[:max_chars] + "\n\n[Resume truncated due to length]"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if provider_name == "OpenRouter":
        headers["HTTP-Referer"] = frappe.utils.get_url()
        headers["X-Title"] = "Frappe Resume Parser"

    last_error = None

    for model in models_to_try:
        model_url = url.format(model=model)

        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            logger.info(f"[RESUME PARSER] Trying {model} (attempt {attempt}) at {model_url}")

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Please analyze and summarize the following resume:\n\n{resume_text}",
                    },
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            }

            try:
                response = req_lib.post(
                    model_url,
                    json=payload,
                    headers=headers,
                    timeout=90,
                )

                status_code = response.status_code
                body = response.text

                logger.info(f"[RESUME PARSER] {model} returned {status_code}")

                if status_code == 200:
                    result = response.json()
                    summary = result["choices"][0]["message"]["content"]
                    logger.info(f"[RESUME PARSER] Success with {model}")
                    return summary.strip()

                if status_code == 429:
                    last_error = f"[{provider_name}] {model} rate-limited (429)"
                    logger.warning(f"[RESUME PARSER] {last_error}, body: {body[:200]}")

                    if attempt < MAX_RETRIES_PER_MODEL:
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    else:
                        # Move to next fallback model
                        logger.info(f"[RESUME PARSER] {model} exhausted retries, trying next model")
                        break

                # Non-429 error — don't retry, report immediately
                error_detail = f"[{provider_name}] {model} returned {status_code}: {body[:300]}"
                logger.error(f"[RESUME PARSER] {error_detail}")
                frappe.throw(error_detail)

            except frappe.exceptions.ValidationError:
                raise

            except Exception as e:
                last_error = f"[{provider_name}] {model} — {type(e).__name__}: {str(e)[:200]}"
                logger.error(f"[RESUME PARSER] {last_error}")

                if attempt < MAX_RETRIES_PER_MODEL:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                else:
                    break

    # All models exhausted
    frappe.throw(
        f"All models rate-limited. Last error: {last_error}. "
        "Try again in a few minutes, or add credits to your OpenRouter account "
        "to remove free-tier rate limits."
    )


def _get_settings() -> dict:
    """Load Resume Parser Settings as a dict."""
    try:
        settings_doc = frappe.get_single("Resume Parser Settings")
        return {
            "llm_provider": settings_doc.llm_provider,
            "api_key": settings_doc.get_password("api_key"),
            "model_name": settings_doc.model_name,
        }
    except Exception:
        frappe.throw(
            "Resume Parser Settings not found. Please configure the app first.",
            title="Resume Parser Setup Required",
        )

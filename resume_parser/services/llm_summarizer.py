"""
LLM-based resume summarization service.

Supports Anthropic (Claude), OpenRouter, Groq, and HuggingFace.
Includes automatic retry with fallback models when free models are rate-limited.
"""

import frappe
import json
import time


# ---------------------------------------------------------------------------
# Provider configurations
# ---------------------------------------------------------------------------
PROVIDERS = {
    "Anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-sonnet-4-20250514",
        "fallback_models": [],
        "is_anthropic": True,
    },
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "fallback_models": [
            "nvidia/nemotron-3-super-120b-a12b:free",
            "minimax/minimax-m2.5:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "arcee-ai/trinity-large-preview:free",
        ],
        "is_anthropic": False,
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
        "fallback_models": [],
        "is_anthropic": False,
    },
    "HuggingFace": {
        "url": "https://api-inference.huggingface.co/models/{model}/v1/chat/completions",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
        "fallback_models": [],
        "is_anthropic": False,
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
    provider_name = settings.get("llm_provider", "Anthropic")
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

    # Truncate very long resumes to avoid token limits
    max_chars = 15000
    if len(resume_text) > max_chars:
        resume_text = resume_text[:max_chars] + "\n\n[Resume truncated due to length]"

    # --- Anthropic uses a different API format ---
    if provider.get("is_anthropic"):
        return _call_anthropic(req_lib, logger, provider, api_key, custom_model, resume_text)

    # --- OpenAI-compatible providers (OpenRouter, Groq, HuggingFace) ---
    return _call_openai_compat(req_lib, logger, provider, provider_name, api_key, custom_model, resume_text)


def _call_anthropic(req_lib, logger, provider, api_key, custom_model, resume_text):
    """Call the Anthropic Messages API."""
    model = custom_model or provider["default_model"]
    url = provider["url"]

    logger.info(f"[RESUME PARSER] Calling Anthropic: {url}, model: {model}")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model": model,
        "max_tokens": 1024,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": f"Please analyze and summarize the following resume:\n\n{resume_text}",
            }
        ],
    }

    try:
        response = req_lib.post(url, json=payload, headers=headers, timeout=90)
        status_code = response.status_code
        body = response.text

        logger.info(f"[RESUME PARSER] Anthropic returned {status_code}")

        if status_code == 200:
            result = response.json()
            # Anthropic returns content as a list of blocks
            content_blocks = result.get("content", [])
            summary = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    summary += block.get("text", "")
            logger.info("[RESUME PARSER] Success with Anthropic")
            return summary.strip()

        error_detail = f"[Anthropic] {model} returned {status_code}: {body[:300]}"
        logger.error(f"[RESUME PARSER] {error_detail}")

        if status_code == 401:
            frappe.throw("Invalid Anthropic API key. Check Resume Parser Settings.")
        elif status_code == 429:
            frappe.throw(f"[Anthropic] Rate limit exceeded. Please wait a moment and retry. Details: {body[:200]}")
        else:
            frappe.throw(error_detail)

    except frappe.exceptions.ValidationError:
        raise

    except Exception as e:
        msg = f"[Anthropic] {type(e).__name__}: {str(e)[:300]}"
        logger.error(f"[RESUME PARSER] {msg}")
        frappe.throw(msg)


def _call_openai_compat(req_lib, logger, provider, provider_name, api_key, custom_model, resume_text):
    """Call OpenAI-compatible providers (OpenRouter, Groq, HuggingFace) with fallback."""
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
                "temperature": 0,
                "max_tokens": 1024,
                "seed": 42,
            }

            try:
                response = req_lib.post(
                    model_url, json=payload, headers=headers, timeout=90,
                )

                status_code = response.status_code
                body = response.text

                logger.info(f"[RESUME PARSER] {model} returned {status_code}")

                if status_code == 200:
                    result = response.json()
                    summary = result["choices"][0]["message"]["content"]
                    logger.info(f"[RESUME PARSER] Success with {model}")
                    return summary.strip()

                if status_code in (429, 404):
                    # 429 = rate limited, 404 = model not available — try next
                    last_error = f"[{provider_name}] {model} returned {status_code}: {body[:200]}"
                    logger.warning(f"[RESUME PARSER] {last_error}")

                    if attempt < MAX_RETRIES_PER_MODEL and status_code == 429:
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    else:
                        break

                # Other errors — report immediately
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
        f"All models failed. Last error: {last_error}. "
        "Try again in a few minutes, or switch to Anthropic (Claude) "
        "in Resume Parser Settings for reliable results."
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

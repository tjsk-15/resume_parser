"""
LLM-based resume summarization service.

Supports OpenRouter (recommended for cloud hosting), Groq, and HuggingFace.
Uses the `requests` library (bundled with Frappe) for reliable HTTP calls.
"""

import frappe
import json
import requests


# ---------------------------------------------------------------------------
# Provider configurations
# ---------------------------------------------------------------------------
PROVIDERS = {
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
    },
    "HuggingFace": {
        "url": "https://api-inference.huggingface.co/models/{model}/v1/chat/completions",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
    },
}

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

    Args:
        resume_text: Plain text extracted from the resume PDF

    Returns:
        Structured summary string

    Raises:
        frappe.ValidationError: If API call fails or settings are missing
    """
    logger = frappe.logger("resume_parser")

    settings = _get_settings()
    provider_name = settings.get("llm_provider", "OpenRouter")
    api_key = settings.get("api_key")
    custom_model = settings.get("model_name")

    logger.info(f"Using LLM provider: {provider_name}")

    if not api_key:
        frappe.throw(
            "Resume Parser API key not configured. "
            "Go to Resume Parser Settings to add your API key.",
            title="Resume Parser Setup Required",
        )

    provider = PROVIDERS.get(provider_name)
    if not provider:
        frappe.throw(f"Unknown LLM provider: {provider_name}")

    model = custom_model or provider["default_model"]
    url = provider["url"].format(model=model)

    logger.info(f"Calling {url} with model {model}")

    # Truncate very long resumes to avoid token limits (approx 12k tokens)
    max_chars = 15000
    if len(resume_text) > max_chars:
        resume_text = resume_text[:max_chars] + "\n\n[Resume truncated due to length]"

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

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # OpenRouter requires these headers
    if provider_name == "OpenRouter":
        headers["HTTP-Referer"] = frappe.utils.get_url()
        headers["X-Title"] = "Frappe Resume Parser"

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=90,
        )

        logger.info(f"Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            summary = result["choices"][0]["message"]["content"]
            logger.info("Resume summary generated successfully")
            return summary.strip()

        # Handle errors
        error_body = response.text[:500]
        logger.error(f"LLM API error ({response.status_code}): {error_body}")

        if response.status_code == 401:
            frappe.throw(
                f"Invalid {provider_name} API key. "
                "Please check your Resume Parser Settings."
            )
        elif response.status_code == 403 and "1010" in error_body:
            frappe.throw(
                f"{provider_name} is blocking requests from this server "
                "(Cloudflare error 1010). Switch to OpenRouter in "
                "Resume Parser Settings."
            )
        elif response.status_code == 429:
            frappe.throw(
                "LLM API rate limit exceeded. The summary will be retried "
                "automatically. You can also click 'Parse Resume' to retry manually."
            )
        else:
            frappe.throw(
                f"LLM API error ({response.status_code}): {error_body}"
            )

    except requests.exceptions.Timeout:
        logger.error("LLM API request timed out after 90 seconds")
        frappe.throw(
            f"{provider_name} API request timed out. "
            "Click 'Parse Resume' to retry."
        )

    except requests.exceptions.ConnectionError as e:
        logger.error(f"LLM API connection failed: {e}")
        frappe.throw(
            f"Could not connect to {provider_name} API. "
            f"Connection error: {str(e)[:200]}"
        )

    except Exception as e:
        logger.error(f"Unexpected error calling LLM API: {type(e).__name__}: {e}")
        frappe.throw(
            f"Unexpected error: {type(e).__name__}: {str(e)[:200]}. "
            "Check Error Log for details."
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

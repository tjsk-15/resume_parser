"""
Public API endpoints for Resume Parser.

Includes a debug endpoint to test LLM connectivity.
"""

import frappe
import requests
import json


@frappe.whitelist()
def test_llm_connection():
    """
    Test the LLM API connection. Call from browser console:
        frappe.call('resume_parser.api.test_llm_connection')
    Or visit: /api/method/resume_parser.api.test_llm_connection
    """
    frappe.only_for("System Manager")

    from resume_parser.services.llm_summarizer import PROVIDERS

    try:
        settings_doc = frappe.get_single("Resume Parser Settings")
        provider_name = settings_doc.llm_provider
        api_key = settings_doc.get_password("api_key")
        custom_model = settings_doc.model_name
    except Exception as e:
        return {"status": "error", "message": f"Cannot load settings: {e}"}

    if not api_key:
        return {"status": "error", "message": "No API key configured"}

    provider = PROVIDERS.get(provider_name)
    if not provider:
        return {"status": "error", "message": f"Unknown provider: {provider_name}"}

    model = custom_model or provider["default_model"]
    url = provider["url"].format(model=model)

    debug_info = {
        "provider": provider_name,
        "model": model,
        "url": url,
        "api_key_length": len(api_key),
        "api_key_prefix": api_key[:8] + "..." if len(api_key) > 8 else "***",
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    if provider_name == "OpenRouter":
        headers["HTTP-Referer"] = frappe.utils.get_url()
        headers["X-Title"] = "Frappe Resume Parser"

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say hello in exactly 5 words."}
        ],
        "temperature": 0.1,
        "max_tokens": 50,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        debug_info["status_code"] = response.status_code
        debug_info["response_headers"] = dict(response.headers)

        if response.status_code == 200:
            result = response.json()
            reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            debug_info["status"] = "success"
            debug_info["llm_reply"] = reply
            debug_info["message"] = "LLM connection is working!"
        else:
            debug_info["status"] = "error"
            debug_info["error_body"] = response.text[:500]
            debug_info["message"] = f"API returned status {response.status_code}"

    except requests.exceptions.Timeout:
        debug_info["status"] = "error"
        debug_info["message"] = "Request timed out after 30 seconds"

    except requests.exceptions.ConnectionError as e:
        debug_info["status"] = "error"
        debug_info["message"] = f"Connection failed: {str(e)[:300]}"

    except Exception as e:
        debug_info["status"] = "error"
        debug_info["message"] = f"{type(e).__name__}: {str(e)[:300]}"

    return debug_info

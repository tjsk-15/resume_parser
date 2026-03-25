"""
Public API endpoints for Resume Parser.

Includes debug endpoints to test LLM connectivity.
"""

import frappe


@frappe.whitelist()
def test_llm_connection():
    """
    Test the LLM API connection at multiple levels.

    Call from browser console:
        frappe.call({method: 'resume_parser.api.test_llm_connection', callback: r => console.log(JSON.stringify(r.message, null, 2))})

    Or visit: /api/method/resume_parser.api.test_llm_connection
    """
    frappe.only_for("System Manager")

    from resume_parser.services.llm_summarizer import PROVIDERS

    results = {"tests": []}

    # --- Test 1: Can we load settings? ---
    try:
        settings_doc = frappe.get_single("Resume Parser Settings")
        provider_name = settings_doc.llm_provider
        api_key = settings_doc.get_password("api_key")
        custom_model = settings_doc.model_name

        results["settings"] = {
            "provider": provider_name,
            "api_key_length": len(api_key) if api_key else 0,
            "api_key_prefix": (api_key[:8] + "...") if api_key and len(api_key) > 8 else "too_short",
            "custom_model": custom_model or "(using default)",
        }
        results["tests"].append({"test": "load_settings", "status": "pass"})
    except Exception as e:
        results["tests"].append({"test": "load_settings", "status": "fail", "error": str(e)})
        return results

    if not api_key:
        results["tests"].append({"test": "api_key_check", "status": "fail", "error": "No API key"})
        return results

    provider = PROVIDERS.get(provider_name, {})
    model = custom_model or provider.get("default_model", "unknown")
    url = provider.get("url", "unknown").format(model=model)

    results["target"] = {"url": url, "model": model}

    # --- Test 2: Can we import requests? ---
    try:
        import requests
        results["tests"].append({"test": "import_requests", "status": "pass", "version": requests.__version__})
    except ImportError as e:
        results["tests"].append({"test": "import_requests", "status": "fail", "error": str(e)})
        return results

    # --- Test 3: Can we reach the internet at all? ---
    try:
        r = requests.get("https://httpbin.org/get", timeout=10)
        results["tests"].append({
            "test": "internet_connectivity",
            "status": "pass",
            "httpbin_status": r.status_code,
        })
    except Exception as e:
        results["tests"].append({
            "test": "internet_connectivity",
            "status": "fail",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        })

    # --- Test 4: Can we reach the LLM provider's domain? ---
    try:
        r = requests.get(url.replace("/chat/completions", ""), timeout=10, allow_redirects=True)
        results["tests"].append({
            "test": "provider_reachable",
            "status": "pass",
            "status_code": r.status_code,
            "response_snippet": r.text[:200],
        })
    except Exception as e:
        results["tests"].append({
            "test": "provider_reachable",
            "status": "fail",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        })

    # --- Test 5: Actual LLM API call ---
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if provider_name == "OpenRouter":
        headers["HTTP-Referer"] = frappe.utils.get_url()
        headers["X-Title"] = "Frappe Resume Parser"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hello in exactly 5 words."}],
        "temperature": 0.1,
        "max_tokens": 50,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        test_result = {
            "test": "llm_api_call",
            "status_code": response.status_code,
            "response_body": response.text[:500],
        }

        if response.status_code == 200:
            result = response.json()
            reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            test_result["status"] = "pass"
            test_result["llm_reply"] = reply
            test_result["message"] = "LLM connection is working!"
        else:
            test_result["status"] = "fail"
            test_result["message"] = f"API returned {response.status_code}"

        results["tests"].append(test_result)

    except Exception as e:
        results["tests"].append({
            "test": "llm_api_call",
            "status": "fail",
            "error": f"{type(e).__name__}: {str(e)[:300]}",
        })

    return results

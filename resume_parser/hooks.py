app_name = "resume_parser"
app_title = "Resume Parser"
app_publisher = "Tej"
app_description = "AI-powered resume parsing and summarization for Job Applicants using free cloud LLMs"
app_email = "tjs.kutnikar@gmail.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext", "hrms"]

# ---------- Install / Uninstall ----------
after_install = "resume_parser.setup.after_install"
before_uninstall = "resume_parser.setup.before_uninstall"

# ---------- Custom Fields (injected into Job Applicant) ----------
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Resume Parser"]],
    }
]

# ---------- Doc Events ----------
doc_events = {
    "Job Applicant": {
        "after_insert": "resume_parser.services.resume_handler.on_applicant_save",
        "on_update": "resume_parser.services.resume_handler.on_applicant_save",
    }
}

# ---------- Client Scripts ----------
doctype_js = {
    "Job Applicant": "public/js/job_applicant.js"
}

# ---------- Scheduler (retry failed parses every 6 hours) ----------
scheduler_events = {
    "cron": {
        "0 */6 * * *": [
            "resume_parser.background_jobs.retry_failed.retry_failed_parses"
        ]
    }
}

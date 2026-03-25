"""
Scheduled job to retry failed resume parses.

Runs every 6 hours via scheduler_events in hooks.py.
"""

import frappe


def retry_failed_parses():
    """Find Job Applicants with failed parses and retry them."""
    failed_applicants = frappe.get_all(
        "Job Applicant",
        filters={"resume_parse_status": "Failed"},
        fields=["name"],
        limit=20,
    )

    if not failed_applicants:
        return

    frappe.logger("resume_parser").info(
        f"Retrying {len(failed_applicants)} failed resume parses"
    )

    for applicant in failed_applicants:
        try:
            doc = frappe.get_doc("Job Applicant", applicant.name)
            resume_url = _find_resume(doc)

            if not resume_url:
                continue

            frappe.enqueue(
                "resume_parser.services.resume_handler.parse_and_summarize",
                applicant_name=doc.name,
                resume_url=resume_url,
                queue="default",
                timeout=120,
                is_async=True,
            )
        except Exception as e:
            frappe.logger("resume_parser").error(
                f"Retry enqueue failed for {applicant.name}: {e}"
            )


def _find_resume(doc) -> str | None:
    """Find PDF resume URL from Job Applicant."""
    resume_url = doc.get("resume_attachment")
    if resume_url and resume_url.lower().endswith(".pdf"):
        return resume_url

    attachments = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Job Applicant",
            "attached_to_name": doc.name,
            "file_url": ["like", "%.pdf"],
        },
        fields=["file_url"],
        order_by="creation desc",
        limit=1,
    )

    return attachments[0].file_url if attachments else None

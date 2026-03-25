"""
Doc event handler for Job Applicant.

Triggered on after_insert and on_update to automatically parse attached resumes
and generate AI summaries.
"""

import frappe
from frappe import _
from frappe.exceptions import ValidationError


def on_applicant_save(doc, method):
    """
    Hook called after a Job Applicant is inserted or updated.

    Checks if a resume is attached and AI summary is missing,
    then enqueues background parsing.
    """
    # Skip if already summarized and resume hasn't changed
    if doc.get("resume_ai_summary") and not _resume_changed(doc):
        return

    # Find the resume attachment
    resume_url = _find_resume_attachment(doc)
    if not resume_url:
        return

    # Enqueue background job so we don't block the save
    frappe.enqueue(
        "resume_parser.services.resume_handler.parse_and_summarize",
        applicant_name=doc.name,
        resume_url=resume_url,
        queue="default",
        timeout=120,
        is_async=True,
        enqueue_after_commit=True,
    )

    frappe.msgprint(
        _("Resume parsing has been queued. The AI summary will appear shortly."),
        indicator="blue",
        alert=True,
    )


def parse_and_summarize(applicant_name: str, resume_url: str):
    """
    Background job: extract text from resume PDF and generate AI summary.

    Args:
        applicant_name: Name (ID) of the Job Applicant document
        resume_url: File URL of the resume attachment
    """
    from resume_parser.services.pdf_extractor import extract_text_from_pdf
    from resume_parser.services.llm_summarizer import summarize_resume

    logger = frappe.logger("resume_parser")

    try:
        logger.info(f"Parsing resume for {applicant_name}: {resume_url}")

        # Step 1: Extract text from PDF
        resume_text = extract_text_from_pdf(resume_url)

        if not resume_text or len(resume_text.strip()) < 20:
            _update_summary(
                applicant_name,
                "Could not extract meaningful text from the resume. "
                "The file may be image-based or corrupted.",
                status="Failed",
            )
            return

        logger.info(f"Extracted {len(resume_text)} chars from resume")

        # Step 2: Summarize with LLM
        summary = summarize_resume(resume_text)

        # Step 3: Save summary to Job Applicant
        _update_summary(applicant_name, summary, status="Completed")

        logger.info(f"Resume summary completed for {applicant_name}")

        # Notify the user via realtime
        frappe.publish_realtime(
            "resume_parsed",
            {
                "applicant_name": applicant_name,
                "status": "success",
                "message": f"Resume summary ready for {applicant_name}",
            },
            doctype="Job Applicant",
            docname=applicant_name,
            after_commit=True,
        )

    except ValidationError as e:
        # frappe.throw() raises ValidationError — pass through the message directly
        error_msg = str(e)
        logger.error(f"Resume parsing failed for {applicant_name}: {error_msg}")
        _update_summary(
            applicant_name,
            f"Parsing failed: {error_msg}. Click 'Parse Resume' to retry.",
            status="Failed",
        )

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Resume parsing failed for {applicant_name}: {error_msg}")
        _update_summary(
            applicant_name,
            f"Parsing failed: {error_msg}. Click 'Parse Resume' to retry.",
            status="Failed",
        )


def _update_summary(applicant_name: str, summary: str, status: str = "Completed"):
    """Update the AI summary fields on the Job Applicant document."""
    frappe.db.set_value(
        "Job Applicant",
        applicant_name,
        {
            "resume_ai_summary": summary,
            "resume_parse_status": status,
            "resume_parsed_on": frappe.utils.now(),
        },
        update_modified=False,
    )
    frappe.db.commit()


def _find_resume_attachment(doc) -> str | None:
    """
    Find a PDF resume attachment on the Job Applicant.

    Checks:
    1. The 'resume_attachment' field (standard HRMS field)
    2. Any attached PDF file
    """
    # Check the standard resume_attachment field first
    resume_url = doc.get("resume_attachment")
    if resume_url and resume_url.lower().endswith(".pdf"):
        return resume_url

    # Fall back to checking File doctype for attached PDFs
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

    if attachments:
        return attachments[0].file_url

    return None


def _resume_changed(doc) -> bool:
    """Check if the resume attachment has changed since last parse."""
    if not doc.get("resume_parsed_on"):
        return True

    current_resume = doc.get("resume_attachment", "")
    previous = frappe.db.get_value(
        "Job Applicant", doc.name, "resume_attachment"
    )

    return current_resume != previous


@frappe.whitelist()
def manual_parse_resume(applicant_name: str):
    """
    Whitelisted API for manually triggering resume parsing from the UI.

    Called from the 'Parse Resume' button on the Job Applicant form.
    """
    frappe.has_permission("Job Applicant", doc=applicant_name, ptype="write", throw=True)

    doc = frappe.get_doc("Job Applicant", applicant_name)
    resume_url = _find_resume_attachment(doc)

    if not resume_url:
        frappe.throw(_("No PDF resume found attached to this applicant."))

    # Clear previous summary and re-parse
    frappe.db.set_value(
        "Job Applicant",
        applicant_name,
        {"resume_ai_summary": "", "resume_parse_status": "Pending"},
        update_modified=False,
    )

    frappe.enqueue(
        "resume_parser.services.resume_handler.parse_and_summarize",
        applicant_name=applicant_name,
        resume_url=resume_url,
        queue="default",
        timeout=120,
        is_async=True,
    )

    return {"message": "Resume parsing has been queued."}

"""
Setup custom fields on install.

This is called by hooks.py after_install to create the custom fields
on Job Applicant for the AI resume summary.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
    "Job Applicant": [
        {
            "fieldname": "resume_parser_section",
            "label": "AI Resume Summary",
            "fieldtype": "Section Break",
            "insert_after": "notes",
            "collapsible": 0,
            "module": "Resume Parser",
        },
        {
            "fieldname": "resume_parse_status",
            "label": "Parse Status",
            "fieldtype": "Select",
            "options": "\nPending\nCompleted\nFailed",
            "insert_after": "resume_parser_section",
            "read_only": 1,
            "no_copy": 1,
            "module": "Resume Parser",
        },
        {
            "fieldname": "resume_parsed_on",
            "label": "Parsed On",
            "fieldtype": "Datetime",
            "insert_after": "resume_parse_status",
            "read_only": 1,
            "no_copy": 1,
            "module": "Resume Parser",
        },
        {
            "fieldname": "resume_parser_col_break",
            "fieldtype": "Column Break",
            "insert_after": "resume_parsed_on",
            "module": "Resume Parser",
        },
        {
            "fieldname": "resume_ai_summary",
            "label": "AI Summary",
            "fieldtype": "Markdown Editor",
            "insert_after": "resume_parser_col_break",
            "read_only": 1,
            "no_copy": 1,
            "module": "Resume Parser",
        },
    ]
}


def after_install():
    """Create custom fields after app installation."""
    create_custom_fields(CUSTOM_FIELDS, update=True)
    frappe.db.commit()


def before_uninstall():
    """Remove custom fields before app uninstallation."""
    for doctype, fields in CUSTOM_FIELDS.items():
        for field in fields:
            fieldname = field.get("fieldname")
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
                frappe.delete_doc("Custom Field", f"{doctype}-{fieldname}", force=True)
    frappe.db.commit()

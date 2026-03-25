"""Resume Parser Settings DocType controller."""

import frappe
from frappe.model.document import Document


class ResumeParserSettings(Document):
    def validate(self):
        if self.llm_provider and self.api_key:
            # Validate API key format (basic check)
            api_key = self.get_password("api_key")
            if not api_key or len(api_key) < 10:
                frappe.throw("API key appears to be invalid. Please check and re-enter.")

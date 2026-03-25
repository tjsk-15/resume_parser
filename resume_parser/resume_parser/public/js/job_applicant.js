// Client-side customization for Job Applicant form
// Adds a "Parse Resume" button and handles realtime updates

frappe.ui.form.on("Job Applicant", {
    refresh(frm) {
        // Add "Parse Resume" button if user has write permission
        if (frm.doc.name && frappe.model.can_write("Job Applicant")) {
            frm.add_custom_button(
                __("Parse Resume"),
                function () {
                    parse_resume(frm);
                },
                __("AI Tools")
            );
        }

        // Style the summary field based on parse status
        if (frm.doc.resume_parse_status === "Completed") {
            frm.fields_dict.resume_parse_status.$wrapper
                .find(".like-disabled-input")
                .css("color", "green");
        } else if (frm.doc.resume_parse_status === "Failed") {
            frm.fields_dict.resume_parse_status.$wrapper
                .find(".like-disabled-input")
                .css("color", "red");
        }

        // Listen for realtime resume parse completion
        frappe.realtime.on("resume_parsed", function (data) {
            if (data.applicant_name === frm.doc.name) {
                frappe.show_alert(
                    {
                        message: __("Resume summary is ready!"),
                        indicator: "green",
                    },
                    5
                );
                frm.reload_doc();
            }
        });
    },

    // Auto-trigger parsing when resume_attachment changes
    resume_attachment(frm) {
        if (frm.doc.resume_attachment && frm.doc.name) {
            frappe.show_alert(
                {
                    message: __(
                        "Resume attached. Save the form to trigger AI parsing."
                    ),
                    indicator: "blue",
                },
                5
            );
        }
    },
});

function parse_resume(frm) {
    frappe.confirm(
        __("Parse the attached resume and generate an AI summary?"),
        function () {
            frm.set_value("resume_parse_status", "Pending");
            frm.set_value("resume_ai_summary", "");

            frappe.call({
                method: "resume_parser.services.resume_handler.manual_parse_resume",
                args: { applicant_name: frm.doc.name },
                callback: function (r) {
                    if (r.message) {
                        frappe.show_alert(
                            {
                                message: __(r.message.message || "Parsing queued..."),
                                indicator: "blue",
                            },
                            5
                        );
                    }
                },
                error: function (r) {
                    frappe.msgprint({
                        title: __("Parse Error"),
                        message:
                            r.message ||
                            __("Failed to queue resume parsing. Check the console for details."),
                        indicator: "red",
                    });
                },
            });
        }
    );
}

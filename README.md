# Resume Parser for Frappe HRMS

AI-powered resume parsing and summarization for Job Applicants. Automatically extracts text from PDF resumes and generates structured summaries using free cloud-hosted LLMs (Groq, OpenRouter, or HuggingFace).

## Features

- **Automatic parsing** — Resumes are parsed when a Job Applicant is created (via Job Board or backend)
- **Manual trigger** — "Parse Resume" button on the Job Applicant form under AI Tools
- **Background processing** — Parsing runs asynchronously so saves are never blocked
- **Auto-retry** — Failed parses are retried every 6 hours
- **Multiple LLM providers** — Groq (recommended), OpenRouter, HuggingFace — all free tiers
- **Structured summaries** — Professional summary, skills, experience, education, certifications

## Requirements

- Frappe v16+
- ERPNext
- HRMS (Frappe HR)
- PyMuPDF (`pip install PyMuPDF`)
- A free API key from Groq, OpenRouter, or HuggingFace

## Installation

```bash
# Get the app
bench get-app https://github.com/YOUR_ORG/resume_parser.git
# OR copy the resume_parser folder to your bench/apps/ directory

# Install on your site
bench --site YOUR_SITE install-app resume_parser

# Install Python dependencies
bench pip install PyMuPDF

# Restart
bench restart
```

## Setup

1. Go to **Resume Parser Settings** (search bar or `/app/resume-parser-settings`)
2. Select your LLM provider (Groq recommended — 30 free requests/minute)
3. Enter your API key:
   - **Groq**: Sign up at [console.groq.com](https://console.groq.com) → API Keys → Create
   - **OpenRouter**: Sign up at [openrouter.ai](https://openrouter.ai) → Keys
   - **HuggingFace**: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
4. Save

## Usage

### Automatic (recommended)
Simply save a Job Applicant with a PDF resume attached. The AI summary will appear within a few seconds.

### Manual
Open any Job Applicant → Click **AI Tools** → **Parse Resume**

### Via Job Board
When applicants submit through the HRMS Job Board with a PDF resume, the summary is generated automatically after submission.

## App Structure

```
resume_parser/
├── hooks.py                    # App config, doc_events, scheduler
├── setup.py                    # Custom field creation on install
├── services/
│   ├── resume_handler.py       # Doc event handler + background jobs
│   ├── pdf_extractor.py        # PDF text extraction (PyMuPDF/pdfminer)
│   └── llm_summarizer.py       # LLM API integration (Groq/OpenRouter/HF)
├── background_jobs/
│   └── retry_failed.py         # Scheduled retry for failed parses
├── resume_module/
│   └── doctype/
│       └── resume_parser_settings/  # Settings Single DocType
├── public/js/
│   └── job_applicant.js        # Client-side "Parse Resume" button
└── translations/
```

## License

MIT

# Benchmark Suite: PHASE 1 - Document To Agenda Items

## 1. Overview
Evaluates the pre-meeting document ingestion pipeline:
* Document format parsing (DOCX, PDF, Markdown).
* Text structure & table extraction.
* Agenda item extraction (Topic, Estimated Minutes, Order).

## 2. Dataset Specification (20 Cases Target)
* `samples/S01` to `samples/S20`:
  * 7 PDF files: `01_sprint_planning.pdf`, `04_previous_meeting.pdf`, `08_housekeeping.pdf`, `09_approval_meeting.pdf`, `11_hop_ky_thuat.pdf`, `14_operations_handover.pdf`, `17_completed_migration.pdf`.
  * 7 DOCX files: `02_ke_hoach_nhom.docx`, `03_release_readiness.docx`, `06_repeated_requests.docx`, `10_technical_review.docx`, `13_bang_cong_viec.docx`, `15_onboarding.docx`, `18_similar_modules.docx`.
  * 5 Markdown files: `05_api_contract.md`, `07_iteration_planning.md`, `12_support_triage.md`, `16_security_planning.md`, `20_utf8_bom.md`.
  * 1 Plain text file: `19_plain_text.txt`.

## 3. Evaluation Strategy & Metrics (Document Ingestion & Integrity)
* **Format Conversion Success Rate (%)**: Parsing completion across PDF, DOCX, Markdown, and TXT without crashing.
* **UTF-8 Character Integrity & Diacritics**: Valid Unicode decoding, preserving Vietnamese diacritics and special characters without corruption.
* **Content Extraction Completeness**: Verification that extracted text is non-empty, with structural retention (headings, tables, lists).
* **Ingestion Latency (ms)**: Processing time per document.
*(Note: Direction A focuses on document parsing & ingestion integrity; no ground truth agenda JSON is required).*


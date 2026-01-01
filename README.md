# PDF MoM Writer

Small utility to write Meeting Minutes (MoMs) into an existing PDF template while preserving the header/footer. It wraps and paginates content, keeps important sections together when possible, and produces a multi-page PDF when needed.

## Quick start

1. Create and activate a virtual environment (we used `pdf`):
   - python -m venv pdf
   - PowerShell: .\pdf\Scripts\Activate.ps1
   - or cmd: pdf\Scripts\activate.bat

2. Install dependencies:
   - pip install -r pdf_mom_writer\requirements.txt

3. Prepare files in the project root:
   - `Template.pdf` — your template (keeps header/footer)
   - `pdf_mom_writer/content.txt` — the MoM you will write

4. Generate PDF (defaults):
   - python fill.py
   This writes `output.pdf` in the project root.

Or override defaults:
- python fill.py --input path/to/file.txt --template "My Template.pdf" --output result.pdf

## Input format (simple Markdown-ish)
- H1: `# Title` (rendered as 16pt Times Bold, centered)
- H2: `## Section` (rendered as 14pt Times Bold)
- Bulleted lists: `- item` or `* item`
- Numbered lists: `1. item`
- Inline formatting: `**bold**`, `*italic*`
- Multiple spaces are preserved (use two or more spaces)

Example:

```
# Meeting Title

Date: 2026-01-01

## Attendees:
1. Alice
2. Bob

## Action Items
- Alice: Do X
- Bob: Do Y
```

## Behavior & Notes
- The script uses the first page of your template PDF as the page background for every generated page.
- Content is wrapped and paginated automatically into the template's white area.
- Common sections (Attendees, Action Items, Discussion, Signature) are grouped and kept together when possible. If a section is larger than a single page it will be split across pages automatically (to avoid hangs).
- If text overlaps header/footer, fine-tune margins using flags: `--top`, `--bottom`, `--left`, `--right` (values are in points).

## Command-line options
- `--template` (path to your template PDF; if omitted the default template file in the project root will be used)
- `--input` (default: `pdf_mom_writer/content.txt`)
- `--output` (default: `output.pdf`)
- `--left`, `--right`, `--top`, `--bottom` (margins in points)
- `--font-size` (body text, default 12)
- `--h1-size` (default 16)
- `--h2-size` (default 14)
- `--debug` prints internal debug information (flowables, overlays)

## Troubleshooting
- If the script hangs: try `--debug` to see flowable/overlay info, or reduce/unwrap very large sections in your `content.txt`.
- If lists or headings don’t align as expected, adjust left/right margins or list indent leftPadding in the code.

## Files ignored by Git
See `.gitignore` — by default we ignore `pdf_mom_writer/content.txt`, the template PDF, `output.pdf`, and virtual envs (`pdf/`, `venv/`).

## Development notes
- Fonts: Times-Roman for body, Times-Bold for headings.
- The main script is `fill.py` (run from project root). The project also contains helper scripts in `scripts/` (e.g., `inspect_pdf.py`).

---

If you'd like, I can add page numbers, a header/footer overlay (for page numbers or small notes), or export to timestamped output files automatically. Which improvement do you want next?
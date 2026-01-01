import argparse
from io import BytesIO
from pathlib import Path
import re
import copy as _copy

from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Frame, Paragraph, ListFlowable, ListItem, Spacer, KeepTogether, PageBreak
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader, PdfWriter


def _inline_format(s: str) -> str:
    def _preserve_spaces(m):
        n = len(m.group(0))
        return '&nbsp;' * (n - 1) + ' '

    s = re.sub(r' {2,}', _preserve_spaces, s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'\*(.+?)\*', r'<i>\1</i>', s)
    return s


def build_flowables(text: str, body_style: ParagraphStyle, h1_style: ParagraphStyle, h2_style: ParagraphStyle):
    flowables = []
    lines = text.splitlines()

    current_list = None
    current_list_type = None

    current_section = None

    def flush_list(to_container):
        nonlocal current_list, current_list_type
        if not current_list:
            return
        items = [ListItem(item, leftIndent=0) for item in current_list]
        if current_list_type == 'bullet':
            lf = ListFlowable(items, bulletType='bullet', leftPadding=12, bulletFontName='Times-Roman', bulletFontSize=body_style.fontSize)
        else:
            lf = ListFlowable(items, bulletType='1', bulletFormat='%s.', leftPadding=12, bulletFontName='Times-Roman', bulletFontSize=body_style.fontSize)
        to_container.append(lf)
        current_list = None
        current_list_type = None

    def flush_section():
        nonlocal current_section
        if not current_section:
            return
        if len(current_section) > 1:
            flowables.append(("SECTION", list(current_section)))
        else:
            flowables.extend(current_section)
        current_section = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip('\n')
        nxt = lines[i+1] if i+1 < len(lines) else ''

        if not line.strip():
            if current_list:
                if current_section is not None:
                    flush_list(current_section)
                else:
                    flush_list(flowables)
            if current_section is not None:
                current_section.append(Spacer(1, 6))
            else:
                flowables.append(Spacer(1, 6))
            i += 1
            continue

        if line.startswith('# '):
            if current_list:
                flush_list(current_section if current_section is not None else flowables)
            flush_section()
            flowables.append(Paragraph(_inline_format(line[2:].strip()), h1_style))
            i += 1
            continue

        if line.startswith('## '):
            if current_list:
                flush_list(current_section if current_section is not None else flowables)
            flush_section()
            current_section = [Paragraph(_inline_format(line[3:].strip()), h2_style)]
            i += 1
            continue

        # detect colon-labeled sections
        m_bullet_next = re.match(r'^[\-\*]\s+.*', nxt.strip())
        m_number_next = re.match(r'^\d+\.\s+.*', nxt.strip())
        if line.strip().endswith(':') and (m_bullet_next or m_number_next):
            if current_list:
                flush_list(current_section if current_section is not None else flowables)
            flush_section()
            current_section = [Paragraph(_inline_format(line.strip()), body_style)]
            i += 1
            continue

        m_bullet = re.match(r'^[\-\*]\s+(.*)', line)
        m_number = re.match(r'^(\d+)\.\s+(.*)', line)
        if m_bullet:
            if current_list_type != 'bullet':
                if current_list:
                    flush_list(current_section if current_section is not None else flowables)
                current_list_type = 'bullet'
                current_list = []
            current_list.append(Paragraph(_inline_format(m_bullet.group(1).strip()), body_style))
            i += 1
            continue
        if m_number:
            if current_list_type != 'number':
                if current_list:
                    flush_list(current_section if current_section is not None else flowables)
                current_list_type = 'number'
                current_list = []
            current_list.append(Paragraph(_inline_format(m_number.group(2).strip()), body_style))
            i += 1
            continue

        # normal paragraph
        if current_list:
            flush_list(current_section if current_section is not None else flowables)
        p_html = _inline_format(line)
        if current_section is not None:
            current_section.append(Paragraph(p_html.strip(), body_style))
        else:
            flowables.append(Paragraph(p_html.strip(), body_style))
        i += 1

    if current_list:
        flush_list(current_section if current_section is not None else flowables)
    flush_section()
    return flowables


def estimate_height(flow_items, width, max_height=None):
    total = 0
    for f in flow_items:
        try:
            w, h = f.wrap(width, max_height if max_height is not None else 1e6)
        except Exception:
            return float("inf")
        total += h
        if max_height is not None and total > max_height:
            return total
    return total


def make_overlay_pages(page_width, page_height, left, bottom, content_width, content_height, flowables):
    overlays = []
    work = flowables[:]

    # Helper to estimate height for a collection of flowables
    def estimate_height(flow_items, width, max_h=None):
        total = 0
        for f in flow_items:
            try:
                w, h = f.wrap(width, max_h if max_h is not None else 1e6)
            except Exception:
                return float('inf')
            total += h
            if max_h is not None and total > max_h:
                return total
        return total

    while work:
        if len(work) > 1:
            new_work = []
            start = 0
            if isinstance(work[0], tuple) and work[0][0] == 'SECTION':
                new_work.append(work[0])
                start = 1
            for item in work[start:]:
                if isinstance(item, tuple) and item[0] == 'SECTION':
                    new_work.extend(item[1])
                else:
                    new_work.append(item)
            work = new_work

        buf = BytesIO()
        canv = Canvas(buf, pagesize=(page_width, page_height))
        frame = Frame(left, bottom, content_width, content_height, leftPadding=6, rightPadding=6, showBoundary=0)

        # If the next item is a SECTION marker, try to keep it together on this new page if it will fit
        if work and isinstance(work[0], tuple) and work[0][0] == 'SECTION':
            _, items = work[0]
            est = estimate_height(items, content_width, content_height)
            if est <= content_height:
                # The whole section fits on one page, so add it first
                frame.addFromList(items[:], canv)
                # remove the section marker
                work.pop(0)
                # Let the frame fill the rest of the page from remaining work
                frame.addFromList(work, canv)
            else:
                # Section is larger than a page — unwrap it so it can be split naturally
                work = items + work[1:]
                frame.addFromList(work, canv)
        else:
            # Normal case: let reportlab consume as many flowables as fit on the page
            frame.addFromList(work, canv)

        canv.save()
        buf.seek(0)
        overlays.append(buf)
    return overlays


def main():
    ap = argparse.ArgumentParser(description="Overlay text into a PDF template and paginate.")
    ap.add_argument("--template", default="CSI Template.pdf", help="Path to template PDF (single page used as background). Defaults to 'CSI Template.pdf' in current folder.")
    ap.add_argument("--input", default="content.txt", help="Path to text file containing MoMs. Defaults to 'pdf_mom_writer/content.txt'.")
    ap.add_argument("--output", default="output.pdf", help="Path to write resulting PDF (default 'output.pdf')")
    ap.add_argument("--left", type=float, default=50.0, help="Left margin (pt)")
    ap.add_argument("--right", type=float, default=50.0, help="Right margin (pt)")
    ap.add_argument("--top", type=float, default=120.0, help="Top margin (pt)")
    ap.add_argument("--bottom", type=float, default=100.0, help="Bottom margin (pt)")
    ap.add_argument("--font-size", type=float, default=12.0, help="Body font size (pt) - default 12")
    ap.add_argument("--h1-size", type=float, default=16.0, help="H1 font size (pt) - default 16")
    ap.add_argument("--h2-size", type=float, default=14.0, help="H2 font size (pt) - default 14")
    ap.add_argument("--debug", action="store_true", help="Enable debug logging to stdout")

    args = ap.parse_args()

    # Resolve template path: accept the provided path, else try common candidates in repo root and pdf_mom_writer/
    candidate_templates = [
        args.template,
        'Template.pdf',
        'template.pdf',
        'CSI Template.pdf',
        'pdf_mom_writer/Template.pdf',
        'pdf_mom_writer/CSI Template.pdf',
    ]
    template_path = None
    for cand in candidate_templates:
        p = Path(cand)
        if not p.is_absolute():
            p = Path.cwd() / p
        if p.exists():
            template_path = p
            break
    if template_path is None:
        raise SystemExit(f"Template PDF not found. Tried: {', '.join(candidate_templates)}")

    tpl_reader = PdfReader(str(template_path))
    if not tpl_reader.pages:
        raise SystemExit("Template PDF has no pages")
    template_page = tpl_reader.pages[0]
    media = template_page.mediabox
    page_w = float(media.width)
    page_h = float(media.height)

    left = args.left
    right = args.right
    top = args.top
    bottom = args.bottom
    content_w = page_w - left - right
    content_h = page_h - top - bottom
    if content_w <= 0 or content_h <= 0:
        raise SystemExit("Invalid margins: content area is not positive. Adjust top/bottom/left/right values.")

    # Resolve input path: try provided path, then try common candidates
    candidate_inputs = [
        args.input,
        'pdf_mom_writer/content.txt',
        'pdf_mom_writer/content.md',
        'content.txt',
        'content.md',
    ]
    input_path = None
    for cand in candidate_inputs:
        p = Path(cand)
        if not p.is_absolute():
            p = Path.cwd() / p
        if p.exists():
            input_path = p
            break
    if input_path is None:
        raise SystemExit(f"Input content not found. Tried: {', '.join(candidate_inputs)}")

    with open(input_path, "r", encoding="utf-8") as f:
        txt = f.read()

    styles = getSampleStyleSheet()
    body_size = args.font_size
    h1_size = args.h1_size
    h2_size = args.h2_size

    body = ParagraphStyle(
        "MoMBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=body_size,
        leading=body_size * 1.25,
    )
    h1 = ParagraphStyle(
        "MoMH1",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=h1_size,
        leading=h1_size + 4,
        alignment=1,  # centered headings
    )
    h2 = ParagraphStyle(
        "MoMH2",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=h2_size,
        leading=h2_size + 2,
        spaceBefore=6,
        spaceAfter=6,
    )

    flowables = build_flowables(txt, body, h1, h2)

    if args.debug:
        print(f"DEBUG: generated {len(flowables)} flowables")
        for i, f in enumerate(flowables[:10], 1):
            print(f"  {i}: {type(f).__name__}")

    overlays = make_overlay_pages(page_w, page_h, left, bottom, content_w, content_h, flowables)

    if args.debug:
        print(f"DEBUG: created {len(overlays)} overlay page(s)")
        # extract overlay text samples
        for i, buf in enumerate(overlays, 1):
            overlay_reader = PdfReader(buf)
            ot = overlay_reader.pages[0].extract_text() or ""
            print(f"  overlay {i} text (first140): {ot.strip()[:140]!r}")

    writer = PdfWriter()

    # Merge overlay and template
    for buf in overlays:
        overlay_reader = PdfReader(buf)
        overlay_page = overlay_reader.pages[0]
        # copy overlay and merge the template beneath it
        page = _copy.deepcopy(overlay_page)
        page.merge_page(_copy.deepcopy(template_page))
        writer.add_page(page)

    with open(args.output, "wb") as out_f:
        writer.write(out_f)

    print(f"Wrote {len(overlays)} page(s) to {args.output}")


if __name__ == "__main__":
    main()

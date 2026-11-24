#!/usr/bin/env python3
"""Render the report's Markdown source with embedded tables, links and figures."""
import argparse
from html import escape
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Preformatted

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://github.com/a-little-hoof/580-final'
WIDTH = letter[0] - 90
INK = colors.HexColor('#172434')
BLUE = colors.HexColor('#24567A')


def clean(s):
    return s.translate(str.maketrans({'—': '-', '–': '-', '‑': '-', '×': 'x', '→': '->', '−': '-', '“': '"', '”': '"', '’': "'"}))


def target(url, source):
    if url.startswith(('https://', 'http://', '#', 'mailto:')):
        return url
    path = (source.parent / url).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Report link escapes project: ' + url)
    return REPO + '/blob/main/' + quote(path.relative_to(ROOT).as_posix())


def inline(children, source):
    out = []
    for t in children or []:
        if t.type == 'text': out.append(escape(clean(t.content)))
        elif t.type in ('softbreak', 'hardbreak'): out.append(' ' if t.type == 'softbreak' else '<br/>')
        elif t.type == 'code_inline': out.append('<font name="Courier" size="8">' + escape(clean(t.content)) + '</font>')
        elif t.type == 'strong_open': out.append('<b>')
        elif t.type == 'strong_close': out.append('</b>')
        elif t.type == 'em_open': out.append('<i>')
        elif t.type == 'em_close': out.append('</i>')
        elif t.type == 'link_open': out.append('<a color="#24567A" href="' + escape(target(t.attrGet('href'), source), quote=True) + '">')
        elif t.type == 'link_close': out.append('</a>')
        elif t.type == 'html_inline': out.append(escape(t.content))
        elif t.type != 'image': raise ValueError('Unsupported inline Markdown: ' + t.type)
    return ''.join(out)


def styles():
    body = ParagraphStyle('body', fontName='Helvetica', fontSize=9.5, leading=13.2, textColor=INK,
                          spaceAfter=7, splitLongWords=True, allowWidows=0, allowOrphans=0)
    return {
        'body': body,
        'quote': ParagraphStyle('quote', parent=body, fontSize=8.4, leading=11.4, leftIndent=12,
                                borderColor=colors.HexColor('#B5C9D8'), borderWidth=0.7, borderPadding=7, spaceAfter=9),
        'title': ParagraphStyle('title', parent=body, fontName='Helvetica-Bold', fontSize=23, leading=28,
                                spaceAfter=12, textColor=BLUE, keepWithNext=True),
        'h2': ParagraphStyle('h2', parent=body, fontName='Helvetica-Bold', fontSize=13, leading=17,
                             spaceBefore=13, spaceAfter=7, textColor=BLUE, keepWithNext=True),
        'h3': ParagraphStyle('h3', parent=body, fontName='Helvetica-Bold', fontSize=10.5, leading=14,
                             spaceBefore=9, keepWithNext=True),
        'cell': ParagraphStyle('cell', parent=body, fontSize=7.5, leading=10, spaceAfter=0),
        'head': ParagraphStyle('head', parent=body, fontName='Helvetica-Bold', fontSize=7.5, leading=10,
                               textColor=colors.white, spaceAfter=0),
        'code': ParagraphStyle('code', parent=body, fontName='Courier', fontSize=7.1, leading=9.1,
                               leftIndent=8, backColor=colors.HexColor('#F0F4F7')),
    }


def render(source, destination):
    st = styles()
    tokens = MarkdownIt('commonmark').enable('table').parse(source.read_text())
    story, i, quoted, item = [], 0, False, False
    while i < len(tokens):
        t = tokens[i]
        if t.type == 'heading_open':
            value = tokens[i + 1]
            style = st['title' if t.tag == 'h1' else 'h2' if t.tag == 'h2' else 'h3']
            story.append(Paragraph(inline(value.children, source), style)); i += 3; continue
        if t.type == 'paragraph_open':
            value = tokens[i + 1]
            images = [c for c in value.children or [] if c.type == 'image']
            if images:
                if len(value.children) != 1: raise ValueError('Place report figures in their own paragraphs')
                path = (source.parent / images[0].attrGet('src')).resolve()
                if not path.is_relative_to(ROOT): raise ValueError('Figure escapes project')
                im = Image(str(path)); ratio = min(WIDTH / im.imageWidth, 390 / im.imageHeight)
                im.drawWidth, im.drawHeight = im.imageWidth * ratio, im.imageHeight * ratio
                story.extend([Spacer(1, 5), im, Spacer(1, 8)])
            else:
                story.append(Paragraph(inline(value.children, source), st['quote' if quoted else 'body'],
                                       bulletText='\u2022' if item else None))
            i += 3; continue
        if t.type == 'table_open':
            rows, row, header = [], [], True
            i += 1
            while tokens[i].type != 'table_close':
                q = tokens[i]
                if q.type == 'tr_open': row = []
                elif q.type == 'inline': row.append(Paragraph(inline(q.children, source), st['head' if header else 'cell']))
                elif q.type == 'tr_close': rows.append(row)
                elif q.type == 'thead_close': header = False
                i += 1
            n = len(rows[0])
            if any(len(row) != n for row in rows): raise ValueError('Ragged report table')
            weights = {2: [0.16, 0.84], 3: [0.24, 0.29, 0.47],
                       7: [0.23, 0.14, 0.13, 0.13, 0.12, 0.12, 0.13],
                       8: [0.22, 0.12, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11]}.get(n, [1/n]*n)
            table = Table(rows, colWidths=[WIDTH*w for w in weights], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),BLUE), ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F0F4F7')]),
                ('LINEBELOW',(0,0),(-1,0),0.7,BLUE), ('LINEBELOW',(0,-1),(-1,-1),0.5,colors.HexColor('#BCCCD7')),
                ('LEFTPADDING',(0,0),(-1,-1),6), ('RIGHTPADDING',(0,0),(-1,-1),6),
                ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
            ]))
            if n == 7 and rows[0][0].getPlainText() == 'Task / mode':
                table.setStyle(TableStyle([
                    ('NOSPLIT', (0, row), (-1, row + 1))
                    for row in range(1, len(rows) - 1, 2)
                ]))
            story.extend([Spacer(1,3), table, Spacer(1,10)])
        elif t.type == 'blockquote_open': quoted = True
        elif t.type == 'blockquote_close': quoted = False
        elif t.type == 'list_item_open': item = True
        elif t.type == 'list_item_close': item = False
        elif t.type in ('fence','code_block'): story.append(Preformatted(clean(t.content),st['code'],maxLineLength=100))
        elif t.type == 'hr': story.append(Spacer(1,8))
        elif t.type not in ('bullet_list_open','bullet_list_close','ordered_list_open','ordered_list_close'):
            raise ValueError('Unsupported block Markdown: ' + t.type)
        i += 1

    def footer(canvas, doc):
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor('#CCD8E0')); canvas.setLineWidth(0.4)
        canvas.line(45,38,letter[0]-45,38); canvas.setFont('Helvetica',8); canvas.setFillColor(BLUE)
        canvas.drawString(45,25,'COMP 580 | Yifei Wang | yw251')
        canvas.drawRightString(letter[0]-45,25,str(doc.page)); canvas.restoreState()
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(destination), pagesize=letter, leftMargin=45, rightMargin=45,
                            topMargin=43, bottomMargin=49, title='Less Formatting, Same Information',
                            author='Yifei Wang (yw251)', subject='COMP 580 final project')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'report/report.md')
    p.add_argument('--out',type=Path,default=ROOT/'output/pdf/comp580-yw251-report.pdf')
    a=p.parse_args();render(a.source.resolve(),a.out.resolve());print(a.out)

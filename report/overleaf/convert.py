#!/usr/bin/env python3
"""Convert this project's Markdown report into an editable Overleaf document.

Only writes beside this script. No model, browser, or network calls.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = ROOT / "report/report.md"
REPOSITORY = "https://github.com/a-little-hoof/580-final"


def escape(text):
    substitutions = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
        "|": r"\textbar{}", "±": r"\textpm{}", "–": "--", "—": "---",
        "’": "'", "‘": "`", "“": "``", "”": "''",
    }
    return "".join(substitutions.get(char, char) for char in text)


def link_target(target):
    if target.startswith(("https://", "http://")):
        return target
    path = (SOURCE.parent / target).resolve()
    relative = path.relative_to(ROOT).as_posix()
    kind = "tree" if path.is_dir() else "blob"
    return f"{REPOSITORY}/{kind}/main/{quote(relative)}"


INLINE = re.compile(r"(`[^`]+`|\*\*.+?\*\*|\[[^\]]+\]\([^)]+\)|<https?://[^>]+>)")


def inline(text):
    out = []
    end = 0
    for match in INLINE.finditer(text):
        out.append(escape(text[end:match.start()]))
        part = match.group()
        if part.startswith("`"):
            out.append(r"\texttt{" + escape(part[1:-1]) + "}")
        elif part.startswith("**"):
            out.append(r"\textbf{" + inline(part[2:-2]) + "}")
        elif part.startswith("["):
            label, target = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part).groups()
            out.append(r"\href{" + escape(link_target(target)) + "}{" + inline(label) + "}")
        else:
            out.append(r"\url{" + part[1:-1] + "}")
        end = match.end()
    out.append(escape(text[end:]))
    return "".join(out)


def table(lines):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    header, alignment, *body = rows
    count = len(header)
    if any(len(row) != count for row in rows):
        raise ValueError("Unequal table rows")
    if count == 2:
        columns = (r"@{}>{\raggedright\arraybackslash}p{.10\linewidth}"
                   r">{\raggedright\arraybackslash}p{\dimexpr.90\linewidth-2\tabcolsep\relax}@{}")
    elif count == 3:
        columns = (r"@{}>{\raggedright\arraybackslash}p{.10\linewidth}"
                   r">{\raggedright\arraybackslash}p{.23\linewidth}"
                   r">{\raggedright\arraybackslash}p{\dimexpr.67\linewidth-4\tabcolsep\relax}@{}")
    else:
        columns = "@{}" + "".join("r" if cell.endswith(":") else "l" for cell in alignment) + "@{}"
    head = " & ".join(r"\textbf{" + inline(cell) + "}" for cell in header) + r" \\"
    out = [r"\begingroup", r"\small", r"\setlength{\tabcolsep}{4pt}",
           r"\renewcommand{\arraystretch}{1.15}", r"\begin{longtable}{" + columns + "}",
           r"\toprule", head, r"\midrule", r"\endfirsthead",
           r"\toprule", head, r"\midrule", r"\endhead", r"\bottomrule", r"\endfoot"]
    out += [" & ".join(inline(cell) for cell in row) + r" \\" for row in body]
    out += [r"\end{longtable}", r"\endgroup"]
    return "\n".join(out)


PREAMBLE = r"""% Editable report converted from report/report.md. Do not replace with a PDF wrapper.
\documentclass[10pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=0.72in]{geometry}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{array,booktabs,longtable}
\usepackage{xurl}
\usepackage{needspace}
\usepackage[hidelinks]{hyperref}
\hypersetup{pdftitle={Less Formatting, Same Information},pdfauthor={Yifei Wang}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.4em}
\setlength{\emergencystretch}{2em}
\setlength{\LTleft}{0pt}
\setlength{\LTright}{0pt}
\setlength{\LTpre}{0.4em}
\setlength{\LTpost}{0.6em}
\urlstyle{same}
\begin{document}
"""


def convert(text):
    lines = text.splitlines()
    title = lines[0].removeprefix("# ")
    first_section = next(i for i, line in enumerate(lines) if line.startswith("## "))
    author = [line.strip() for line in lines[1:first_section] if line.strip()]
    out = [PREAMBLE, r"\begin{center}", r"{\LARGE\bfseries " + inline(title) + r"}\par\medskip",
           r" \\".join(inline(line) for line in author), r"\end{center}"]
    i = first_section
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("## "):
            title = line[3:]
            out += [r"\Needspace{4\baselineskip}", r"\section*{" + inline(title) + "}"]
            i += 1
        elif line.startswith("|"):
            start = i
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            out.append(table(lines[start:i]))
        elif line.startswith("!["):
            if not re.fullmatch(r"!\[[^\]]*\]\(figures/main-comparison\.png\)", line):
                raise ValueError("Unexpected image")
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            caption = lines[i].strip()
            if not caption.startswith("**Figure 1.**"):
                raise ValueError("Figure caption missing")
            out += [r"\begin{center}\begin{minipage}{\linewidth}",
                    r"\includegraphics[width=\linewidth]{main-comparison.pdf}",
                    r"\par\smallskip{\small " + inline(caption) + "}",
                    r"\end{minipage}\end{center}"]
            i += 1
        elif line.startswith("> "):
            out += [r"\begin{quote}\small", inline(line[2:]), r"\end{quote}"]
            i += 1
        else:
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("## ", "|", "> ", "![")):
                paragraph.append(lines[i].strip())
                i += 1
            out.append(inline(" ".join(paragraph)))
        out.append("")
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    text = SOURCE.read_text(encoding="utf-8")
    output = HERE / "main.tex"
    output.write_text(convert(text), encoding="utf-8")
    figure = HERE / "main-comparison.pdf"
    shutil.copyfile(ROOT / "report/figures/main-comparison.pdf", figure)
    sections = re.findall(r"^## (\d+)\. (.+)$", text, re.M)
    if [number for number, _ in sections] != [str(i) for i in range(10)]:
        raise ValueError("Expected sections 0 through 9")
    quotes = re.findall(r"^> (.+)$", text, re.M)
    metadata = {
        "source": "report/report.md", "source_sha256": digest(SOURCE),
        "main_tex_sha256": digest(output), "figure_sha256": digest(figure),
        "sections": [f"{number}. {title}" for number, title in sections],
        "prompt_quotes": [{"text": value, "sha256": hashlib.sha256(value.encode()).hexdigest()} for value in quotes],
        "conversion": "All report blocks retained; relative artifact links resolve to the GitHub main branch; vector PDF replaces the identical plot PNG.",
        "compile_target": "pdfLaTeX on Overleaf; local validation may use cached Tectonic",
    }
    (HERE / "conversion.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"main_tex": str(output), "source_sha256": metadata["source_sha256"],
                      "sections": len(sections), "prompt_quotes": len(quotes)}, indent=2))


if __name__ == "__main__":
    main()

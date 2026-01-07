#!/usr/bin/env python3
import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename

APP_ROOT = Path(__file__).resolve().parent
ASSETS = [
    "ieee/ieee-conference.tex",
    "ieee/IEEEtran.cls",
    "ieee/IEEEtran.bst",
    "ieee/ieee.csl",
    "ieee/pandoc-csl-fix.tex",
]

ALLOWED_MD = {"md"}
ALLOWED_BIB = {"bib"}
ALLOWED_ZIP = {"zip"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB


def _allowed(filename: str, exts: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def _copy_assets(dest: Path) -> None:
    for name in ASSETS:
        src = APP_ROOT / name
        if not src.exists():
            raise FileNotFoundError(f"Missing required asset: {name}")
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, target)


def _link_paper_assets(src_dir: Path, work_dir: Path) -> list[Path]:
    links: list[Path] = []
    if not src_dir.exists():
        return links
    for entry in src_dir.iterdir():
        if entry.suffix in (".md", ".bib"):
            continue
        target = work_dir / entry.name
        if target.exists():
            continue
        target.symlink_to(entry)
        links.append(target)
    return links


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _run_conversion(work: Path, paper_dir: Path) -> None:
    out_rel = Path("outputs")
    out_dir = work / out_rel
    out_dir.mkdir(parents=True, exist_ok=True)

    ieee_dir = work / "ieee"
    env = os.environ.copy()
    env["TEXINPUTS"] = f"{ieee_dir}:{env.get('TEXINPUTS', '')}:"
    env["BIBINPUTS"] = f"{paper_dir}:{out_dir}:{env.get('BIBINPUTS', '')}:"
    env["BSTINPUTS"] = f"{ieee_dir}:{paper_dir}:{out_dir}:{env.get('BSTINPUTS', '')}:"

    _run(
        [
            "pandoc",
            str(paper_dir / "paper.md"),
            "--template",
            str(Path("ieee") / "ieee-conference.tex"),
            "--natbib",
            "-s",
            "-o",
            str(out_rel / "paper.tex"),
        ],
        cwd=work,
        env=env,
    )

    tex_path = out_dir / "paper.tex"
    text = tex_path.read_text()
    tex_path.write_text(text.replace(r"\citep", r"\cite"))

    for ext in ("aux", "bbl", "blg", "out", "log", "pdf"):
        (out_dir / f"paper.{ext}").unlink(missing_ok=True)

    for bib in paper_dir.glob("*.bib"):
        shutil.copy(bib, out_dir / bib.name)

    _run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(out_rel),
            str(out_rel / "paper.tex"),
        ],
        cwd=work,
        env=env,
    )
    _run(["bibtex", str(out_rel / "paper")], cwd=work, env=env)
    _run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(out_rel),
            str(out_rel / "paper.tex"),
        ],
        cwd=work,
        env=env,
    )
    _run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(out_rel),
            str(out_rel / "paper.tex"),
        ],
        cwd=work,
        env=env,
    )


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            member_path = (dest / member.filename).resolve()
            try:
                member_path.relative_to(dest_resolved)
            except ValueError:
                raise ValueError("Zip file contains an unsafe path.")
        zf.extractall(dest)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    md_file = request.files.get("md_file")
    bib_file = request.files.get("bib_file")
    fig_zip = request.files.get("fig_zip")

    if not md_file or not md_file.filename:
        return render_template("index.html", error="Missing .md file.")
    if not bib_file or not bib_file.filename:
        return render_template("index.html", error="Missing .bib file.")
    if not fig_zip or not fig_zip.filename:
        return render_template("index.html", error="Missing figures .zip file.")

    if not _allowed(md_file.filename, ALLOWED_MD):
        return render_template("index.html", error="Markdown file must be .md.")
    if not _allowed(bib_file.filename, ALLOWED_BIB):
        return render_template("index.html", error="Bibliography file must be .bib.")
    if not _allowed(fig_zip.filename, ALLOWED_ZIP):
        return render_template("index.html", error="Figures upload must be a .zip.")

    with tempfile.TemporaryDirectory(prefix="ieee-convert-") as tmpdir:
        work = Path(tmpdir)
        paper_dir = work / "paperFiles"
        paper_dir.mkdir(parents=True, exist_ok=True)

        try:
            _copy_assets(work)

            md_path = paper_dir / "paper.md"
            md_file.save(md_path)

            bib_name = secure_filename(bib_file.filename) or "library.bib"
            bib_path = paper_dir / bib_name
            bib_file.save(bib_path)

            if bib_name != "library.bib":
                shutil.copy(bib_path, paper_dir / "library.bib")

            zip_path = work / "figures.zip"
            fig_zip.save(zip_path)
            _safe_extract_zip(zip_path, paper_dir)

            links = _link_paper_assets(paper_dir, work)
            try:
                _run_conversion(work, paper_dir)
            finally:
                for link in links:
                    link.unlink(missing_ok=True)

            pdf_path = work / "outputs" / "paper.pdf"
            if not pdf_path.exists():
                raise FileNotFoundError("PDF was not generated.")

            pdf_bytes = pdf_path.read_bytes()
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="paper.pdf",
            )
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            log = ""
            if isinstance(exc, subprocess.CalledProcessError):
                log = (exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")
            return render_template(
                "index.html",
                error=str(exc),
                log=log.strip(),
            )


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)

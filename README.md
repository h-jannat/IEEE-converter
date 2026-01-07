# IEEE Converter

Small helper project that converts `paper.md` into an IEEE-style PDF using Pandoc + LaTeX.

## Outputs
- `outputs/paper.tex` (intermediate)
- `outputs/paper.pdf` (final)

## Web App (Flask)
The web app runs conversions locally using Pandoc + LaTeX, so they must be
installed on the host (or run the app inside a container that has them).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 and upload:
- `paper.md`
- `library.bib`
- a `.zip` of figures (preserve the folder structure used in markdown, e.g. `result_plots/`).

### Web App via Docker
```bash
docker compose build
USER_ID=$(id -u) GROUP_ID=$(id -g) docker compose up web
```

## Tests
Integration tests use Flask's test client and run a full conversion. They will
skip automatically if `pandoc`, `pdflatex`, or `bibtex` are not installed.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Notes
- The app runs Pandoc, fixes `\citep` to `\cite`, and then runs `pdflatex` + `bibtex`.
- Generated files are written to `outputs/` inside the temporary job directory.
- Build artifacts (`*.aux`, `*.bbl`, `*.blg`, `*.log`, `*.out`, `*.pdf`) are ignored by `.dockerignore`.

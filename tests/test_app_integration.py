import io
import shutil
import sys
import zipfile
from pathlib import Path
import struct
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app


def _has_deps() -> bool:
    return all(shutil.which(cmd) for cmd in ("pandoc", "pdflatex", "bibtex"))


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _png_bytes() -> bytes:
    width = 1
    height = 1
    bit_depth = 8
    color_type = 6  # RGBA
    compression = 0
    filter_method = 0
    interlace = 0
    ihdr_data = struct.pack(
        "!IIBBBBB",
        width,
        height,
        bit_depth,
        color_type,
        compression,
        filter_method,
        interlace,
    )
    raw = b"\x00" + b"\xff\x00\x00\xff"
    idat_data = zlib.compress(raw)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack("!I", len(data))
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return length + chunk_type + data + struct.pack("!I", crc)

    signature = b"\x89PNG\r\n\x1a\n"
    return signature + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", idat_data) + chunk(b"IEND", b"")


@pytest.mark.skipif(not _has_deps(), reason="pandoc/latex not installed")
def test_upload_converts_to_pdf():
    client = app.test_client()

    md = b"""---\ntitle: \"Test Paper\"\nauthor: \"Test Author\"\nbibliography: library\n---\n\nCite [@Test2024].\n\n![Test](result_plots/test.png)\n"""
    bib = b"""@article{Test2024,\n  title={Test Entry},\n  author={Doe, Jane},\n  journal={Test Journal},\n  year={2024}\n}\n"""
    png_bytes = _png_bytes()
    zip_bytes = _zip_bytes({"result_plots/test.png": png_bytes})

    data = {
        "md_file": (io.BytesIO(md), "paper.md"),
        "bib_file": (io.BytesIO(bib), "library.bib"),
        "fig_zip": (io.BytesIO(zip_bytes), "figures.zip"),
    }
    resp = client.post("/", data=data, content_type="multipart/form-data")

    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_missing_files_show_error():
    client = app.test_client()

    resp = client.post("/", data={}, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert b"Missing .md file." in resp.data


def test_zip_path_traversal_rejected():
    client = app.test_client()

    md = b"title: Test\n\n![Test](result_plots/test.png)\n"
    bib = b"@article{Test2024, title={Test}, author={Doe}, year={2024}}\n"
    zip_bytes = _zip_bytes({"../evil.txt": b"nope"})

    data = {
        "md_file": (io.BytesIO(md), "paper.md"),
        "bib_file": (io.BytesIO(bib), "library.bib"),
        "fig_zip": (io.BytesIO(zip_bytes), "figures.zip"),
    }
    resp = client.post("/", data=data, content_type="multipart/form-data")

    assert resp.status_code == 200
    assert b"unsafe path" in resp.data

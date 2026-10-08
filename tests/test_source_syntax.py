from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def test_python_sources_parse():
    for path in ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

def test_frontend_has_single_generation_entrypoint():
    text=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    assert text.count("async function generateImage(){") == 1
    assert text.count("async function editImage(){") == 1

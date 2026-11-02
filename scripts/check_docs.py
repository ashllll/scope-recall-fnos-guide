"""Check local document links and parse source/configuration templates."""
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
for path in [*ROOT.glob("scripts/*.py"), *ROOT.glob("deploy/**/*.py"), *ROOT.glob("tests/*.py")]:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
for path in [*ROOT.glob("templates/*.json"), *ROOT.glob("diagrams/*.json")]:
    json.loads(path.read_text(encoding="utf-8"))
errors = []
for path in [*ROOT.glob("*.md"), *ROOT.glob("docs/*.md"), *ROOT.glob("templates/*.md")]:
    body = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
        if "://" in target or target.startswith("#"):
            continue
        local = target.split("#", 1)[0]
        if not (path.parent / local).exists():
            errors.append(f"{path.relative_to(ROOT)}: {target}")
if errors:
    raise SystemExit("Broken local links:\n" + "\n".join(errors))
print("Python/JSON syntax and local document links passed")

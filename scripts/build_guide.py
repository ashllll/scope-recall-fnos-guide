"""Build the complete guide from the current deployment chapters."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = ["01-storage.md", "02-docker.md", "03-clients.md", "04-network.md", "05-operations.md", "06-validation.md", "08-monitoring.md"]

def render():
    parts = ["# Scope Recall 飞牛部署全流程\n\n版本：1.1 · 核对日期：2026-11-02 · 参考上游：3.17.0\n\n配置与 Docker 在空间 3，记忆与文件在空间 1；Mac Codex/DSH 共享记忆；NAS OpenAI 只走 GLaDOS；常驻状态面板与 Bark 异常通知。\n\n[交互部署图](deployment.html) · [仓库首页](../README.md)\n"]
    expected = set()
    for name in CHAPTERS:
        body = (ROOT / "docs" / name).read_text(encoding="utf-8")
        body = re.sub(r"^\[\d+\]:.*\n?", "", body, flags=re.M).strip()
        expected.update(re.findall(r"\[(\d+)\]", body))
        body = re.sub(r"^(#{1,5}) ", r"#\1 ", body, flags=re.M)
        parts.append(body)
    parts.append((ROOT / "docs/references.md").read_text(encoding="utf-8").split("\n", 1)[1].strip())
    result = "\n\n".join(parts) + "\n"
    assert expected <= set(re.findall(r"\[(\d+)\]", result)), "citation lost during merge"
    return result

if __name__ == "__main__":
    path = ROOT / "docs/00-deployment-guide.md"
    content = render()
    if "--check" in sys.argv:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit("Guide is stale: run python3 scripts/build_guide.py")
    else:
        path.write_text(content, encoding="utf-8")

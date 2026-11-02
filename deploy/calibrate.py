"""Small synthetic Chinese embedding check; never logs credentials or vectors."""
import json
import math
import shlex
import urllib.request
from pathlib import Path
from scope_recall.core.recall_policy import encode_embedding_text

pairs = [
    ("Docker 和配置保存在存储空间 3，记忆及文件数据保存在存储空间 1。", "记忆文件放空间一，容器与配置放空间三。"),
    ("这个项目的设备屏幕是 1024×600 的横屏。", "开发板显示屏分辨率为 1024 乘 600，使用横向布局。"),
    ("代码修改完成后要运行仓库的本地检查。", "更改源码以后先通过项目自带的检查再交付。"),
    ("语义搜索使用 OpenAI 的文本嵌入模型。", "记忆的向量检索由 OpenAI embedding 提供。"),
]
texts = [encode_embedding_text(text, kind=kind)
         for pair in pairs for text, kind in zip(pair, ("document", "query"))]
key = None
for line in Path("/config/model.env").read_text().splitlines():
    if line.startswith("OPENAI_API_KEY="):
        key = shlex.split(line.split("=", 1)[1])[0]
if not key:
    raise SystemExit("credential missing")
request = urllib.request.Request(
    "https://api.openai.com/v1/embeddings",
    data=json.dumps({"model": "text-embedding-3-small", "input": texts, "dimensions": 1536}).encode(),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
except Exception as exc:
    raise SystemExit(type(exc).__name__) from None
vectors = [row["embedding"] for row in sorted(result["data"], key=lambda row: row["index"])]
def cosine(a, b):
    return sum(x*y for x,y in zip(a,b)) / math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))
positive = [cosine(vectors[i], vectors[i+1]) for i in range(0, len(texts), 2)]
negative = [cosine(vectors[i], vectors[j+1]) for i in range(0,len(texts),2)
            for j in range(0,len(texts),2) if i != j]
assert min(positive) > max(negative), "calibration pairs overlap"
threshold = round((min(positive) + max(negative))/2, 3)
report = {"model": result["model"], "dimensions": len(vectors[0]), "positive_cosines": positive,
          "negative_cosines": negative, "vector_threshold": threshold, "usage": result["usage"],
          "limitation": "Four synthetic pairs validate initial routing, not broad retrieval quality."}
Path("/config/embedding-check.json").write_text(json.dumps(report, indent=2)+"\n")
print(json.dumps(report))

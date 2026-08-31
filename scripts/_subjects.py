"""被试清单的唯一读取入口。

先前每个采集/分析脚本各写一份 [("kylin11","kylin-desktop-v11"), ...]，
新增被试要改 10 处，漏改一处就是静默的覆盖缺口。改为都从
config/subjects.json 读，新增被试只动那一个文件。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_CFG = json.loads((ROOT / "config" / "subjects.json").read_text())

SUBJECTS = _CFG["subjects"]
TIERS = _CFG["tiers"]
# 兼容旧代码里的 (did, image) 元组列表形态
PAIRS = [(s["did"], s["image"]) for s in SUBJECTS]
DIDS = [s["did"] for s in SUBJECTS]
IMAGES = {s["did"]: s["image"] for s in SUBJECTS}
FAMILY = {s["did"]: s["family"] for s in SUBJECTS}
METHOD = {s["did"]: s["method"] for s in SUBJECTS}
SHORT  = {s["did"]: s["short"] for s in SUBJECTS}   # 图表/矩阵表头用的短名


def image_ref(did, tier):
    return f"{IMAGES[did]}:{tier}"

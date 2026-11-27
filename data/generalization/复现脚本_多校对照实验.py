# -*- coding: utf-8 -*-
"""多校泛化验证：扩校前后对照实验（离线域名层口径）
阶段1：official_domains 由 1 所扩至 6 所
阶段2：在阶段1基础上增加"他校真实域名排除表"

运行方式：
    在本文件所在目录执行  python 复现脚本_多校对照实验.py
依赖：numpy / scikit-learn / joblib / tldextract / requests / beautifulsoup4
说明：路径全部按本文件位置推导，无需修改；不联网，不写数据库，输出写入本目录下的 _运行输出 文件夹。
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(os.path.dirname(HERE))            # 项目根目录
SRC = os.path.join(PKG, "01_检测程序", "源码")
OUT = os.path.join(HERE, "_运行输出")
os.makedirs(OUT, exist_ok=True)

sys.path.insert(0, SRC)
import detector  # noqa: E402

with open(os.path.join(SRC, "data", "features.json"), encoding="utf-8") as fh:
    base = json.load(fh)

SCHOOLS = {
    "xmu.edu.cn": "厦门大学",
    "fzu.edu.cn": "福州大学",
    "hqu.edu.cn": "华侨大学",
    "jmu.edu.cn": "集美大学",
    "qznu.edu.cn": "泉州师范学院",
}
EXCLUDE = ["xmut.edu.cn", "jnu.edu.cn", "fjut.edu.cn", "mnnu.edu.cn", "hnu.edu.cn"]
MAIN = {"xmu.edu.cn": "xmu", "fzu.edu.cn": "fzu", "hqu.edu.cn": "hqu",
        "jmu.edu.cn": "jmu", "qznu.edu.cn": "qznu"}
VARIANT = {"xmu": "xrnu", "fzu": "f2u", "hqu": "hgu", "jmu": "jrnu", "qznu": "q2nu"}

samples = []
for official, name in SCHOOLS.items():
    m = MAIN[official]
    v = VARIANT[m]
    samples += [
        {"school": name, "official": official, "technique": "可疑域名后缀",
         "url": f"http://{m}-edu.xyz", "label": 1},
        {"school": name, "official": official, "technique": "诱导子域",
         "url": f"http://login.{m}-edu.cn", "label": 1},
        {"school": name, "official": official, "technique": "官方域名拼接",
         "url": f"http://{official}.verify.xyz", "label": 1},
        {"school": name, "official": official, "technique": "形近替换",
         "url": f"http://{v}.edu.cn", "label": 1},
    ]
for d in EXCLUDE:
    samples.append({"school": "对照（他校真实域名）", "official": "-",
                    "technique": "极相似对照", "url": "http://" + d, "label": 0})


def build(stage):
    feats = copy.deepcopy(base)
    feats["official_domains"] = dict(base["official_domains"])
    feats["official_domains"].update(SCHOOLS)
    if stage == 2:
        feats["known_safe_domains"] = dict(base["known_safe_domains"])
        for d in EXCLUDE:
            feats["known_safe_domains"][d] = "他校真实域名（排除表）"
    return feats


def run(features, urls):
    feat_path = os.path.join(OUT, "_tmp_features.json")
    with open(feat_path, "w", encoding="utf-8") as fh:
        json.dump(features, fh, ensure_ascii=False, indent=2)
    detector.DEFAULT_FEATURES_PATH = feat_path
    from detector import ml_detector
    ml_detector._safe_cache.update({"key": None, "domains": (), "suffixes": (), "official": ()})
    import importlib
    from detector import engine as engine_mod
    importlib.reload(engine_mod)
    det = engine_mod.Detector(features=features)
    det.content_fetcher.fetch = lambda url: {"ok": False, "error": "离线评测：未抓取页面内容（域名层口径）"}
    results = []
    for u in urls:
        r = det.detect(u)
        results.append({"url": u, "score": r["score"], "level": r["level"],
                        "domain_score": r["domain_score"], "reasons": r["reasons"]})
    return results


urls = [s["url"] for s in samples]
print("样本数", len(samples))

for stage, tag in ((1, "stage1"), (2, "stage2")):
    res = run(build(stage), urls)
    hit = sum(1 for r in res if r["level"] in ("可疑", "高危"))
    dist = {}
    for r in res:
        dist[r["level"]] = dist.get(r["level"], 0) + 1
    for s, r in zip(samples, res):
        s.setdefault("results", {})[tag] = {"score": r["score"], "level": r["level"],
                                            "reasons": r["reasons"]}
    with open(os.path.join(OUT, f"{tag}.json"), "w", encoding="utf-8") as fh:
        json.dump({"stage": stage, "official_domains": build(stage)["official_domains"],
                   "features": build(stage), "summary": {"hit": hit, "n": len(res), "dist": dist}},
                  fh, ensure_ascii=False, indent=2)

    print(f"\n===== {tag} =====")
    pos = [s for s in samples if s["label"] == 1]
    neg = [s for s in samples if s["label"] == 0]
    p_hit = sum(1 for s in pos if s["results"][tag]["level"] in ("可疑", "高危"))
    n_hit = sum(1 for s in neg if s["results"][tag]["level"] in ("可疑", "高危"))
    print(f"真仿冒 检出 {p_hit}/{len(pos)} = {p_hit / len(pos) * 100:.1f}%")
    print(f"对照   误报 {n_hit}/{len(neg)} = {n_hit / len(neg) * 100:.1f}%")
    by_t = {}
    for s in pos:
        by_t.setdefault(s["technique"], [0, 0])
        by_t[s["technique"]][1] += 1
        if s["results"][tag]["level"] in ("可疑", "高危"):
            by_t[s["technique"]][0] += 1
    for k, (a, b) in by_t.items():
        print(f"  {k}: {a}/{b}")

with open(os.path.join(OUT, "samples.json"), "w", encoding="utf-8") as fh:
    json.dump(samples, fh, ensure_ascii=False, indent=2)
print("\n输出目录", OUT)

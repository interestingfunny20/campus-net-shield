# -*- coding: utf-8 -*-
"""回归：本校 39 条域内样本在扩校前/后的结论变化（离线域名层口径）

运行方式：
    先跑 复现脚本_多校对照实验.py（生成阶段2特征库），再在本文件所在目录执行
    python 复现脚本_本校39条回归.py
"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(os.path.dirname(HERE))            # 项目根目录
SRC = os.path.join(PKG, "01_检测程序", "源码")
UR = os.path.join(PKG, "06_测试数据与指标", "02_指标复现材料")
OUT = os.path.join(HERE, "_运行输出")

sys.path.insert(0, SRC)
import detector  # noqa: E402

with open(os.path.join(SRC, "data", "features.json"), encoding="utf-8") as fh:
    base = json.load(fh)
with open(os.path.join(UR, "onsite_samples.json"), encoding="utf-8") as fh:
    onsite = json.load(fh)

stage2 = os.path.join(OUT, "stage2.json")
if not os.path.exists(stage2):
    raise SystemExit("未找到 stage2.json，请先运行 复现脚本_多校对照实验.py")
with open(stage2, encoding="utf-8") as fh:
    multi = json.load(fh)["features"]


def run(features, urls):
    feat_path = os.path.join(OUT, "_tmp_regression.json")
    with open(feat_path, "w", encoding="utf-8") as fh:
        json.dump(features, fh, ensure_ascii=False, indent=2)
    detector.DEFAULT_FEATURES_PATH = feat_path
    from detector import ml_detector
    ml_detector._safe_cache.update({"key": None, "domains": (), "suffixes": (), "official": ()})
    from detector import engine as engine_mod
    importlib.reload(engine_mod)
    det = engine_mod.Detector(features=features)
    det.content_fetcher.fetch = lambda url: {"ok": False, "error": "离线评测：未抓取页面内容（域名层口径）"}
    results = []
    for u in urls:
        r = det.detect(u)
        results.append({"url": u, "score": r["score"], "level": r["level"], "reasons": r["reasons"]})
    return results


urls = [s["url"] for s in onsite]
before = run(base, urls)
after = run(multi, urls)

for tag, res in (("扩校前", before), ("扩校后", after)):
    dist = {}
    for r in res:
        dist[r["level"]] = dist.get(r["level"], 0) + 1
    hit = dist.get("可疑", 0) + dist.get("高危", 0)
    print(f"{tag}: 检出 {hit}/{len(res)}  分布 {dist}")

changed = []
print("\n结论或分数发生变化的样本：")
for item, b, c in zip(onsite, before, after):
    if (b["level"] != c["level"]) or (b["score"] != c["score"]):
        changed.append({"url": item["url"], "group": item["group"],
                        "before": [b["level"], b["score"]], "after": [c["level"], c["score"]],
                        "new_reasons": [x for x in c["reasons"] if x not in b["reasons"]]})
        print(f"  {item['url']:42s} {b['level']}{b['score']:>4} -> {c['level']}{c['score']:>4}")
print("变化数:", len(changed))

with open(os.path.join(OUT, "regression.json"), "w", encoding="utf-8") as fh:
    json.dump({"before": before, "after": after, "changed": changed}, fh, ensure_ascii=False, indent=2)

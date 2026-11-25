# -*- coding: utf-8 -*-
"""汇总最终指标：规则引擎（新 exe 实测）+ ML（重训模型）+ 域内分组。"""
import json
from pathlib import Path

W = Path(__file__).resolve().parent
HIT = {"可疑", "高危"}

rows = json.load(open(W / "exe_202_results.json", encoding="utf-8"))
pos_set = {l.strip().lower() for l in open(W / "labeled_pos.txt", encoding="utf-8") if l.strip()}
neg_set = {l.strip().lower() for l in open(W / "labeled_neg.txt", encoding="utf-8") if l.strip()}

by_dom = {}
for r in rows:
    by_dom[r["domain"].lower().replace("http://", "").strip("/")] = r


def pick(source_set):
    out = []
    for d in source_set:
        r = by_dom.get(d)
        out.append({"domain": d, "level": (r or {}).get("level"), "score": (r or {}).get("score")})
    return out


pos = pick(pos_set)
neg = pick(neg_set)


def dist(rs):
    d = {}
    for r in rs:
        d[r["level"]] = d.get(r["level"], 0) + 1
    return d


print("正样本 %d: %s" % (len(pos), dist(pos)))
print("负样本 %d: %s" % (len(neg), dist(neg)))
print("未匹配条数:", sum(1 for r in pos + neg if r["level"] is None))


def calc(rs, label):
    hit = sum(1 for r in rs if r["level"] in HIT)
    miss = len(rs) - hit
    return hit, miss


tp, fn = calc(pos, 1)
fp, tn = calc(neg, 0)


def metric(tp, fn, fp, tn, tag):
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    acc = (tp + tn) / (tp + fn + fp + tn)
    print("%-16s TP=%d FN=%d FP=%d TN=%d | 精确率 %.2f%% 召回率 %.2f%% F1 %.4f 误报率 %.2f%% 准确率 %.2f%%"
          % (tag, tp, fn, fp, tn, prec * 100, rec * 100, f1, fpr * 100, acc * 100))
    return {"scope": tag, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "false_positive_rate": round(fpr, 4), "accuracy": round(acc, 4)}


print("\n=== 规则引擎（新 exe 实测）===")
m_a = metric(tp, fn, fp, tn, "口径A 全样本")

pos_d = [r for r in pos if r["level"] != "未知"]
neg_d = [r for r in neg if r["level"] != "未知"]
tp2, fn2 = calc(pos_d, 1)
fp2, tn2 = calc(neg_d, 0)
m_b = metric(tp2, fn2, fp2, tn2, "口径B 仅可判定")
print("可判定: 正 %d / 负 %d" % (len(pos_d), len(neg_d)))

onsite = json.load(open(W / "exe_onsite_results.json", encoding="utf-8"))
meta = {m["domain"]: m["group"] for m in json.load(open(W / "onsite_samples.json", encoding="utf-8"))}
hit = sum(1 for r in onsite if r["level"] in HIT)
print("\n=== 域内（新 exe，39 条）===")
print("检出 %d/%d = %.1f%%，分布 %s" % (hit, len(onsite), hit / len(onsite) * 100, dist(onsite)))
by_group = {}
for r in onsite:
    g = meta.get(r["domain"], "")
    s = by_group.setdefault(g, {"n": 0, "hit": 0})
    s["n"] += 1
    if r["level"] in HIT:
        s["hit"] += 1
for g, s in by_group.items():
    print("  %-8s %d/%d = %.0f%%" % (g, s["hit"], s["n"], s["hit"] / s["n"] * 100))

ml = json.load(open(W / "ml_metrics.json", encoding="utf-8"))
print("\n=== ML（重训，12 维）===")
print("训练 %d 正 + %d 负，CV F1 %.4f，测试集 F1 %.4f" %
      (ml["train_pos"], ml["train_neg"], ml["cv_f1_mean"], ml["test"]["f1"]))
print("精确率 %.2f%% 召回率 %.2f%% 误报率 %.2f%%" %
      (ml["test"]["precision"] * 100, ml["test"]["recall"] * 100, ml["test"]["false_positive_rate"] * 100))

json.dump({"rule_scope_a": m_a, "rule_scope_b": m_b,
           "rule_pos_dist": dist(pos), "rule_neg_dist": dist(neg),
           "onsite": {"hit": hit, "n": len(onsite), "by_group": by_group, "dist": dist(onsite)},
           "ml": ml["test"], "ml_cv_f1": ml["cv_f1_mean"],
           "ml_train": {"pos": ml["train_pos"], "neg": ml["train_neg"]}},
          open(W / "final_metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n已写入 final_metrics.json")

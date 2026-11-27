# -*- coding: utf-8 -*-
"""在标注集上计算规则引擎的混淆矩阵与四项指标（可复现）。

数据来源：exe_202_results.json（exe 批量实测结果，前 100 条为正样本、
  后 102 条为负样本；正样本取自 Phishing.Database ACTIVE 在线钓鱼域名，
  负样本为官方/知名/高校/政府正常站点）
判定口径：预测为正 = 可疑 / 高危；预测为负 = 安全 / 未知
"""
import json
from pathlib import Path

W = Path(__file__).resolve().parent
ALL = json.load(open(W / "exe_202_results.json", encoding="utf-8"))
POS, NEG = ALL[:100], ALL[100:]

POS_LABEL = 1
NEG_LABEL = 0
HIT = {"可疑", "高危"}
UNK = "未知"


def confusion(pos, neg):
    tp = sum(1 for x in pos if x["level"] in HIT)
    fn = len(pos) - tp
    fp = sum(1 for x in neg if x["level"] in HIT)
    tn = len(neg) - fp
    return tp, fn, fp, tn


def ratio(a, b):
    return round(a / b, 4) if b else 0.0


def report(tag, tp, tn, fp, fn):
    p = ratio(tp, tp + fp)
    r = ratio(tp, tp + fn)
    f1 = round(2 * p * r / (p + r), 4) if (p + r) else 0.0
    fpr = ratio(fp, fp + tn)
    acc = ratio(tp + tn, tp + tn + fp + fn)
    out = {
        "scope": tag,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "precision": p, "recall": r, "f1": f1,
        "false_positive_rate": fpr, "accuracy": acc,
        "n_pos": tp + fn, "n_neg": tn + fp,
    }
    print("%-22s TP=%d FN=%d FP=%d TN=%d | 精确率=%.2f%% 召回率=%.2f%% F1=%.4f 误报率=%.2f%% 准确率=%.2f%%"
          % (tag, tp, fn, fp, tn, p * 100, r * 100, f1, fpr * 100, acc * 100))
    return out


def level_dist(rows, name):
    d = {}
    for x in rows:
        d[x["level"]] = d.get(x["level"], 0) + 1
    print("%s 等级分布: %s" % (name, d))
    return d


res = {}
print("样本量: 正 %d / 负 %d" % (len(POS), len(NEG)))
res["pos_level_dist"] = level_dist(POS, "正样本")
res["neg_level_dist"] = level_dist(NEG, "负样本")

# 口径 A：全样本，未知按负处理
tp, fn, fp, tn = confusion(POS, NEG)
res["scope_a_all"] = report("口径A 全样本", tp, tn, fp, fn)

# 口径 B：剔除未知，仅可判定样本
pos_d = [x for x in POS if x["level"] != UNK]
neg_d = [x for x in NEG if x["level"] != UNK]
tp, fn, fp, tn = confusion(pos_d, neg_d)
res["scope_b_decidable"] = report("口径B 仅可判定", tp, tn, fp, fn)
res["decidable_count"] = {"pos": len(pos_d), "neg": len(neg_d)}
print("可判定条数: 正 %d / 负 %d" % (len(pos_d), len(neg_d)))

res["fp_samples"] = [{"domain": x["domain"], "level": x["level"], "score": x["score"]}
                     for x in NEG if x["level"] in HIT]
res["pos_scores"] = sorted({x["score"] for x in POS})

json.dump(res, open(W / "metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写入 metrics.json")

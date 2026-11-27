# -*- coding: utf-8 -*-
"""训练 12 维随机森林（v2 训练集）并在独立标注集上评估，输出可复现指标。

训练集：Phishing.Database ACTIVE 正样本 1500 + Tranco 中国/海外站点负样本 1500
测试集：exe 已批量实测过的 100 正 / 102 负（与训练集零重叠）
特征：与 exe 内 features_extractor 完全一致的 12 维
"""
import json
import os
import sys
from pathlib import Path

W = Path(__file__).resolve().parent

# 检测器源码位置：默认按项目目录结构推导，可用环境变量覆盖（占位常量，换机器无需改代码）
DETECTOR_SRC_ENV = "DOUBAO_DETECTOR_SRC"
DETECTOR_SRC = Path(os.environ.get(DETECTOR_SRC_ENV,
                                   str(W.parents[1] / "01_检测程序" / "源码")))
sys.path.insert(0, str(DETECTOR_SRC))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.model_selection import cross_val_score  # noqa: E402

from detector.features_extractor import FEATURE_ORDER, extract_features  # noqa: E402


def to_url(d):
    return d if d.startswith(("http://", "https://")) else "http://" + d


def featurize(domains):
    rows = [extract_features(to_url(d)) for d in domains]
    return np.array([[r[k] for k in FEATURE_ORDER] for r in rows], dtype=float)


pos = [l.strip() for l in open(W / "train2_pos.txt", encoding="utf-8") if l.strip()]
neg = [l.strip() for l in open(W / "train2_neg.txt", encoding="utf-8") if l.strip()]
X = np.vstack([featurize(pos), featurize(neg)])
y = np.array([1] * len(pos) + [0] * len(neg))
print("训练集 %d 条（正 %d / 负 %d），特征 %d 维" % (len(y), len(pos), len(neg), len(FEATURE_ORDER)))

clf = RandomForestClassifier(n_estimators=200, random_state=2026, n_jobs=-1, min_samples_leaf=3)
cv = cross_val_score(clf, X, y, cv=5, scoring="f1")
print("5 折交叉验证 F1: %.4f (±%.4f)" % (cv.mean(), cv.std()))
clf.fit(X, y)

ALL = json.load(open(W / "exe_202_results.json", encoding="utf-8"))
tp_rows, tn_rows = ALL[:100], ALL[100:]      # 前 100 条正样本、后 102 条负样本
Xp = featurize([x["domain"] for x in tp_rows])
Xn = featurize([x["domain"] for x in tn_rows])
yp, yn = clf.predict(Xp), clf.predict(Xn)
pp, pn = clf.predict_proba(Xp)[:, 1], clf.predict_proba(Xn)[:, 1]

TP = int((yp == 1).sum()); FN = int((yp == 0).sum())
FP = int((yn == 1).sum()); TN = int((yn == 0).sum())
prec = TP / (TP + FP) if (TP + FP) else 0.0
rec = TP / (TP + FN) if (TP + FN) else 0.0
f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
fpr = FP / (FP + TN) if (FP + TN) else 0.0
acc = (TP + TN) / (len(yp) + len(yn))

print("\n=== 独立测试集（100 正 / 102 负）===")
print("TP=%d FN=%d FP=%d TN=%d" % (TP, FN, FP, TN))
print("精确率 %.2f%%  召回率 %.2f%%  F1 %.4f  误报率 %.2f%%  准确率 %.2f%%"
      % (prec * 100, rec * 100, f1, fpr * 100, acc * 100))
print("正样本概率 中位 %.3f / 最低 %.3f | 负样本概率 中位 %.3f / 最高 %.3f"
      % (np.median(pp), pp.min(), np.median(pn), pn.max()))

fake = [tn_rows[i]["domain"] for i in range(len(tn_rows)) if yn[i] == 1]
miss = [tp_rows[i]["domain"] for i in range(len(tp_rows)) if yp[i] == 0]
print("误报 %d 条: %s" % (len(fake), fake[:15]))
print("漏报 %d 条: %s" % (len(miss), miss[:12]))

joblib.dump({"model": clf, "features": list(FEATURE_ORDER)}, W / "phishing_model_v2_12d.pkl")
json.dump({
    "train_pos": len(pos), "train_neg": len(neg),
    "feature_order": list(FEATURE_ORDER),
    "cv_f1_mean": round(float(cv.mean()), 4), "cv_f1_std": round(float(cv.std()), 4),
    "test": {"tp": TP, "fn": FN, "fp": FP, "tn": TN,
             "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
             "false_positive_rate": round(fpr, 4), "accuracy": round(acc, 4)},
    "missed": miss, "false_alarms": fake,
}, open(W / "ml_metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n已保存 phishing_model_v2_12d.pkl / ml_metrics.json")

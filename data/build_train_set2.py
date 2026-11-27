# -*- coding: utf-8 -*-
"""训练集 v2：负样本改为「Tranco 中国站点为主 + 全球站点为辅」，避免模型把 .edu.cn
高校站当成钓鱼站（v1 因负样本全是海外域名，测试集 66 条误报集中在高校官网）。

正样本仍取 Phishing.Database ACTIVE，与标注集严格去重。

注意：本脚本依赖《Phishing.Database》与《Tranco》原始榜单（体积过大未随包提供），
    仅作取数过程留档；复现指标请直接用已产出的 train2_pos.txt / train2_neg.txt。
"""
import random
from pathlib import Path

W = Path(__file__).resolve().parent
ACTIVE = W / "phishing_db" / "Phishing.Database-master" / "output" / "domains.list" / "domains" / "ACTIVE" / "list"
TRANCO = W / "tranco" / "top-1m.csv"

N_POS = 1500
N_NEG_CN = 1000
N_NEG_GLOBAL = 500
SEED = 2026

test_pos = {l.strip().lower() for l in open(W / "labeled_pos.txt", encoding="utf-8") if l.strip()}
test_neg = {l.strip().lower() for l in open(W / "labeled_neg.txt", encoding="utf-8") if l.strip()}
blocked = test_pos | test_neg
blocked |= {d.replace("www.", "", 1) for d in blocked}

# 正样本
act = sorted(set(l.strip().lower() for l in open(ACTIVE, encoding="utf-8") if l.strip()) - blocked)
random.seed(SEED)
pos = random.sample(act, N_POS)
print("正样本: %d（池 %d）" % (len(pos), len(act)))

# 负样本：读取 Tranco 前 20 万名
cn, glob = [], []
with open(TRANCO, encoding="utf-8") as f:
    for line in f:
        rank, dom = line.strip().split(",")
        if int(rank) > 200000:
            break
        d = dom.lower()
        if d in blocked:
            continue
        if d.endswith(".cn"):
            cn.append(d)
        else:
            glob.append(d)
print("Tranco 候选: .cn %d / 其他 %d" % (len(cn), len(glob)))

random.seed(SEED + 1)
neg_cn = random.sample(cn[:5000], min(N_NEG_CN, len(cn)))
neg_gl = random.sample(glob[:5000], min(N_NEG_GLOBAL, len(glob)))
neg = neg_cn + neg_gl
print("负样本: %d（中国 %d + 海外 %d）" % (len(neg), len(neg_cn), len(neg_gl)))

(W / "train2_pos.txt").write_text("\n".join(pos), encoding="utf-8")
(W / "train2_neg.txt").write_text("\n".join(neg), encoding="utf-8")
print("重叠检查: 正 %d 负 %d 正负互交 %d"
      % (len(set(pos) & test_pos), len(set(neg) & test_neg), len(set(pos) & set(neg))))
print("负样本示例:", (neg_cn[:5], neg_gl[:5]))

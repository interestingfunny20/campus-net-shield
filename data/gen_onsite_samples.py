# -*- coding: utf-8 -*-
"""构造「域内」测试样本：仿冒闽南科技学院（mku.edu.cn）的 URL 变体 40 条。

按仿冒手法分 5 组，用于测规则引擎在本校仿冒场景上的召回率。
说明：这些域名均不存在对应页面，抓取必然失败，因此测的是「域名侧」识别能力；
内容侧能力由桌面端演示样本（8 条含真实页面特征）单独呈现。
"""
import json
from pathlib import Path

W = Path(__file__).resolve().parent

groups = {
    "形近替换": [
        "mku-edu.cn", "mku-edu.com", "mkuedu.cn", "mku.edu.com", "mkv.edu.cn",
        "rnku.edu.cn", "mkujwc.cn", "www.mku-edu.cn",
    ],
    "可疑TLD": [
        "mku-edu.top", "mku-edu.xyz", "mku-edu.icu", "mku-edu.vip", "mku-edu.club",
        "mku-edu.online", "mku-edu.site", "mku-edu.link", "mku-edu.monster",
        "mku-edu.stream", "mku-edu.rest",
    ],
    "诱导子域": [
        "jw.mku-edu.cn", "jwc.mku-edu.cn", "login.mku-edu.cn", "mku-login.cn",
        "mku-jwc.cn", "mku-xsc.cn", "mku-pay.cn", "mku-grant.cn", "mku-subsidy.top",
        "mku-jw.cn",
    ],
    "拼接官方": [
        "mku.edu.cn.login-verify.top", "mku.edu.cn.verify.xyz", "mku.edu.cn.evil.com",
        "mku.edu.cn.secure-login.com", "mku.edu.cn.account-update.club",
    ],
    "无关对照": [
        "xkmu.edu.cn", "mkx.edu.cn", "nkmu.edu.cn", "mku2.edu.cn", "jnku.edu.cn",
    ],
}

rows = []
for g, doms in groups.items():
    for d in doms:
        rows.append({"domain": d, "url": "http://" + d, "group": g})

print("合计 %d 条，分组: %s" % (len(rows), {g: len(v) for g, v in groups.items()}))
(W / "onsite_samples.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
(W / "onsite_samples.txt").write_text("\n".join(r["url"] for r in rows), encoding="utf-8")
print("已写 onsite_samples.txt / onsite_samples.json")

# -*- coding: utf-8 -*-
"""扩容已知安全域名白名单（known_safe_domains）。

来源全部可追溯：
    1. 原有 43 条手工白名单；
    2. Tranco 榜单（真实流量排名）前 5000 名中以 .cn 结尾的站点；
    3. 央媒 / 银行 / 运营商 / 互联网大厂等核心品牌域名（必须在 Tranco 中存在才收录）。

排除：被钓鱼滥用的托管建站平台与短链服务（weebly / wixsite / 000webhost / blogspot 等），
这些域名若进白名单会削弱对「托管型钓鱼站」的识别。
"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parent
FEATURES = W / "build_src" / "data" / "features.json"
TRANCO = W / "tranco" / "top-1m.csv"
OUT = W / "build_src" / "data" / "features.json"

EXCLUDE = (
    "weebly", "wixsite", "wix.com", "000webhost", "blogspot", "wordpress.com",
    "github.io", "gitlab.io", "netlify", "vercel", "herokuapp", "blogspot.com",
    "0rz.tw", "bit.ly", "tinyurl", "t.cn", "goo.gl", "ow.ly", "is.gd",
    "shorturl", "dwz.cn", "suo.im", "turl.", "lihi", "pse.is", "reurl",
    "pages.dev", "azurewebsites", "cloudfront", "firebaseapp", "glitch",
    "webnode", "jimdo", "strikingly", "simplesite", "carrd", "bento",
)

BRANDS = {
    # 央媒 / 官方媒体
    "cctv", "xinhuanet", "news", "people", "chinadaily", "gmw", "ce", "cnr",
    "cri", "china", "chinanews", "thepaper", "yicai", "caixin", "jiemian",
    # 门户与内容
    "sina", "sohu", "163", "126", "qq", "weibo", "zhihu", "douban", "tieba",
    "baidu", "360", "sogou", "toutiao", "ifeng", "hupu", "tianya", "csdn",
    "cnblogs", "jianshu", "36kr", "huxiu", "sspai", "zuoyebang",
    # 音视频与社区
    "bilibili", "douyin", "kuaishou", "xiaohongshu", "youku", "iqiyi", "mgtv",
    "tencentvideo", "huya", "douyu", "ximalaya", "qingting", "kugou", "kuwo",
    "netease", "migu", "acfun", "zhihu",
    # 电商与生活服务
    "taobao", "tmall", "jd", "pinduoduo", "suning", "gome", "vip", "kaola",
    "alibaba", "1688", "aliexpress", "meituan", "dianping", "ele", "eleme",
    "ctrip", "qunar", "fliggy", "tongcheng", "ly", "didiglobal", "didichuxing",
    "hellobike", "ofc", "sf-express", "yto", "zto", "sto", "ems", "chinapost",
    # 支付与金融
    "alipay", "unionpay", "icbc", "ccb", "abchina", "boc", "bankcomm", "cmb",
    "spdb", "cib", "psbc", "cmbc", "cebbank", "citicbank", "pingan", "fund",
    "eastmoney", "hexun", "jrj", "xueqiu",
    # 运营商与设备
    "chinamobile", "10086", "chinaunicom", "10010", "chinatelecom", "189",
    "huawei", "xiaomi", "mi", "oppo", "vivo", "lenovo", "zte", "honor",
    "bytedance", "volcengine",
    # 教育 / 学术
    "chaoxing", "zhihuishu", "icourse163", "xuetangx", "cnki", "wanfang",
    "cqvip", "koolearn", "xdf", "xueersi", "gaokao", "chsi",
    # 工具 / 招聘 / 政务
    "wps", "kingsoft", "jianguoyun", "yuque", "gitee", "coding", "aliyun",
    "qcloud", "ctyun", "51job", "zhaopin", "lagou", "boss", "liepin",
    "gov", "12306", "amap", "autonavi", "mapbar", "baidumap",
}


def accepted(domain):
    d = domain.lower()
    if any(x in d for x in EXCLUDE):
        return False
    if d.endswith(".cn") or d.endswith(".com.cn"):
        return True
    main = d.split(".")[0]
    return main in BRANDS


def main():
    feats = json.load(open(FEATURES, encoding="utf-8"))
    old = dict(feats.get("known_safe_domains", {}))
    print("原白名单 %d 条" % len(old))

    picked = []
    with open(TRANCO, encoding="utf-8") as f:
        for line in f:
            rank, dom = line.strip().split(",")
            if int(rank) > 5000:
                break
            d = dom.lower().replace("www.", "", 1)
            if d and accepted(d):
                picked.append((int(rank), d))

    added = {}
    for _, d in picked:
        if d not in old:
            added[d] = "Tranco 前5000收录站点"
    print("Tranco 前5000 命中 %d 个，其中新增 %d 个" % (len(picked), len(added)))

    # 补充核心品牌：从 Tranco 全表确认存在且排名 <= 20000
    brand_hits = {}
    with open(TRANCO, encoding="utf-8") as f:
        for line in f:
            rank, dom = line.strip().split(",")
            if int(rank) > 20000:
                break
            d = dom.lower().replace("www.", "", 1)
            main_part = d.split(".")[0]
            if main_part in BRANDS and d not in old and d not in added:
                brand_hits[d] = "知名品牌站点(Tranco收录)"
    added.update(brand_hits)
    print("品牌补充 %d 个" % len(brand_hits))

    old.update(added)
    feats["known_safe_domains"] = old

    # 顺带把「蹭名」权重提到 40，使 mku-edu.cn 一类可直接判可疑
    w = feats.get("weights", {})
    print("domain_homograph 原值:", w.get("domain_homograph"))
    w["domain_homograph"] = 40
    feats["weights"] = w

    json.dump(feats, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("新白名单 %d 条 → %s" % (len(old), OUT))
    print("抽查:", [k for k in ("cctv.com", "xinhuanet.com", "bilibili.com", "fujian.gov.cn") if k in old])


if __name__ == "__main__":
    main()

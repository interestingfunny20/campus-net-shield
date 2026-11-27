"""
域名特征检测模块

功能：
    1. 解析 URL，提取协议、主机、子域名、注册域名、后缀；
    2. 形近字混淆检测：与高校官方域名对比，识别 "mnul.edu.cn" 冒充 "mku.edu.cn" 这类仿冒；
    3. 子域名异常检测：层级过多、含可疑关键词（login / verify / pay 等）、子域嵌套官方域名；
    4. IP 直连检测、可疑免费域名后缀检测、域名长度异常检测。

返回：
    check(url) -> {"info": {...}, "findings": [{"text": str, "weight": int}, ...]}
"""
import ipaddress
import re

import tldextract

from .domain_similarity import THRESHOLD_HIGH, classify_similarity, similarity_score


class DomainChecker:

    def __init__(self, features):
        self.official_domains = features.get("official_domains", {})
        self.known_safe_domains = features.get("known_safe_domains", {})
        self.suspicious_subdomains = features.get("suspicious_subdomains", [])
        self.suspicious_tlds = features.get("suspicious_tlds", [])
        self.similar_chars = features.get("visual_similar_chars", {})
        self.weights = features.get("weights", {})
        self.similar_threshold = features.get("domain_similar_threshold", THRESHOLD_HIGH)

    @staticmethod
    def _is_ip(host):
        """判断主机名是否为 IP 地址"""
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    def parse_url(self, url):
        """解析 URL，返回结构化域名信息；无法解析返回 None。

        先用 urlsplit 取主机名、用 ipaddress 判断是否 IP 直连，再决定是否交给
        tldextract 解析；所有域名类字段统一转小写，避免大小写差异导致比对失效。
        """
        if not (url and url.strip()):
            return None
        url = url.strip()
        if not re.match(r"^(https?://)", url, re.IGNORECASE):
            url = "http://" + url
        try:
            from urllib.parse import urlsplit
            parts = urlsplit(url)
            raw_host = (parts.hostname or "").lower().strip(".")
        except Exception:
            return None
        if not raw_host:
            return None

        is_ip = self._is_ip(raw_host)
        if is_ip:
            # IP 直连没有域名层级，tldextract 对纯 IP 的结果不可靠，直接跳过
            host, subdomain, registered_domain, suffix = raw_host, "", "", ""
        else:
            try:
                ext = tldextract.extract(url)
            except Exception:
                return None
            host = (ext.fqdn or "").lower().strip(".")
            if not host:
                return None
            subdomain = (ext.subdomain or "").lower()
            registered_domain = (ext.registered_domain or "").lower()
            suffix = (ext.suffix or "").lower()

        try:
            port = str(parts.port) if parts.port else ""
        except Exception:
            port = ""

        return {
            "protocol": "https" if url.lower().startswith("https://") else "http",
            "host": host,
            "port": port,
            "subdomain": subdomain,
            "registered_domain": registered_domain,
            "suffix": suffix,
            "is_ip": is_ip,
        }

    def _check_ip(self, info):
        """IP 直连：正规高校官网极少用 IP 访问"""
        if info["is_ip"]:
            return [{
                "text": "网站使用IP地址直接访问，正规高校官网不会这样做，需高度警惕",
                "weight": self.weights.get("domain_ip_direct", 20),
            }]
        return []

    def _check_visual_similar(self, info):
        """形近字/蹭名仿冒：用 Levenshtein 编辑距离计算主名相似度。

        两条判定线：
            1. 主名相似度达到阈值 → 形近仿冒（domain_visual_similar）；
            2. 以官方主名开头、紧跟连字符/下划线/数字 → 蹭名仿冒（domain_homograph）。
        """
        findings = []
        rd = info["registered_domain"]
        if not rd or rd in self.known_safe_domains:
            return findings
        rd_main = rd.split(".")[0].lower()
        if not rd_main:
            return findings

        for official in self.official_domains:
            if rd == official:
                continue
            official_main = official.split(".")[0].lower()
            if not official_main:
                continue

            sim = similarity_score(rd_main, official_main)
            if sim >= self.similar_threshold:
                level = classify_similarity(sim)
                findings.append({
                    "text": f'域名「{rd}」与高校官方域名「{official}」主名相似度 {sim:.0f}/100（{level}），疑似形近字仿冒钓鱼网站',
                    "weight": self.weights.get("domain_visual_similar", 40),
                })
                continue

            if rd_main.startswith(official_main) and len(rd_main) > len(official_main):
                tail = rd_main[len(official_main)]
                if tail in ("-", "_") or tail.isdigit():
                    findings.append({
                        "text": f'域名「{rd}」以高校官方名「{official_main}」开头并附加分隔符或数字，疑似蹭名仿冒钓鱼网站',
                        "weight": self.weights.get("domain_homograph", 40),
                    })
        return findings

    def _check_subdomain(self, info):
        """子域名异常：层级过多 / 含可疑关键词 / 嵌套官方域名"""
        findings = []
        sub = info["subdomain"]
        if not sub:
            return findings
        parts = sub.split(".")
        if len(parts) >= 3:
            findings.append({
                "text": f"子域名层级过多（{len(parts)}层），正规校园网站通常不超过2层，异常网站常用多层子域名伪装",
                "weight": self.weights.get("domain_many_subdomains", 15),
            })

        for part in parts:
            hit = next((kw for kw in self.suspicious_subdomains if kw in part.lower()), None)
            if hit:
                findings.append({
                    "text": f"子域名含可疑关键词「{hit}」，钓鱼网站常伪装成登录/验证/缴费入口",
                    "weight": self.weights.get("domain_suspicious_subdomain", 15),
                })
                break

        sub_lower = sub.lower()
        for official in self.official_domains:
            if official and official in sub_lower:
                findings.append({
                    "text": f'子域名中嵌入了官方域名「{official}」，属于「官方域名+.evil.com」式仿冒手法',
                    "weight": self.weights.get("domain_homograph", 40),
                })
                break
        return findings

    def _check_tld(self, info):
        """可疑免费/低价域名后缀"""
        if info["suffix"] in self.suspicious_tlds:
            return [{
                "text": f'域名后缀「.{info["suffix"]}」为免费/低价注册后缀，是钓鱼网站高发区',
                "weight": self.weights.get("domain_suspicious_tld", 10),
            }]
        return []

    def _check_host_length(self, info):
        """域名整体过长、连续数字多等异常结构"""
        findings = []
        host = info["host"]
        if len(host) > 40:
            findings.append({
                "text": "网址过长（超过40个字符），异常网站常用长串字符混淆视听",
                "weight": 5,
            })
        digits = sum(1 for ch in host if ch.isdigit())
        if len(host) > 10 and digits >= 6:
            findings.append({
                "text": "网址包含大量连续数字，疑似自动生成的批量钓鱼域名",
                "weight": 5,
            })
        return findings

    def check(self, url):
        """返回 {"info": 域名信息, "findings": 风险发现列表}"""
        info = self.parse_url(url)
        if info is None:
            return {
                "info": None,
                "findings": [{"text": "无法解析该网址，请检查输入是否正确", "weight": 0}],
            }
        findings = []
        findings += self._check_ip(info)
        findings += self._check_visual_similar(info)
        findings += self._check_subdomain(info)
        findings += self._check_tld(info)
        findings += self._check_host_length(info)
        return {"info": info, "findings": findings}

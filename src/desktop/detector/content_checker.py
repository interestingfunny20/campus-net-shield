"""
网页内容特征识别模块

功能：
    1. 识别页面中的校园高发钓鱼关键词（教务系统 / 奖助学金 / 校园缴费等）；
    2. 识别表单中的敏感索取字段（学号、密码、身份证、银行卡、验证码等）；
    3. 识别敏感索取话术与紧迫催促话术（钓鱼网站常用心理压迫手段）；
    4. 识别页面冒充高校官方的行为（页面出现校名但域名并非该校官方域名）。

返回：
    check(content, domain_info) -> {"findings": [{"text","weight"}], "page_present": bool}
"""
import re
from urllib.parse import urlparse


class ContentChecker:

    def __init__(self, features):
        self.campus_keywords = features.get("campus_keywords", [])
        self.sensitive_fields = features.get("sensitive_fields", [])
        self.sensitive_text = features.get("sensitive_text", [])
        self.urgent_text = features.get("urgent_text", [])
        self.official_names = features.get("official_names", [])
        self.official_domains = features.get("official_domains", {})
        self.known_safe_domains = features.get("known_safe_domains", {})
        self.trusted_suffixes = features.get("trusted_suffixes", [])
        self.weights = features.get("weights", {})

    @staticmethod
    def _domain_of(url):
        """从 URL 提取主机名（粗略），用于跨域链接比对"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    @staticmethod
    def _field_match(name, sf):
        """
        字段名精确/边界匹配，避免短词误命中：
            - 完全相等 → 命中
            - 以 _ 或 - 分隔的独立段（如 user_id / login-captcha）→ 命中
            - sf 长度 >= 5 时才允许子串匹配（避免 sid 这类短词误命中 residence_id）
        """
        name = (name or "").lower().strip()
        sf = (sf or "").lower().strip()
        if not (name and sf):
            return False
        if name == sf:
            return True
        if re.search(f"(^|[_-]){re.escape(sf)}([_-]|$)", name):
            return True
        return bool(len(sf) >= 5 and sf in name)

    def check(self, content, domain_info=None):
        """content: ContentFetcher.fetch 的返回结果；domain_info: DomainChecker.check 的 info"""
        content = content or {}
        findings = []
        title = content.get("title", "") or ""
        text = content.get("text", "") or ""
        forms = content.get("forms", []) or []
        links = content.get("links", []) or []
        page_present = bool(title or text or forms)

        is_trusted = False
        rd = suffix = ""
        if domain_info:
            rd = domain_info.get("registered_domain", "") or ""
            suffix = domain_info.get("suffix", "") or ""
            is_trusted = rd in self.official_domains or rd in self.known_safe_domains or suffix in self.trusted_suffixes

        # 1. 校园高发钓鱼关键词（仅对非信任域名计分）
        if not is_trusted:
            hit_kw = set()
            for kw in self.campus_keywords:
                if kw and (kw in title or kw in text):
                    hit_kw.add(kw)
            for kw in hit_kw:
                findings.append({
                    "text": f"页面出现校园高发钓鱼关键词「{kw}」，此类词常被钓鱼网页冒用",
                    "weight": self.weights.get("content_campus_keyword", 5),
                })

        # 2. 表单敏感字段
        for f in forms:
            name = (f.get("name") or "").lower()
            placeholder = f.get("placeholder") or ""
            ptype = (f.get("type") or "").lower()
            if ptype == "password":
                findings.append({
                    "text": "页面存在密码输入框，正在向访客索要账号密码",
                    "weight": self.weights.get("content_password_field", 30),
                })
            hit_field = next((sf for sf in self.sensitive_fields if self._field_match(name, sf)), None)
            if hit_field:
                findings.append({
                    "text": f'页面表单出现敏感字段「{f.get("name")}」（对应{hit_field}），可能索要个人敏感信息',
                    "weight": self.weights.get("content_sensitive_field", 25),
                })
            hit_ph = next((sf for sf in self.sensitive_fields if self._field_match(placeholder, sf)), None)
            if hit_ph:
                findings.append({
                    "text": f"输入框提示「{placeholder}」，疑似索取{hit_ph}",
                    "weight": self.weights.get("content_sensitive_placeholder", 20),
                })

        # 3. 敏感索取话术（页面或标题出现才计分）
        for st in self.sensitive_text:
            if st and (st in text or (title and st in title)):
                findings.append({
                    "text": f"页面出现敏感索取话术「{st}」，正常网站不会在页面直接索要此类信息",
                    "weight": self.weights.get("content_sensitive_sentence", 8),
                })

        # 4. 紧迫催促话术
        if not is_trusted:
            for ut in self.urgent_text:
                if ut and ut in text:
                    findings.append({
                        "text": f"页面出现紧迫催促话术「{ut}」，钓鱼网站常用限时、冻结等话术制造焦虑",
                        "weight": self.weights.get("content_urgent_sentence", 3),
                    })

        # 5. 冒充官方：页面自称某校官方，但域名既非该校官方也非教育/政府后缀
        if domain_info and rd:
            if rd not in self.official_domains and suffix not in self.trusted_suffixes:
                for name in self.official_names:
                    if name and (name in title or name in text):
                        findings.append({
                            "text": f"页面自称「{name}」官方，但当前域名不属于该校官方域名，疑似冒充官方页面",
                            "weight": self.weights.get("content_impersonate_official", 25),
                        })
                        break

        # 6. 外链引流
        if domain_info and links and not is_trusted:
            base_host = domain_info.get("host", "") or ""
            external = set()
            for link in links:
                host = self._domain_of(link)
                if host and host != base_host and not host.endswith(base_host):
                    external.add(host)
            if len(external) >= 5:
                findings.append({
                    "text": f"页面包含 {len(external)} 个跳转到其它域名的链接，异常页面常通过外链引流",
                    "weight": 5,
                })

        return {"findings": findings, "page_present": page_present}

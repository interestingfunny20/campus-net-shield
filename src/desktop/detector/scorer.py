"""
风险综合评分

总分 100 分封顶：0-30 安全，31-65 可疑，66-100 高危。

信任折减只作用于内容风险分：
    1. 注册域名命中官方域名或已知安全域名 → ×0.4，封顶 25 分；
    2. 后缀为 edu.cn 但不在官方域名内 → ×0.7，封顶 35 分；
    3. 其它域名按原值累加。
官方站点本身带登录框属于正常功能，折减用于避免误判；域名层的形近、
蹭名等异常不受折减影响。
"""
from collections import OrderedDict


class Scorer:
    LEVEL_SAFE = "安全"
    LEVEL_SUSPICIOUS = "可疑"
    LEVEL_HIGH = "高危"
    LEVEL_UNKNOWN = "未知"

    def __init__(self, features):
        self.official_domains = features.get("official_domains", {})
        self.known_safe_domains = features.get("known_safe_domains", {})
        self.trusted_suffixes = features.get("trusted_suffixes", [])
        self.weights = features.get("weights", {})

    def _trust_factor(self, domain_info):
        """
        返回 (内容折减系数, 内容分上限)；域名形近仿冒等域名风险不受此影响
        强信任：注册域名命中官方/知名站点白名单
        弱信任：域名后缀为 edu.cn / gov.cn（教育或政府机构域名，整体可信度较高）
        """
        if not domain_info:
            return (1.0, 100)
        rd = domain_info.get("registered_domain", "")
        suffix = domain_info.get("suffix", "")
        if rd in self.official_domains or rd in self.known_safe_domains:
            return (
             self.weights.get("trusted_content_factor", 0.4),
             self.weights.get("trusted_content_cap", 25))
        if suffix in self.trusted_suffixes:
            return (
             self.weights.get("edu_content_factor", 0.7),
             self.weights.get("edu_content_cap", 35))
        return (1.0, 100)

    def score(self, domain_result, content_result, fetch_result):
        """
        domain_result : DomainChecker.check 的结果
        content_result: ContentChecker.check 的结果
        fetch_result  : ContentFetcher.fetch 的结果（用于展示抓取状态）
        返回报告 dict
        """
        cap = self.weights.get("score_cap", 100)
        safe_max = self.weights.get("level_safe_max", 30)
        susp_max = self.weights.get("level_suspicious_max", 65)
        domain_info = domain_result.get("info")
        all_findings = OrderedDict()
        domain_score = 0
        for f in domain_result.get("findings", []):
            text = f["text"]
            if text not in all_findings:
                all_findings[text] = f["weight"]
            domain_score += f["weight"]

        (factor, cap_c) = self._trust_factor(domain_info)
        content_raw = 0
        for f in content_result.get("findings", []):
            text = f["text"]
            if text not in all_findings:
                all_findings[text] = f["weight"]
            content_raw += f["weight"]

        content_score = min(int(content_raw * factor), cap_c)
        if fetch_result:
            total = min(domain_score + content_score, cap)
            if total <= safe_max:
                if fetch_result and not fetch_result.get("ok", False):
                    level = self.LEVEL_UNKNOWN
                else:
                    level = self.LEVEL_SAFE
            elif total <= susp_max:
                level = self.LEVEL_SUSPICIOUS
            else:
                level = self.LEVEL_HIGH
            reasons = list(all_findings.keys())
            if not reasons:
                if fetch_result and not fetch_result.get("ok", False):
                    reasons = [
                     "页面抓取失败，仅完成域名基础检测", fetch_result.get("error", "")]
                else:
                    reasons = [
                     "未发现明显钓鱼风险特征"]
            conclusion = self._conclusion(level, domain_info, fetch_result)
            return {'score':total, 
             'level':level, 
             'reasons':reasons, 
             'conclusion':conclusion, 
             'domain_score':min(domain_score, cap), 
             'content_score':content_score, 
             'domain_info':domain_info, 
             'fetch':{'ok':bool(fetch_result and fetch_result.get("ok")), 
              'error':((fetch_result or {}).get)("error", ""), 
              'title':((fetch_result or {}).get)("title", ""), 
              'final_url':((fetch_result or {}).get)("final_url", ""), 
              'redirect_count':((fetch_result or {}).get)("redirect_count", 0), 
              'is_https':bool(fetch_result and fetch_result.get("is_https")), 
              'status':((fetch_result or {}).get)("status", 0), 
              'form_count':len((fetch_result or {}).get("forms", []))}}

    @staticmethod
    def _conclusion(level, domain_info, fetch_result):
        """按风险等级生成结论文案"""
        if level == Scorer.LEVEL_HIGH:
            return "⚠ 该网页存在明显钓鱼风险，请立即关闭页面，不要输入任何学号、密码、身份证、银行卡或验证码信息！"
        if level == Scorer.LEVEL_SUSPICIOUS:
            return "⚠ 该网页存在可疑特征，建议核实网站身份后再操作，切勿轻易输入个人敏感信息。"
        if level == Scorer.LEVEL_UNKNOWN:
            return "❓ 页面抓取失败，无法确认网页内容，检测结果仅供参考。建议联网重试，或通过学校官方渠道核实该域名后再访问。"
        if fetch_result:
            if not fetch_result.get("ok", False):
                return "网页抓取失败，未发现域名异常，如需进一步确认请联网重试或手动核实。"
            rd = (domain_info or {}).get("registered_domain", "")
            return f'未发现明显钓鱼风险特征，可以正常访问。域名：{rd or "未知"}。'

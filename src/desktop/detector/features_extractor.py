"""
URL 特征提取模块（供 ML 分类器使用）

所有特征全部从 URL 本身提取，不需要联网抓取网页内容，断网也能跑。
共 12 个特征，覆盖域名结构、字符统计、可疑度指标。
"""
import re

from .domain_similarity import similarity_score

SUSPICIOUS_TLDS = {
 "tk", "ml", "ga", "cf", "gq", "xyz", "top", "icu", "vip", "site",
 "club", "online", "fun", "link", "live", "rest", "monster", "review", "stream"}
SUSPICIOUS_SUBDOMAINS = {
 "login", "verify", "secure", "account", "update", "webmail", "sso", "portal",
 "pay", "finaid", "jw", "jwc", "xsc", "lib", "bank", "card", "auth",
 "security", "grant", "subsidy"}
OFFICIAL_DOMAIN = "mku.edu.cn"

def extract_features(url):
    """从 URL 提取 12 维特征向量，返回 dict"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url if "://" in url else "http://" + url)
        host = parsed.hostname or ""
    except Exception:
        host = ""
    else:
        if not host:
            return _zero_features()
        is_ip = 1 if re.match("^\\d{1,3}(\\.\\d{1,3}){3}$", host) else 0
        parts = host.split(".")
        subdomain_parts = parts[:-2] if len(parts) > 2 else []
        main_name = parts[-2] if len(parts) >= 2 else parts[0]
        tld = parts[-1] if len(parts) >= 2 else ""
        host_len = len(host)
        main_len = len(main_name)
        digit_count = sum(1 for c in host if c.isdigit())
        digit_ratio = digit_count / max(host_len, 1)
        special_count = sum(1 for c in host if c in "-_")
        special_ratio = special_count / max(host_len, 1)
        subdomain_depth = len(subdomain_parts)
        has_suspicious_sub = 0
        for part in subdomain_parts:
            if any(kw in part.lower() for kw in SUSPICIOUS_SUBDOMAINS):
                has_suspicious_sub = 1
                break

        tld_suspicious = 1 if tld.lower() in SUSPICIOUS_TLDS else 0
        sim = similarity_score(main_name, OFFICIAL_DOMAIN.split(".")[0])
        starts_with_official = 1 if main_name.startswith(OFFICIAL_DOMAIN.split(".")[0]) else 0
        hyphen_count = host.count("-")
        vowels = sum(1 for c in host.lower() if c in "aeiou")
        vowel_ratio = vowels / max(host_len, 1)
        return {
          'host_len': host_len,
          'main_len': main_len,
          'digit_ratio': digit_ratio,
          'special_ratio': special_ratio,
          'subdomain_depth': subdomain_depth,
          'has_suspicious_sub': has_suspicious_sub,
          'tld_suspicious': tld_suspicious,
          'is_ip': is_ip,
          'similarity_to_official': sim,
          'starts_with_official': starts_with_official,
          'hyphen_count': hyphen_count,
          'vowel_ratio': vowel_ratio}


def _zero_features():
    """URL 无法解析时返回全零特征"""
    return {
      'host_len': 0,
      'main_len': 0,
      'digit_ratio': 0,
      'special_ratio': 0,
      'subdomain_depth': 0,
      'has_suspicious_sub': 0,
      'tld_suspicious': 0,
      'is_ip': 0,
      'similarity_to_official': 0,
      'starts_with_official': 0,
      'hyphen_count': 0,
      'vowel_ratio': 0}


FEATURE_ORDER = [
 "host_len", "main_len", "digit_ratio", "special_ratio",
 "subdomain_depth", "has_suspicious_sub", "tld_suspicious", "is_ip",
 "similarity_to_official", "starts_with_official", "hyphen_count", "vowel_ratio"]

def features_to_vector(feature_dict):
    """把特征 dict 转成有序列表（供 sklearn 输入）"""
    return [feature_dict[k] for k in FEATURE_ORDER]

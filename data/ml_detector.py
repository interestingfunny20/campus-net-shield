"""ML 二次判别模块（随机森林，12 维 URL 特征）。

设计原则：
1. 规则优先。规则已判高危（>65 分）或已由白名单/可信后缀放行的站点，不再走 ML；
2. ML 命中不是加几分，而是把结论抬到对应等级下限，避免“5 + 25 仍然安全”的算术失效；
3. 模型文件或 scikit-learn 缺失时自动降级为纯规则，不影响主流程与界面响应。
"""
from __future__ import annotations

import os
import threading

MODEL_FILE = "phishing_model_v2_12d.pkl"
RULE_HIGH = 65.5     # 规则已判高危，无需复核（留 0.5 容差，避免浮点误差跳过复核）

_lock = threading.Lock()
_state = {"tried": False, "model": None, "features": None}
_safe_cache = {"key": None, "domains": (), "suffixes": (), "official": ()}

# 钓鱼概率 -> 结论下限（等级：31~65 可疑，>65 高危）
_FLOORS = ((0.95, 68.0), (0.88, 55.0), (0.80, 45.0), (0.70, 38.0))


def model_path():
    """模型与 features.json 同放 data 目录，打包与源码运行路径一致。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", MODEL_FILE)


def _ensure_model():
    if _state["tried"]:
        return _state["model"]
    with _lock:
        if _state["tried"]:
            return _state["model"]
        _state["tried"] = True
        path = model_path()
        if not os.path.exists(path):
            return None
        try:
            import joblib
            bundle = joblib.load(path)
            _state["model"] = bundle["model"]
            _state["features"] = bundle.get("features")
            # 单条 URL 预测用多核没有收益；且打包环境下 n_jobs=-1 会走 multiprocessing，
            # 冻结后的进程重复拉起自身时会异常退出，因此统一压成单线程。
            try:
                model = _state["model"]
                if getattr(model, "n_jobs", 1) not in (1, None):
                    model.n_jobs = 1
            except Exception:
                pass
        except Exception:
            _state["model"] = None
    return _state["model"]


def ml_available():
    return _ensure_model() is not None


def _safe_lists():
    """读取当前特征库里的白名单与可信后缀；按文件路径+修改时间缓存，热加载后自动刷新。"""
    try:
        import detector
        path = detector.DEFAULT_FEATURES_PATH
        key = (path, os.path.getmtime(path))
        if _safe_cache["key"] == key:
            return _safe_cache
        with open(path, "r", encoding="utf-8") as f:
            import json
            data = json.load(f)
        domains = tuple(sorted(data.get("known_safe_domains", {}) or {}, key=len, reverse=True))
        suffixes = tuple(data.get("trusted_suffixes", []) or [])
        official = tuple(data.get("official_domains", []) or [])
        _safe_cache.update(key=key, domains=domains, suffixes=suffixes, official=official)
    except Exception:
        return _safe_cache
    return _safe_cache


def _host_of(url):
    try:
        from urllib.parse import urlparse
        host = (urlparse(url if "://" in url else "http://" + url).hostname or "").lower().strip(".")
        return host
    except Exception:
        return ""


def is_trusted_host(host):
    """白名单主域、可信后缀（edu.cn/gov.cn）、本校官方域，都不交给 ML 复核。"""
    if not host:
        return False
    lst = _safe_lists()
    for d in lst["official"]:
        if host == d or host.endswith("." + d):
            return True
    for s in lst["suffixes"]:
        if host.endswith("." + s) or host == s:
            return True
    for d in lst["domains"]:
        if host == d or host.endswith("." + d):
            return True
    return False


def should_use_ml(rule_score, url=None):
    if rule_score > RULE_HIGH:
        return False
    if url is not None and is_trusted_host(_host_of(url)):
        return False
    return ml_available()


def _phishing_prob(url):
    from .features_extractor import extract_features
    feats = extract_features(url)
    order = _state["features"] or list(feats.keys())
    vec = [float(feats.get(k, 0) or 0) for k in order]
    proba = _state["model"].predict_proba([vec])[0]
    classes = list(_state["model"].classes_)
    idx = classes.index(1) if 1 in classes else len(classes) - 1
    return float(proba[idx])


def ml_score_contribution(url):
    """返回 (结论下限分, 钓鱼概率)。下限分为 0 表示 ML 不建议升级；异常时返回 (0.0, 0.0)。"""
    model = _ensure_model()
    if model is None:
        return 0.0, 0.0
    if is_trusted_host(_host_of(url)):
        return 0.0, 0.0
    try:
        prob = _phishing_prob(url)
    except Exception:
        return 0.0, 0.0
    floor = 0.0
    for threshold, value in _FLOORS:
        if prob >= threshold:
            floor = value
            break
    return floor, prob

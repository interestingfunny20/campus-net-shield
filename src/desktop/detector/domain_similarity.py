# decompyle3 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.13.18 (main, Nov 11 2026, 00:19:14) [MSC v.1944 64 bit (AMD64)]
# Embedded file name: detector\domain_similarity.py
"""
域名形近相似度计算模块（Levenshtein 编辑距离算法）

什么是 Levenshtein 编辑距离（通俗版）：
    两个字符串之间，由一个变成另一个，最少需要几步操作。
    允许的操作有三种：
        1. 插入一个字符（如 mku → mnku，插入 n，1 步）
        2. 删除一个字符（如 mnku → mku，删除 n，1 步）
        3. 替换一个字符（如 mku → xmu，把 m 换成 x，1 步）
    步数越少，说明两个字符串长得越像。

相似度怎么算成 0~100 分：
    相似度 = (1 - 编辑距离 / 较长字符串长度) × 100
    例如 "mku" 和 "mnku"：编辑距离 1，较长串长度 4，
    相似度 = (1 - 1/4) × 100 = 75 分。

形近字符归一化：
    钓鱼网站常用 o/0、l/1/i、s/5 这类"长得像"的字符混淆，
    比如把 mku 写成 mk0u。归一化会把这些形近字符先归为同一组，
    再算一次相似度，取两次结果的较大值，让"视觉上像"也能被抓住。
"""
import functools

def levenshtein_distance(a, b):
    """计算两个字符串的 Levenshtein 编辑距离（经典动态规划实现）。

    返回从 a 变成 b 所需的最少编辑次数（插入/删除/替换各计 1 次）。
    时间复杂度 O(len(a)*len(b))，空间优化为两行数组。
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [
         i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)

        prev = cur

    return prev[lb]


_SIMILAR_GROUPS = [
 ('o', '0'),
 ('l', '1', 'i'),
 ('s', '5'),
 ('z', '2'),
 ('b', '8'),
 ('g', '9')]
_NORMALIZE_MAP = {}
for _group in _SIMILAR_GROUPS:
    _rep = _group[0]
    for _ch in _group:
        if len(_ch) == 1:
            _NORMALIZE_MAP[_ch] = _rep

    def normalize(s):
        """把字符串中的形近字符归一化（o/0→o，l/1/i→l，rn→m，vv→w 等）。

    例："mk0u"  →  "mkou"
        "rnku"  →  "mku"
    """
        s = s.lower().strip()
        s = s.replace("rn", "m")
        s = s.replace("vv", "w")
        return "".join((_NORMALIZE_MAP.get(ch, ch) for ch in s))


    def _raw_score(a, b):
        """单次相似度 0~100：(1 - 编辑距离/较长串长度) × 100"""
        if a == b:
            return 100.0
        d = levenshtein_distance(a, b)
        return (1 - d / max(len(a), len(b))) * 100


    @functools.lru_cache(maxsize=1024)
    def similarity_score(a, b):
        """域名主名相似度（0~100 分）。

    计算两次：原始串比对 + 形近归一化后比对，取较大值。
    例：
        similarity_score("mku", "mku")     = 100（完全相同）
        similarity_score("mku", "mnku")    = 75（插入一个 n）
        similarity_score("mku", "mk0u")    = 100（0 归一化为 o）
        similarity_score("mku", "xmu")     = 33（两个字符不同）
    """
        a = a.lower().strip()
        b = b.lower().strip()
        if not (a and b):
            return 0.0
        s_raw = _raw_score(a, b)
        s_norm = _raw_score(normalize(a), normalize(b))
        return max(s_raw, s_norm)


    THRESHOLD_HIGH = 70.0
    THRESHOLD_MEDIUM = 55.0

    def classify_similarity(score):
        """把 0~100 分映射成风险等级文字（供界面直接展示）"""
        if score >= THRESHOLD_HIGH:
            return "高度疑似仿冒"
        if score >= THRESHOLD_MEDIUM:
            return "部分相似，需留意"
        return "差异较大"

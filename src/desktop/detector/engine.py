"""
检测总流程编排

用户输入 URL 后依次执行：
    域名检测 → 网页抓取 → 内容识别 → 综合评分 → 输出报告
"""
import time

from . import ml_detector
from .content_checker import ContentChecker
from .content_fetcher import ContentFetcher
from .domain_checker import DomainChecker
from .scorer import Scorer


class Detector:
    __doc__ = "完整检测器，GUI 与命令行测试共用"

    def __init__(self, features=None):
        from . import FeatureStore
        self.features = features if features is not None else FeatureStore().data
        self.domain_checker = DomainChecker(self.features)
        self.content_fetcher = ContentFetcher(timeout=5)
        self.content_checker = ContentChecker(self.features)
        self.scorer = Scorer(self.features)

    def detect(self, url):
        start = time.time()
        domain_result = self.domain_checker.check(url)
        fetch_result = self.content_fetcher.fetch(url)
        content_result = self.content_checker.check(fetch_result, domain_result.get("info"))
        report = self.scorer.score(domain_result, content_result, fetch_result)
        rule_score = report["score"]
        if ml_detector.should_use_ml(rule_score, url):
            ml_floor, ml_prob = ml_detector.ml_score_contribution(url)
            if ml_floor > 0.5 and ml_floor > rule_score:
                old_score = report["score"]
                new_score = min(ml_floor, 100)
                report["score"] = round(new_score, 1)
                if new_score <= 30:
                    report["level"] = "安全"
                elif new_score <= 65:
                    report["level"] = "可疑"
                else:
                    report["level"] = "高危"
                report["reasons"].append(f"ML 模型二次判别：钓鱼概率 {ml_prob * 100:.0f}%，规则分 {old_score:.0f} 提升至 {new_score:.0f}")
                # 等级被抬高后，结论文案必须随之重算，否则会出现“68 分高危却写可以正常访问”
                report["conclusion"] = Scorer._conclusion(
                    report["level"], domain_result.get("info"), fetch_result
                )
        report["score"] = round(report["score"], 1)
        report["elapsed"] = round(time.time() - start, 2)
        report["url"] = url.strip()
        return report

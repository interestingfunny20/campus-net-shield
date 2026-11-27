"""
detector 包 —— 面向高校学生的轻量钓鱼网页检测工具核心检测逻辑
"""
import json
import os

DEFAULT_FEATURES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "features.json")

class FeatureStore:
    __doc__ = "特征库加载与访问"

    def __init__(self, path=None):
        self.path = path or DEFAULT_FEATURES_PATH
        with open((self.path), "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def weights(self):
        return self.data.get("weights", {})

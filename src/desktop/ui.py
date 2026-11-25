# decompyle3 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.13.18 (main, Nov 11 2026, 00:19:14) [MSC v.1944 64 bit (AMD64)]
# Embedded file name: ui.py
"""
GUI 可视化交互界面（PyQt5）—— 精致美化版

设计：
    - 程序盾牌图标（QPainter 绘制，无外部图片依赖）
    - 深蓝渐变头部 + 浅色渐变背景
    - 风险等级渐变徽章（绿/橙/红）、风险分进度条
    - 检测时进度条转圈动画，结果即时回填
    - 保持核心控件命名稳定，兼容自动化冒烟测试
"""
import os
from PyQt5.QtCore import Qt, QThread, QPointF, pyqtSignal, QRectF
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QPen, QBrush
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QTextBrowser, QMessageBox, QFileDialog, QFrame, QStatusBar, QProgressBar
from detector.engine import Detector
from detector.report import ReportExporter
from detector.report_uploader import upload_async
APP_VERSION = "v2.3"

class RadarChartWidget(QWidget):
    __doc__ = "8维特征雷达图（QPainter 绘制，无外部依赖）"
    DIM_LABELS = [
     "域名长度","数字比例","特殊字符","子域名","IP地址","超长域名","含@符号","连字符"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self.setMaximumSize(340, 340)
        self._values = [0.5] * 8
        self._score = 0

    def set_data(self, values, score=0):
        self._values = [max(0, min(1, v)) for v in values]
        self._score = score
        self.update()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 + 5
        # 预留 68px 给四周文字标签，避免标签被控件边界裁掉
        radius = min(w, h) / 2 - 68
        n = 8
        for layer in range(1, 4):
            r = radius * layer / 3
            points = []
            for i in range(n):
                angle = 2 * math.pi * i / n - math.pi / 2
                points.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))

            pen = QPen(QColor(200, 200, 220, 80), 1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)

            path.closeSubpath()
            p.drawPath(path)

        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2
            end = QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            p.setPen(QPen(QColor(180, 180, 200, 100), 1))
            p.drawLine(QPointF(cx, cy), end)

        p.setPen(QColor(80, 80, 100))
        label_fs = max(7, min(9, int(w / 36)))
        p.setFont(QFont("Microsoft YaHei", label_fs))
        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            lx = cx + (radius + 4) * cos_a
            ly = cy + (radius + 4) * sin_a
            text = self.DIM_LABELS[i]
            if abs(cos_a) < 0.3:
                rect = QRectF(cx - 32, ly - (12 if sin_a > 0 else 0), 64, 16)
                align = Qt.AlignHCenter | Qt.AlignVCenter
            elif cos_a > 0:
                rect = QRectF(lx, ly - 8, 64, 16)
                align = Qt.AlignLeft | Qt.AlignVCenter
            else:
                rect = QRectF(lx - 64, ly - 8, 64, 16)
                align = Qt.AlignRight | Qt.AlignVCenter
            p.drawText(rect, align, text)

        data_points = []
        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2
            r = radius * self._values[i]
            data_points.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))

        if self._score >= 66:
            fill_color = QColor(248, 113, 113, 100)
            line_color = QColor(239, 68, 68)
        elif self._score >= 31:
            fill_color = QColor(251, 191, 36, 100)
            line_color = QColor(245, 158, 11)
        else:
            fill_color = QColor(74, 222, 128, 100)
            line_color = QColor(34, 197, 94)
        p.setBrush(QBrush(fill_color))
        p.setPen(QPen(line_color, 2))
        data_path = QPainterPath()
        data_path.moveTo(data_points[0])
        for pt in data_points[1:]:
            data_path.lineTo(pt)

        data_path.closeSubpath()
        p.drawPath(data_path)
        p.setPen(QColor(60, 60, 80))
        p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        p.drawText(QRectF(0, 5, w, 20), Qt.AlignCenter, "📊 URL 特征雷达图")
        p.end()


LEVEL_GRAD = {
  '安全': ('#86efac', '#4ade80'),
  '可疑': ('#fcd34d', '#fbbf24'),
  '高危': ('#fca5a5', '#f87171'),
  '未知': ('#d4d4d8', '#9ca3af')}
LEVEL_CHUNK = {
  '安全': "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #86efac, stop:1 #4ade80)",
  '可疑': "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #fcd34d, stop:1 #fbbf24)",
  '高危': "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #fca5a5, stop:1 #f87171)",
  '未知': "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #d4d4d8, stop:1 #9ca3af)"}
LEVEL_ICON = {
  '安全': "🐱", '可疑': "😼", '高危': "🙀", '未知': "🐾"}

class DetectWorker(QThread):
    __doc__ = "后台检测线程，避免阻塞界面"
    finished = pyqtSignal(dict)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.detector = Detector()

    def run(self):
        try:
            report = self.detector.detect(self.url)
            upload_async(report)
        except Exception as e:
            report = {'url':self.url, 
             'score':100,  'level':"高危",  'reasons':[
              f"程序内部错误：{str(e)[:150]}"], 
             'conclusion':"检测过程发生异常，请检查网络后重试。", 
             'elapsed':0, 
             'fetch':{'ok':False, 
              'error':str(e)[:150],  'title':"",  'final_url':self.url, 
              'redirect_count':0,  'is_https':False, 
              'ssl_verified':True,  'status':0,  'form_count':0}}
            self.finished.emit(report)
        else:
            self.finished.emit(report)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"校园钓鱼网页检测助手 {APP_VERSION} · 闽南科技学院挑战杯参赛作品")
        self.setWindowIcon(QIcon(self._make_logo()))
        # 初始尺寸按屏幕可用区域自适应：小屏或 125% 缩放时窗口不会超出屏幕、右侧不再被裁掉
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            want_w = min(1080, int(scr.width() * 0.92))
            want_h = min(760, int(scr.height() * 0.92))
        except Exception:
            scr = None
            want_w, want_h = 1080, 760
        self.setMinimumSize(760, 560)
        self.resize(max(want_w, 760), max(want_h, 560))
        if scr is not None:
            self.move(scr.x() + max(0, (scr.width() - max(want_w, 760)) // 2),
                      scr.y() + max(0, (scr.height() - max(want_h, 560)) // 2))
        self._detail_fs = 0
        self.worker = None
        self._last_report = None
        self._build_ui()
        self._apply_style()
        self._apply_detail_font()

    @staticmethod
    def _make_logo(size=72):
        """小猫钓鱼主题 Logo：暖橙渐变圆角底 + 软萌圆脸小猫 + 小鱼竿"""
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QLinearGradient(0, 0, size, size)
        bg.setColorAt(0.0, QColor("#fdba74"))
        bg.setColorAt(1.0, QColor("#fb923c"))
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, size, size, size * 0.32, size * 0.32)
        w, h = size, size
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(w * 0.5, h * 0.55), size * 0.28, size * 0.25)
        ear_pen = Qt.NoPen
        p.setBrush(QColor("#ffffff"))
        path_l = QPainterPath()
        path_l.moveTo(w * 0.28, h * 0.42)
        path_l.lineTo(w * 0.32, h * 0.25)
        path_l.lineTo(w * 0.42, h * 0.38)
        path_l.closeSubpath()
        p.drawPath(path_l)
        path_r = QPainterPath()
        path_r.moveTo(w * 0.72, h * 0.42)
        path_r.lineTo(w * 0.68, h * 0.25)
        path_r.lineTo(w * 0.58, h * 0.38)
        path_r.closeSubpath()
        p.drawPath(path_r)
        p.setBrush(QColor("#fca5a5"))
        p.drawEllipse(QPointF(w * 0.35, h * 0.33), size * 0.03, size * 0.04)
        p.drawEllipse(QPointF(w * 0.65, h * 0.33), size * 0.03, size * 0.04)
        p.setBrush(QColor("#1e293b"))
        p.drawEllipse(QPointF(w * 0.4, h * 0.55), size * 0.035, size * 0.045)
        p.drawEllipse(QPointF(w * 0.6, h * 0.55), size * 0.035, size * 0.045)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(w * 0.41, h * 0.54), size * 0.012, size * 0.012)
        p.drawEllipse(QPointF(w * 0.61, h * 0.54), size * 0.012, size * 0.012)
        p.setBrush(QColor("#f472b6"))
        nose_path = QPainterPath()
        nose_path.moveTo(w * 0.48, h * 0.62)
        nose_path.lineTo(w * 0.52, h * 0.62)
        nose_path.lineTo(w * 0.5, h * 0.65)
        nose_path.closeSubpath()
        p.drawPath(nose_path)
        pen = p.pen()
        pen.setWidthF(size * 0.02)
        pen.setCapStyle(Qt.RoundCap)
        pen.setColor(QColor("#78716c"))
        p.setPen(pen)
        p.drawArc(int(w * 0.44), int(h * 0.64), int(w * 0.12), int(h * 0.08), 200, -140)
        rod_pen = p.pen()
        rod_pen.setWidthF(size * 0.025)
        rod_pen.setColor(QColor("#92400e"))
        p.setPen(rod_pen)
        p.drawLine(int(w * 0.78), int(h * 0.18), int(w * 0.92), int(h * 0.4))
        line_pen = p.pen()
        line_pen.setWidthF(size * 0.01)
        line_pen.setColor(QColor("#a8a29e"))
        p.setPen(line_pen)
        p.drawLine(int(w * 0.92), int(h * 0.4), int(w * 0.92), int(h * 0.55))
        p.setBrush(QColor("#38bdf8"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(w * 0.92, h * 0.58), size * 0.04, size * 0.025)
        p.end()
        return pm

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(96)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 12, 22, 12)
        hl.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(self._make_logo(64).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(64, 64)
        hl.addWidget(logo)
        tbox = QVBoxLayout()
        tbox.setSpacing(3)
        title = QLabel("🐱 闽南科技学院 · 校园钓鱼网页检测助手")
        title.setObjectName("headerTitle")
        sub = QLabel("输入网址，小猫帮你钓出钓鱼网站，识别仿冒教务·缴费·奖助学金 🎣")
        sub.setObjectName("headerSub")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        hl.addLayout(tbox, 1)
        badge = QLabel("🐟 挑战杯 · 科技发明制作 B 类")
        badge.setObjectName("headerBadge")
        hl.addWidget(badge, 0, Qt.AlignTop)
        root.addWidget(header)
        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入要检测的网址，例如：https://www.mku.edu.cn 或 https://example.com")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setMinimumHeight(46)
        self.url_input.returnPressed.connect(self.on_detect)
        self.detect_btn = QPushButton("🎣  开始钓鱼检测")
        self.detect_btn.setObjectName("primaryBtn")
        self.detect_btn.setMinimumHeight(46)
        self.detect_btn.setMinimumWidth(160)
        self.detect_btn.clicked.connect(self.on_detect)
        input_row.addWidget(self.url_input, 1)
        input_row.addWidget(self.detect_btn)
        root.addLayout(input_row)
        card = QFrame()
        card.setObjectName("resultCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 20, 22, 20)
        cl.setSpacing(14)
        top = QHBoxLayout()
        top.setSpacing(18)
        self.level_badge = QLabel("等待检测")
        self.level_badge.setObjectName("levelBadge")
        self.level_badge.setAlignment(Qt.AlignCenter)
        self.level_badge.setFixedHeight(78)
        self.level_badge.setMinimumWidth(230)
        top.addWidget(self.level_badge, 0)
        right = QVBoxLayout()
        right.setSpacing(4)
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        t1 = QLabel("风险评分")
        t1.setObjectName("scoreTitle")
        self.score_value = QLabel("-- / 100")
        self.score_value.setObjectName("scoreValue")
        r1.addWidget(t1)
        r1.addStretch(1)
        r1.addWidget(self.score_value)
        right.addLayout(r1)
        self.score_bar = QProgressBar()
        self.score_bar.setObjectName("scoreBar")
        self.score_bar.setRange(0, 100)
        self.score_bar.setValue(0)
        self.score_bar.setTextVisible(False)
        self.score_bar.setFixedHeight(14)
        right.addWidget(self.score_bar)
        hint = QLabel("0-30 安全  ·  31-65 可疑  ·  66-100 高危")
        hint.setObjectName("scoreHint")
        right.addWidget(hint)
        top.addLayout(right, 1)
        cl.addLayout(top)
        self.conclusion_label = QLabel("输入网址后点击「一键检测」，本地离线特征库将立即开始分析。")
        self.conclusion_label.setObjectName("conclusionLabel")
        self.conclusion_label.setWordWrap(True)
        cl.addWidget(self.conclusion_label)
        reason_title = QLabel("风险原因与检测详情")
        reason_title.setObjectName("reasonTitle")
        cl.addWidget(reason_title)
        result_layout = QHBoxLayout()
        result_layout.setSpacing(12)
        self.reason_view = QTextBrowser()
        self.reason_view.setOpenExternalLinks(False)
        self.reason_view.setMinimumHeight(170)
        result_layout.addWidget(self.reason_view, 3)
        radar_card = QFrame()
        radar_card.setObjectName("radarCard")
        self.radar_card = radar_card
        radar_layout = QVBoxLayout(radar_card)
        radar_layout.setContentsMargins(8, 8, 8, 8)
        self.radar_widget = RadarChartWidget()
        radar_layout.addWidget(self.radar_widget, 0, Qt.AlignCenter)
        result_layout.addWidget(radar_card, 1)
        cl.addLayout(result_layout, 1)
        root.addWidget(card, 1)
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.export_btn = QPushButton("📄  导出检测报告（txt）")
        self.export_btn.setObjectName("secondaryBtn")
        self.export_btn.setEnabled(False)
        self.export_btn.setMinimumHeight(36)
        self.export_btn.clicked.connect(self.on_export)
        self.export_pdf_btn = QPushButton("📑  导出 PDF 报告")
        self.export_pdf_btn.setObjectName("secondaryBtn")
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setMinimumHeight(36)
        self.export_pdf_btn.clicked.connect(self.on_export_pdf)
        self.load_features_btn = QPushButton("📂  加载外部特征库")
        self.load_features_btn.setObjectName("secondaryBtn")
        self.load_features_btn.setMinimumHeight(36)
        self.load_features_btn.clicked.connect(self.on_load_features)
        tip = QLabel("辅助识别工具，检测结果仅供参考，不能保证 100% 识别全部钓鱼网站。")
        tip.setObjectName("tip")
        tip.setWordWrap(True)
        tip.setMinimumWidth(0)
        bottom.addWidget(self.export_btn)
        bottom.addWidget(self.export_pdf_btn)
        bottom.addWidget(self.load_features_btn)
        bottom.addWidget(tip, 1)
        root.addLayout(bottom)
        self.status = QStatusBar()
        self.status.setObjectName("statusBar")
        self.setStatusBar(self.status)
        self.status.showMessage("🌸 就绪 · 闽南科技学院网络工程专业 · 本地特征库 v2.0 · 断网可用域名检测 💗")

    def _apply_style(self):
        self.setStyleSheet("\n            QMainWindow {\n                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,\n                    stop:0 #fff7ed, stop:1 #ffedd5);\n            }\n            QFrame#header {\n                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,\n                    stop:0 #fb923c, stop:0.6 #fdba74, stop:1 #fcd34d);\n                border-radius: 20px;\n            }\n            QLabel#headerTitle {\n                font-size: 22px; font-weight: bold; color: #ffffff;\n            }\n            QLabel#headerSub { font-size: 13px; color: #fff7ed; }\n            QLabel#headerBadge {\n                font-size: 11px; color: #ffffff;\n                background: rgba(255,255,255,0.25);\n                border: 1px solid rgba(255,255,255,0.4);\n                border-radius: 14px; padding: 6px 14px;\n            }\n            QLineEdit {\n                padding: 0 16px; font-size: 14px;\n                border: 2px solid #fed7aa; border-radius: 16px;\n                background: #ffffff;\n            }\n            QLineEdit:focus { border: 2px solid #fb923c; background: #fff7ed; }\n            QPushButton#primaryBtn {\n                font-size: 15px; font-weight: bold; color: #ffffff;\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #fb923c, stop:1 #f59e0b);\n                border: none; border-radius: 16px;\n            }\n            QPushButton#primaryBtn:hover {\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #ea580c, stop:1 #d97706);\n            }\n            QPushButton#primaryBtn:pressed { background: #c2410c; }\n            QPushButton#primaryBtn:disabled { background: #fdba74; }\n            QPushButton#secondaryBtn {\n                font-size: 13px; color: #c2410c;\n                background: #ffffff; border: 2px solid #fed7aa;\n                border-radius: 14px; padding: 0 18px;\n            }\n            QPushButton#secondaryBtn:hover { background: #fff7ed; }\n            QPushButton#secondaryBtn:disabled { color: #fdba74; }\n            QFrame#resultCard {\n                background: #ffffff;\n                border: 2px solid #ffedd5;\n                border-radius: 20px;\n            }\n            QLabel#levelBadge {\n                font-size: 16px; font-weight: bold; color: #ffffff;\n                background: #d4d4d8; border-radius: 16px;\n            }\n            QLabel#scoreTitle { font-size: 13px; color: #9ca3af; }\n            QLabel#scoreValue { font-size: 22px; font-weight: bold; color: #c2410c; }\n            QLabel#scoreHint { font-size: 11px; color: #fdba74; }\n            QProgressBar#scoreBar {\n                border: none; border-radius: 8px;\n                background: #f3f4f6;\n            }\n            QProgressBar#scoreBar::chunk {\n                border-radius: 8px;\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #fdba74, stop:1 #fb923c);\n            }\n            QLabel#conclusionLabel {\n                font-size: 14px; color: #4b5563;\n                background: #fff7ed; border-radius: 14px; padding: 12px 16px;\n            }\n            QLabel#reasonTitle { font-size: 14px; font-weight: bold; color: #c2410c; }\n            QTextBrowser {\n                font-size: 13px; color: #6b7280;\n                border: 2px solid #ffedd5; border-radius: 14px;\n                background: #fffbeb; padding: 10px;\n            }\n            QLabel#tip { font-size: 12px; color: #fdba74; }\n            QStatusBar#statusBar {\n                font-size: 12px; color: #fff7ed;\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #fb923c, stop:1 #fcd34d);\n                border-radius: 10px;\n            }\n            QStatusBar#statusBar::item { border: none; }\n        ")

    # ---------- 自适应排版 ----------
    def _ui_scale(self):
        """按窗口宽度算缩放系数：900px 为设计基准（13px 字号），放大最多 1.55 倍、缩小到 0.9 倍。"""
        try:
            w = self.width()
        except Exception:
            return 1.0
        return max(0.9, min(w / 900.0, 1.55))

    def _apply_detail_font(self):
        """检测详情文字随窗口大小自适应；字号变化时才重设样式，避免频繁重绘。"""
        try:
            fs = int(round(13 * self._ui_scale()))
            if fs == self._detail_fs:
                return
            self._detail_fs = fs
            self.reason_view.setStyleSheet(
                "QTextBrowser {\n"
                f"    font-size: {fs}px; color: #6b7280;\n"
                "    border: 2px solid #ffedd5; border-radius: 14px;\n"
                "    background: #fffbeb; padding: 10px;\n"
                "}"
            )
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_detail_font()
        # 窄窗口优先保证详情文字可读，雷达图暂时隐藏；窗口拉宽后自动恢复
        try:
            self.radar_card.setVisible(self.width() >= 840)
        except Exception:
            pass

    def on_detect(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.information(self, "提示", "请先输入需要检测的网址。")
            return
        if not url.startswith(('http://', 'https://')):
            url = "http://" + url
            self.url_input.setText(url)
        host_part = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
        host_name = host_part.split(":", 1)[0].strip().lower()
        if (not host_name) or ("." not in host_name) or host_name in ("localhost", "127.0.0.1", "0.0.0.0"):
            QMessageBox.warning(self, "格式提示",
                                "请输入可检测的公网网址，例如：https://www.mku.edu.cn\n"
                                "本机或内网地址（localhost、127.0.0.1、192.168.x.x）无法完成检测。")
            self.status.showMessage("⚠️ 输入无效：请填写完整的公网网址")
            return
        self.detect_btn.setEnabled(False)
        self.detect_btn.setText("🎣  小猫钓鱼中…")
        self.export_btn.setEnabled(False)
        self.export_pdf_btn.setEnabled(False)
        self.status.showMessage(f"🎣 正在钓鱼检测：{url}")
        self.conclusion_label.setText("🐱 小猫正在分析域名和页面内容，请稍候…\n\n📡 联网抓取最长约5秒\n📴 断网时自动降级为本地域名检测\n⏱️ 超时后仍可基于域名特征给出初步判断")
        self._set_level_display("—")
        self.score_value.setText("-- / 100")
        self.score_bar.setRange(0, 0)
        self.reason_view.setPlainText("🐱 小猫正在努力分析中…\n\n正在做的事：\n  ✅ 解析域名结构\n  ✅ 比对形近仿冒特征\n  ✅ 抓取页面内容\n  ✅ 识别敏感索取关键词\n  ✅ 综合评分")
        self.worker = DetectWorker(url)
        self.worker.finished.connect(self._safe_show_result)
        self.worker.start()

    def _safe_show_result(self, report):
        """界面刷新兜底：任何绘制异常都只写日志，不让 Qt 槽函数异常终止进程。"""
        try:
            self._show_result(report)
        except Exception as exc:
            try:
                import traceback
                path = os.path.join(os.environ.get("TEMP", "."), "校园网盾_界面异常.txt")
                with open(path, "a", encoding="utf-8") as f:
                    f.write(str(exc) + "\n")
                    f.write(traceback.format_exc() + "\n")
            except Exception:
                pass

    def _show_result(self, report):
        self.detect_btn.setEnabled(True)
        self.detect_btn.setText("🔍  一键检测")
        self._last_report = report
        self.export_btn.setEnabled(True)
        self.export_pdf_btn.setEnabled(True)
        level = report.get("level", "—")
        self._set_level_display(level)
        raw_score = report.get("score", 0)
        try:
            score = int(round(float(raw_score)))
        except (TypeError, ValueError):
            score = 0
        elapsed = report.get("elapsed", 0)
        self.score_value.setText(f"{score} / 100")
        self.score_bar.setRange(0, 100)
        self.score_bar.setValue(score)
        chunk = LEVEL_CHUNK.get(level, LEVEL_CHUNK["安全"])
        self.score_bar.setStyleSheet(f"QProgressBar#scoreBar {{ border:none; border-radius:7px; background:#e2e8f0; }}QProgressBar#scoreBar::chunk {{ border-radius:7px; background:{chunk}; }}")
        self.conclusion_label.setText(report.get("conclusion", ""))
        parts = [
         "【风险原因】"]
        reasons = report.get("reasons", [])
        if reasons:
            parts += [f"{i}. {r}" for i, r in enumerate(reasons, 1)]
        else:
            parts.append("未发现明显风险特征。")
        fetch = report.get("fetch", {})
        parts.append("")
        parts.append("【页面抓取情况】")
        if fetch.get("ok"):
            parts.append(f'· 抓取成功（HTTP {fetch.get("status", "?")}）')
            parts.append(f'· 页面标题：{fetch.get("title", "（无标题）")}')
            parts.append(f'· 最终地址：{fetch.get("final_url", "")}')
            parts.append(f'· 重定向 {fetch.get("redirect_count", 0)} 次 · {"HTTPS 加密" if fetch.get("is_https") else "HTTP 明文"} · 证书{"正常" if fetch.get("ssl_verified") else "异常"} · 表单输入框 {fetch.get("form_count", 0)} 个')
        else:
            err = fetch.get("error", "未知原因")
            parts.append(f"· 抓取失败：{err}")
            parts.append("· 已自动降级：基于域名特征完成基础检测")
            parts.append("· 建议：检查网络连接后重新检测，或通过学校官网核实该网址")
        self.reason_view.setPlainText("\n".join(parts))
        self._update_radar(report)
        self.status.showMessage(f'检测完成：{report.get("url", "")} · 等级 {level} · {score} 分 · 耗时 {elapsed} 秒')

    def _update_radar(self, report):
        """从 URL 提取 8 维特征，更新雷达图"""
        url = report.get("url", "")
        score = report.get("score", 0)
        try:
            from urllib.parse import urlparse
            import re
            parsed = urlparse(url if url.startswith("http") else f"http://{url}")
            domain = parsed.netloc.lower()
            values = [
             min(1, len(domain) / 40),
             min(1, sum((c.isdigit() for c in domain)) / max(len(domain), 1) * 5),
             min(1, sum((c in "-._%" for c in domain)) / max(len(domain), 1) * 5),
             min(1, domain.count(".") / 5),
             1.0 if re.match("^\\d+\\.\\d+\\.\\d+\\.\\d+$", domain) else 0,
             1.0 if len(domain) > 30 else len(domain) / 30,
             1.0 if "@" in url else 0,
             1.0 if "-" in domain else 0]
            self.radar_widget.set_data(values, score)
        except Exception:
            pass

    def _set_level_display(self, level):
        if level == "—":
            self.level_badge.setText("🐱 等待钓鱼")
            self.level_badge.setStyleSheet("background:#d4d4d8; color:#ffffff; border-radius:16px;")
            return
        (c1, c2) = LEVEL_GRAD.get(level, ('#d4d4d8', '#d4d4d8'))
        icon = LEVEL_ICON.get(level, "")
        level_text = {
          '安全': "🐱 钓到小鱼啦 · 安全",
          '可疑': "😼 好像有奇怪的鱼 · 可疑",
          '高危': "🙀 钓到炸弹了 · 高危",
          '未知': "🐾 没抓到页面 · 未知"}.get(level, level)
        self.level_badge.setText(level_text)
        self.level_badge.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c1}, stop:1 {c2});color:#ffffff; border-radius:16px;")
        self.level_badge.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))

    def on_export(self):
        if not self._last_report:
            return
        home = os.environ.get("PHISHING_GUARD_HOME")
        if home:
            default_dir = os.path.join(home, "reports")
        else:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        os.makedirs(default_dir, exist_ok=True)
        (path, _) = QFileDialog.getSaveFileName(self, "导出检测报告", os.path.join(default_dir, "检测报告.txt"), "文本文件 (*.txt)")
        if not path:
            return
        try:
            saved = ReportExporter.save(self._last_report, path)
            QMessageBox.information(self, "导出成功", f"报告已保存到：\n{saved}")
        except Exception as e:
            try:
                QMessageBox.critical(self, "导出失败", f"保存报告时出错：{str(e)[:150]}")
            finally:
                e = None
                del e

    def on_export_pdf(self):
        """导出 PDF 检测报告"""
        if not self._last_report:
            return
        home = os.environ.get("PHISHING_GUARD_HOME")
        if home:
            default_dir = os.path.join(home, "reports")
        else:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        os.makedirs(default_dir, exist_ok=True)
        import datetime
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        (path, _) = QFileDialog.getSaveFileName(self, "导出 PDF 检测报告", os.path.join(default_dir, f"检测报告_{stamp}.pdf"), "PDF 文件 (*.pdf)")
        if not path:
            return
        try:
            saved = ReportExporter.to_pdf(self._last_report, path)
            QMessageBox.information(self, "导出成功", f"PDF 报告已保存到：\n{saved}")
        except Exception as e:
            try:
                QMessageBox.critical(self, "导出失败", f"生成 PDF 时出错：{str(e)[:150]}")
            finally:
                e = None
                del e

    def on_load_features(self):
        """加载外部特征库 features.json，无需改源码即可更新检测规则"""
        (path, _) = QFileDialog.getOpenFileName(self, "选择特征库文件 features.json", "", "JSON 特征库 (*.json)")
        if not path:
            return
        try:
            from detector import FeatureStore
            from detector.engine import Detector
            new_features = FeatureStore(path)
            version = new_features.get("feature_version", "未知")
            desc = new_features.get("feature_description", "")
            import detector
            detector.DEFAULT_FEATURES_PATH = path
            self.detector = Detector(features=new_features.data)
            self.status.showMessage(f"✅ 特征库已加载：v{version} · {desc[:30]} · {os.path.basename(path)}")
            QMessageBox.information(self, "加载成功", f"特征库已更新！\n\n版本：v{version}\n说明：{desc}\n\n新规则已立即生效，无需重启程序。")
        except Exception as e:
            try:
                QMessageBox.critical(self, "加载失败", f"读取特征库时出错：\n{str(e)[:200]}")
            finally:
                e = None
                del e


def run():
    try:
        from PyQt5.QtCore import Qt

        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    app = QApplication([])
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    app.exec_()

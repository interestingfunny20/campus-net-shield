"""
PyQt5 图形界面

    - 盾牌图标与雷达图均由 QPainter 绘制，不依赖外部图片
    - 顶部渐变条、风险等级徽章、风险分进度条
    - 检测在子线程执行，完成后把结果回填主线程
    - 主要控件保留固定 objectName，便于界面自动化测试读取
"""
import os

from detector.engine import Detector
from detector.report import ReportExporter
from detector.report_uploader import upload_async
from PyQt5.QtCore import QPointF, QRectF, Qt, QThread, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

APP_VERSION = "v2.3"

class RadarChartWidget(QWidget):
    __doc__ = "8维特征雷达图（QPainter 绘制，无外部依赖）"
    DIM_LABELS = [
     "域名长度","数字比例","特殊字符","子域名","IP地址","超长域名","含@符号","连字符"]

    def __init__(self, parent=None):
        super().__init__(parent)
        # 允许随卡片剩余空间自由伸缩，避免全屏时控件比卡片还大而被裁切
        self.setMinimumSize(140, 140)
        self.setMaximumSize(600, 600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        cx, cy = w / 2, h / 2 + 8
        # 字号随控件宽度收放，再按实际字形宽度预留横向空间，保证 @ 这类窄字符也不被裁
        label_fs = max(7, min(10, int(w / 36)))
        fm_top = QFontMetricsF(QFont("Microsoft YaHei", label_fs))
        max_lw = max(fm_top.horizontalAdvance(t) for t in self.DIM_LABELS) + max(4.0, label_fs * 0.4)
        # 顶部留出标题高度（约 30px）+ 标签高度，避免标题压住「域名长度」
        radius = max(30, min(w / 2 - (max_lw + 6), h / 2 - 24, cy - 54))
        n = 8
        for layer in range(1, 4):
            r = radius * layer / 3
            points = []
            for i in range(n):
                angle = 2 * math.pi * i / n - math.pi / 2
                points.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))

            pen = QPen(QColor(190, 190, 215, 120), 1)
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
            p.setPen(QPen(QColor(175, 175, 200, 130), 1))
            p.drawLine(QPointF(cx, cy), end)

        p.setPen(QColor(80, 80, 100))
        p.setFont(QFont("Microsoft YaHei", label_fs))
        show_labels = radius >= 22
        # 按实际字形宽度排版：含 @ 等窄字符的标签不再被固定宽度矩形裁掉
        fm = fm_top
        for i in range(n):
            if not show_labels:
                break
            angle = 2 * math.pi * i / n - math.pi / 2
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            lx = cx + (radius + 4) * cos_a
            ly = cy + (radius + 4) * sin_a
            text = self.DIM_LABELS[i]
            tw = fm.horizontalAdvance(text) + max(4.0, label_fs * 0.4)
            th = fm.height() + 2
            if abs(cos_a) < 0.3:
                box_x = min(max(1, cx - tw / 2), max(1, w - tw - 1))
                box_y = ly - th - 1 if sin_a < 0 else ly + 1
                align = Qt.AlignHCenter | Qt.AlignVCenter
            else:
                box_x = min(lx, max(1, w - tw - 1)) if cos_a > 0 else max(1, lx - tw)
                box_y = ly - th / 2
                align = (Qt.AlignLeft if cos_a > 0 else Qt.AlignRight) | Qt.AlignVCenter
            box_y = min(max(1, box_y), max(1, h - th - 1))
            p.drawText(QRectF(box_x, box_y, tw, th), align | Qt.TextDontClip, text)

        data_points = []
        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2
            # 以 22% 为显示基线：全 0 的维度也能画出完整八边形，不再塌成几根射线
            r = radius * (0.22 + 0.78 * self._values[i])
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
        # 每个顶点画一个小圆点，低值维度也能看出位置
        p.setBrush(QBrush(line_color))
        p.setPen(Qt.NoPen)
        for pt in data_points:
            p.drawEllipse(pt, 2.5, 2.5)
        p.setPen(QColor(60, 60, 80))
        p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        p.drawText(QRectF(0, 4, w, 22), Qt.AlignHCenter | Qt.AlignTop | Qt.TextDontClip, "📊 URL 特征雷达图")
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
              'status':0,  'form_count':0}}
            self.finished.emit(report)
        else:
            self.finished.emit(report)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"校园钓鱼网页检测助手 {APP_VERSION} · 闽南科技学院挑战杯参赛作品")
        self.setWindowIcon(self._best_icon())
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
        self._style_scale = -1.0
        self._fitted = False
        self._chunk_qss = "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #fdba74, stop:1 #fb923c)"
        self.worker = None
        self._last_report = None
        self._build_ui()
        self._apply_all()

    @classmethod
    def _icon_file(cls):
        """优先用带多尺寸帧的图标文件，找不到再退回画笔生成的小猫 Logo。"""
        try:
            import sys

            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            for rel in ("icon.ico", os.path.join("assets", "icon.ico")):
                path = os.path.join(base, rel)
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        return None

    def _best_icon(self):
        path = self._icon_file()
        if path:
            ico = QIcon(path)
            if not ico.isNull():
                return ico
        return QIcon(self._make_logo())

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

    def _fit_to_screen(self):
        """首次显示时把窗口完整塞进屏幕可用区域，避免左侧/底部内容被屏幕边缘裁掉。"""
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            fg = self.frameGeometry()
            if fg.width() > scr.width() or fg.height() > scr.height():
                self.resize(min(fg.width(), scr.width() - 2), min(fg.height(), scr.height() - 2))
                fg = self.frameGeometry()
            x = min(max(fg.x(), scr.x()), scr.x() + scr.width() - fg.width())
            y = min(max(fg.y(), scr.y()), scr.y() + scr.height() - fg.height())
            self.move(max(x, scr.x()), max(y, scr.y()))
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_fitted", False):
            self._fitted = True
            self._fit_to_screen()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        self._root_lay = root
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(96)
        self._header = header
        hl = QHBoxLayout(header)
        self._hlay = hl
        hl.setContentsMargins(22, 12, 22, 12)
        hl.setSpacing(16)
        logo = QLabel()
        self._logo = logo
        logo.setPixmap(self._make_logo(64).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(64, 64)
        hl.addWidget(logo)
        tbox = QVBoxLayout()
        self._tbox = tbox
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
        self._input_row = input_row
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
        card_outer = QHBoxLayout(card)
        self._card_outer = card_outer
        card_outer.setContentsMargins(22, 20, 22, 20)
        card_outer.setSpacing(14)
        cl = QVBoxLayout()
        self._clay = cl
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(14)
        top = QHBoxLayout()
        self._top_lay = top
        top.setSpacing(18)
        self.level_badge = QLabel("等待检测")
        self.level_badge.setObjectName("levelBadge")
        self.level_badge.setAlignment(Qt.AlignCenter)
        self.level_badge.setFixedHeight(78)
        self.level_badge.setMinimumWidth(230)
        top.addWidget(self.level_badge, 0)
        right = QVBoxLayout()
        self._right_lay = right
        right.setSpacing(4)
        r1 = QHBoxLayout()
        self._r1_lay = r1
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
        self.reason_view = QTextBrowser()
        self.reason_view.setOpenExternalLinks(False)
        self.reason_view.setMinimumHeight(170)
        cl.addWidget(self.reason_view, 1)
        radar_card = QFrame()
        radar_card.setObjectName("radarCard")
        self.radar_card = radar_card
        radar_layout = QVBoxLayout(radar_card)
        self._radar_lay = radar_layout
        radar_layout.setContentsMargins(8, 8, 8, 8)
        self.radar_widget = RadarChartWidget()
        radar_layout.addWidget(self.radar_widget, 1)
        card_outer.addLayout(cl, 3)
        card_outer.addWidget(radar_card, 2)
        root.addWidget(card, 1)
        bottom = QHBoxLayout()
        self._bottom_lay = bottom
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

    def _style_template(self):
        return ("\n            QMainWindow {\n                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,\n                    stop:0 #fff7ed, stop:1 #ffedd5);\n            }\n            QFrame#header {\n                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,\n                    stop:0 #fb923c, stop:0.6 #fdba74, stop:1 #fcd34d);\n                border-radius: 20px;\n            }\n            QLabel#headerTitle {\n                font-size: 22px; font-weight: bold; color: #ffffff;\n            }\n            QLabel#headerSub { font-size: 13px; color: #fff7ed; }\n            QLabel#headerBadge {\n                font-size: 11px; color: #ffffff;\n                background: rgba(255,255,255,0.25);\n                border: 1px solid rgba(255,255,255,0.4);\n                border-radius: 14px; padding: 6px 14px;\n            }\n            QLineEdit {\n                padding: 0 16px; font-size: 14px;\n                border: 2px solid #fed7aa; border-radius: 16px;\n                background: #ffffff;\n            }\n            QLineEdit:focus { border: 2px solid #fb923c; background: #fff7ed; }\n            QPushButton#primaryBtn {\n                font-size: 15px; font-weight: bold; color: #ffffff;\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #fb923c, stop:1 #f59e0b);\n                border: none; border-radius: 16px;\n            }\n            QPushButton#primaryBtn:hover {\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #ea580c, stop:1 #d97706);\n            }\n            QPushButton#primaryBtn:pressed { background: #c2410c; }\n            QPushButton#primaryBtn:disabled { background: #fdba74; }\n            QPushButton#secondaryBtn {\n                font-size: 13px; color: #c2410c;\n                background: #ffffff; border: 2px solid #fed7aa;\n                border-radius: 14px; padding: 0 18px;\n            }\n            QPushButton#secondaryBtn:hover { background: #fff7ed; }\n            QPushButton#secondaryBtn:disabled { color: #fdba74; }\n            QFrame#resultCard {\n                background: #ffffff;\n                border: 2px solid #ffedd5;\n                border-radius: 20px;\n            }\n            QLabel#levelBadge {\n                font-size: 16px; font-weight: bold; color: #ffffff;\n                background: #d4d4d8; border-radius: 16px;\n            }\n            QLabel#scoreTitle { font-size: 13px; color: #9ca3af; }\n            QLabel#scoreValue { font-size: 22px; font-weight: bold; color: #c2410c; }\n            QLabel#scoreHint { font-size: 11px; color: #fdba74; }\n            QProgressBar#scoreBar {\n                border: none; border-radius: 8px;\n                background: #f3f4f6;\n            }\n            QProgressBar#scoreBar::chunk {\n                border-radius: 8px;\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #fdba74, stop:1 #fb923c);\n            }\n            QLabel#conclusionLabel {\n                font-size: 14px; color: #4b5563;\n                background: #fff7ed; border-radius: 14px; padding: 12px 16px;\n            }\n            QLabel#reasonTitle { font-size: 14px; font-weight: bold; color: #c2410c; }\n            QTextBrowser {\n                font-size: 13px; color: #6b7280;\n                border: 2px solid #ffedd5; border-radius: 14px;\n                background: #fffbeb; padding: 10px;\n            }\n            QLabel#tip { font-size: 12px; color: #fdba74; }\n            QStatusBar#statusBar {\n                font-size: 12px; color: #fff7ed;\n                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,\n                    stop:0 #fb923c, stop:1 #fcd34d);\n                border-radius: 10px;\n            }\n            QStatusBar#statusBar::item { border: none; }\n        ")

    # ---------- 自适应排版 ----------
    BASE_W = 900.0
    BASE_H = 700.0

    def _ui_scale(self):
        """整页缩放系数：以 900×700 为设计基准，同时受宽、高约束，范围 0.85~1.5。"""
        try:
            w, h = self.width(), self.height()
        except Exception:
            return 1.0
        s = min(w / self.BASE_W, h / self.BASE_H)
        return max(0.85, min(s, 1.5))

    def _s(self, v, s=None):
        """按当前缩放系数把一个设计像素值换算成实际像素。"""
        if s is None:
            s = self._ui_scale()
        return max(1, round(v * s))

    def _scale_qss(self, qss, s):
        """把样式表里所有 px 数值按缩放系数等比放缩，避免逐个手写。"""
        import re

        def _rep(m):
            v = float(m.group(1)) * s
            return "%d%s" % (max(1, round(v)), m.group(2))

        return re.sub(r"([0-9]+(?:\.[0-9]+)?)(px)", _rep, qss)

    def _apply_style(self, scale=None):
        """应用整套样式：字号、圆角、内边距全部随窗口缩放。"""
        s = self._ui_scale() if scale is None else scale
        try:
            self.setStyleSheet(self._scale_qss(self._style_template(), s))
        except Exception:
            pass

    def _apply_metrics(self, scale=None):
        """应用固定像素的尺寸/间距（高度、宽度、外边距），同样随窗口缩放。"""
        s = self._ui_scale() if scale is None else scale
        try:
            self._root_lay.setContentsMargins(self._s(20, s), self._s(20, s), self._s(20, s), self._s(16, s))
            self._root_lay.setSpacing(self._s(14, s))
            self._header.setFixedHeight(self._s(96, s))
            self._hlay.setContentsMargins(self._s(22, s), self._s(12, s), self._s(22, s), self._s(12, s))
            self._hlay.setSpacing(self._s(16, s))
            logo_px = self._s(64, s)
            self._logo.setFixedSize(logo_px, logo_px)
            self._logo.setPixmap(self._make_logo(logo_px))
            self._tbox.setSpacing(self._s(3, s))
            self._input_row.setSpacing(self._s(10, s))
            self.url_input.setMinimumHeight(self._s(46, s))
            # 窗口不够宽时换短占位文字，避免提示语被截断
            if self.width() < 1180:
                self.url_input.setPlaceholderText("请输入要检测的网址，如 https://www.mku.edu.cn")
            else:
                self.url_input.setPlaceholderText("请输入要检测的网址，例如：https://www.mku.edu.cn 或 https://example.com")
            self.detect_btn.setMinimumHeight(self._s(46, s))
            self.detect_btn.setMinimumWidth(self._s(160, s))
            self._card_outer.setContentsMargins(self._s(22, s), self._s(20, s), self._s(22, s), self._s(20, s))
            self._card_outer.setSpacing(self._s(14, s))
            self._clay.setContentsMargins(0, 0, 0, 0)
            self._clay.setSpacing(self._s(14, s))
            self._top_lay.setSpacing(self._s(18, s))
            self.level_badge.setFixedHeight(self._s(78, s))
            self.level_badge.setMinimumWidth(self._s(230, s))
            self._right_lay.setSpacing(self._s(4, s))
            self._r1_lay.setSpacing(self._s(8, s))
            self.score_bar.setFixedHeight(self._s(14, s))
            self.reason_view.setMinimumHeight(self._s(170, s))
            self._radar_lay.setContentsMargins(self._s(8, s), self._s(8, s), self._s(8, s), self._s(8, s))
            radar_min = max(self._s(150, s), 220)
            self.radar_widget.setMinimumSize(radar_min, radar_min)
            self.radar_card.setMinimumWidth(radar_min + 2 * self._s(8, s))
            self._bottom_lay.setSpacing(self._s(12, s))
            for btn in (self.export_btn, self.export_pdf_btn, self.load_features_btn):
                btn.setMinimumHeight(self._s(36, s))
        except Exception:
            pass

    def _apply_detail_font(self):
        """检测详情文字随窗口大小自适应（与整页缩放保持同一系数）。"""
        try:
            s = self._ui_scale()
            fs = round(13 * s)
            if fs == self._detail_fs:
                return
            self._detail_fs = fs
            self.reason_view.setStyleSheet(
                "QTextBrowser {\n"
                f"    font-size: {fs}px; color: #6b7280;\n"
                f"    border: 2px solid #ffedd5; border-radius: {self._s(14, s)}px;\n"
                f"    background: #fffbeb; padding: {self._s(10, s)}px;\n"
                "}"
            )
        except Exception:
            pass

    def _apply_score_bar_style(self):
        """风险分进度条：圆角与色块同样随窗口缩放，等级色沿用最近一次的检测结果。"""
        try:
            s = self._ui_scale()
            chunk = self._chunk_qss or LEVEL_CHUNK["未知"]
            r = self._s(7, s)
            self.score_bar.setStyleSheet(
                f"QProgressBar#scoreBar {{ border:none; border-radius:{r}px; background:#e2e8f0; }}"
                f"QProgressBar#scoreBar::chunk {{ border-radius:{r}px; background:{chunk}; }}"
            )
        except Exception:
            pass

    def _apply_all(self):
        """一次性刷新整页的自适应排版。"""
        s = self._ui_scale()
        self._style_scale = s
        self._apply_style(s)
        self._apply_metrics(s)
        self._apply_detail_font()
        self._apply_score_bar_style()
        self._sync_min_size()

    def _sync_min_size(self):
        """窗口最小尺寸不低于内容所需，避免用户把窗口缩得太小后按钮、雷达被裁掉。"""
        try:
            need = self.centralWidget().minimumSizeHint()
            scr = QApplication.primaryScreen().availableGeometry()
            min_w = min(max(760, need.width()), max(760, scr.width()))
            min_h = min(max(560, need.height()), max(560, scr.height()))
            cur = self.minimumSize()
            if abs(min_w - cur.width()) > 6 or abs(min_h - cur.height()) > 6:
                self.setMinimumSize(min_w, min_h)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        s = self._ui_scale()
        # 缩放系数变化够大才整套重排，避免拖动窗口时反复重绘
        if abs(s - getattr(self, "_style_scale", -1.0)) >= 0.03:
            self._apply_all()
        else:
            self._apply_detail_font()
        # 雷达图尽量都显示；空间实在放不下才隐藏（阈值按宽度和高度同时判断）
        try:
            self.radar_card.setVisible(self.width() >= 840 and self.height() >= 640)
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
            score = round(float(raw_score))
        except (TypeError, ValueError):
            score = 0
        elapsed = report.get("elapsed", 0)
        self.score_value.setText(f"{score} / 100")
        self.score_bar.setRange(0, 100)
        self.score_bar.setValue(score)
        chunk = LEVEL_CHUNK.get(level, LEVEL_CHUNK["安全"])
        self._chunk_qss = chunk
        self._apply_score_bar_style()
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
            parts.append(f'· 重定向 {fetch.get("redirect_count", 0)} 次 · {"HTTPS 加密" if fetch.get("is_https") else "HTTP 明文"} · 表单输入框 {fetch.get("form_count", 0)} 个')
        else:
            err = fetch.get("error", "未知原因")
            parts.append(f"· 抓取失败：{err}")
            parts.append("· 已自动降级：基于域名特征完成基础检测")
            parts.append("· 建议：检查网络连接后重新检测，或通过学校官网核实该网址")
        self.reason_view.setPlainText("\n".join(parts))
        self._update_radar(report)
        self.status.showMessage(f'检测完成：{report.get("url", "")} · 等级 {level} · {score} 分 · 耗时 {elapsed} 秒')

    def _update_radar(self, report):
        """从 URL 提取 8 维特征，更新雷达图（每一项都归一到 0~1，正常站点不应被拉满）"""
        url = report.get("url", "")
        score = report.get("score", 0)
        try:
            import re
            from urllib.parse import urlparse
            parsed = urlparse(url if url.startswith("http") else f"http://{url}")
            host = (parsed.netloc or "").lower()
            if "@" in host:
                host = host.split("@")[-1]
            if ":" in host:
                host = host.split(":", 1)[0]
            if not host:
                host = (parsed.path or "").split("/")[0].lower()
            length = max(len(host), 1)
            digits = sum(1 for c in host if c.isdigit()) / length
            # 特殊字符只算 . 和 - 之外的符号，避免正常域名的点号把这一维直接拉满
            special = sum(1 for c in host if (not c.isalnum()) and c not in ".-") / length
            dots = host.count(".")
            is_ip = bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host))
            values = [
             min(1, len(host) / 40),
             min(1, digits * 8),
             min(1, special * 8),
             min(1, max(0, dots - 1) / 3),
             1.0 if is_ip else 0,
             1.0 if len(host) > 30 else len(host) / 30,
             1.0 if "@" in url else 0,
             1.0 if "-" in host else 0]
            self.radar_widget.set_data(values, score)
        except Exception:
            pass

    def _set_level_display(self, level):
        r = self._s(16)
        if level == "—":
            self.level_badge.setText("🐱 等待钓鱼")
            self.level_badge.setStyleSheet(f"background:#d4d4d8; color:#ffffff; border-radius:{r}px;")
            return
        c1, c2 = LEVEL_GRAD.get(level, ('#d4d4d8', '#d4d4d8'))
        level_text = {
          '安全': "🐱 钓到小鱼啦 · 安全",
          '可疑': "😼 好像有奇怪的鱼 · 可疑",
          '高危': "🙀 钓到炸弹了 · 高危",
          '未知': "🐾 没抓到页面 · 未知"}.get(level, level)
        self.level_badge.setText(level_text)
        self.level_badge.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c1}, stop:1 {c2});color:#ffffff; border-radius:{r}px;")
        self.level_badge.setFont(QFont("Microsoft YaHei", max(9, round(14 * self._ui_scale())), QFont.Bold))

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

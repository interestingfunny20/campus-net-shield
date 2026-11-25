"""桌面端启动入口（PyInstaller 打包用）。

职责：设置 OpenMP/线程环境、开启 DPI 感知、主线程预热 ML 依赖、拉起主窗口。
"""
import os
import sys

# 必须在任何 numpy / scipy / sklearn 导入之前设置：
# 避免重复加载 OpenMP 运行时导致进程被 abort，同时限制线程数，减少打包环境下的资源冲突。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


def _resource(rel_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


def _log(msg):
    """windowed 模式没有控制台，异常写临时日志便于排查。"""
    try:
        path = os.path.join(os.environ.get("TEMP", "."), "校园网盾_启动日志.txt")
        with open(path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _patch_tldextract():
    """离线可用：直接用内置 Public Suffix List 快照，不发起联网下载。"""
    try:
        import tldextract

        tldextract.extract = tldextract.TLDExtract(suffix_list_urls=())
    except Exception as e:
        _log("tldextract patch 失败：%r" % (e,))


def _preload_ml():
    """在主线程预热 ML 依赖：子线程首次加载大型扩展容易与 Qt 的运行时冲突。"""
    try:
        import numpy  # noqa: F401
        import joblib  # noqa: F401
        from sklearn.ensemble import RandomForestClassifier  # noqa: F401

        from detector import ml_detector

        ok = ml_detector.ml_available()
        _log("ML 预热完成，模型可用：%s" % ok)
        return ok
    except Exception as e:
        _log("ML 预热失败：%r" % (e,))
        return False


def main():
    # 打包后若走 multiprocessing 分支，必须先 freeze_support，否则会重复拉起本 exe
    try:
        import multiprocessing

        multiprocessing.freeze_support()
    except Exception:
        pass

    _patch_tldextract()
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    _preload_ml()

    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QApplication

    # 开启 Qt 自带的高 DPI 缩放，保证 125%/150% 缩放下文字按真实像素渲染不发虚
    try:
        from PyQt5.QtCore import Qt

        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    import ui

    app = QApplication([])
    app.setStyle("Fusion")
    icon = _resource(os.path.join("assets", "icon.ico"))
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))

    window = ui.MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

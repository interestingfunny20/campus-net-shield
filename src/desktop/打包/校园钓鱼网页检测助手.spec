# -*- mode: python ; coding: utf-8 -*-
# 路径一律按 SPECPATH（本 spec 所在目录）推导，不再依赖构建机器的绝对路径。
# 只要保持 源码\launcher.py、源码\data、源码\assets 的相对位置，可直接在源码目录执行：
#   python -m PyInstaller 打包\校园钓鱼网页检测助手.spec
import os

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

SRC = os.path.abspath(os.path.join(SPECPATH, ".."))  # 源码根：01_检测程序\源码

datas = [(os.path.join(SRC, "data"), "data"), (os.path.join(SRC, "assets"), "assets")]
hiddenimports = ['reportlab.graphics.barcode', 'reportlab.pdfbase.cidfonts', 'sklearn.ensemble', 'sklearn.tree', 'joblib']
datas += collect_data_files('tldextract')
datas += collect_data_files('certifi')
datas += collect_data_files('reportlab')
datas += collect_data_files('sklearn')
hiddenimports += collect_submodules('sklearn')
hiddenimports += collect_submodules('joblib')
hiddenimports += collect_submodules('scipy')


a = Analysis(
    [os.path.join(SRC, 'launcher.py')],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='校园钓鱼网页检测助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(SRC, 'assets', 'icon.ico')],
)

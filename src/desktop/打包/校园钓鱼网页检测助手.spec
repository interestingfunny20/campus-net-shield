# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('C:/Users/MR/Doubao/chats/2026-11-24/new-chat-1/_work/build_src/data', 'data'), ('C:/Users/MR/Doubao/chats/2026-11-24/new-chat-1/_work/build_src/assets', 'assets')]
hiddenimports = ['reportlab.graphics.barcode', 'reportlab.pdfbase.cidfonts', 'sklearn.ensemble', 'sklearn.tree', 'joblib']
datas += collect_data_files('tldextract')
datas += collect_data_files('certifi')
datas += collect_data_files('reportlab')
datas += collect_data_files('sklearn')
hiddenimports += collect_submodules('sklearn')
hiddenimports += collect_submodules('joblib')
hiddenimports += collect_submodules('scipy')


a = Analysis(
    ['C:/Users/MR/Doubao/chats/2026-11-24/new-chat-1/_work/build_src/launcher.py'],
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
    icon=['C:/Users/MR/Doubao/chats/2026-11-24/new-chat-1/_work/build_src/assets/icon.ico'],
)

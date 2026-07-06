# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("customtkinter") + collect_submodules("tkinterdnd2")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/fonts/Assistant.ttf", "assets/fonts"),
        ("assets/fonts/OFL.txt", "assets/fonts"),
        ("assets/images/capital_gains_logo.png", "assets/images"),
        ("assets/images/capital_gains_logo_transparent.png", "assets/images"),
    ],
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
    name="CapitalGainsFIFO",
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
)

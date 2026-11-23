# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

pyogrio_datas, pyogrio_binaries, pyogrio_imports = collect_all("pyogrio")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=pyogrio_binaries,
    datas=pyogrio_datas + [("shp_tool/data/土地利用.gpkg", "shp_tool/data")],
    hiddenimports=pyogrio_imports + ["pyogrio._geometry", "openpyxl"],
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
    [],
    exclude_binaries=True,
    name='ShpWorkbench',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ShpWorkbench',
)

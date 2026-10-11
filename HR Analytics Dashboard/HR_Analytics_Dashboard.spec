# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build for the single-file HR_Analytics_Dashboard.exe.
# Build with build_exe.bat (or: pyinstaller HR_Analytics_Dashboard.spec --noconfirm).
#
# The local AI model is NOT bundled (2 GB) — the .exe looks for it in a models/
# folder next to itself and offers to download it from the AI Advisor tab.

from PyInstaller.utils.hooks import collect_all

# llama-cpp-python loads its compiled llama.dll at runtime, which PyInstaller
# can't see from the imports alone
llama_datas, llama_binaries, llama_hidden = collect_all('llama_cpp')

a = Analysis(
    ['HR_Analytics_Dashboard.py'],
    pathex=[],
    binaries=llama_binaries,
    datas=llama_datas + [
        ('Default documents', 'Default documents'),
        ('assets/app.ico', 'assets'),
    ],
    hiddenimports=llama_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Installed in the dev environment but never imported by the app
    excludes=['tkinter', 'seaborn', 'scipy', 'IPython', 'pytest'],
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
    name='HR_Analytics_Dashboard',
    icon='assets/app.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX compression can corrupt the Qt and llama DLLs
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

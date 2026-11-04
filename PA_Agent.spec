# -*- mode: python ; coding: utf-8 -*-
# ruff: noqa: F821  -- SPECPATH/Analysis/PYZ/EXE/COLLECT are injected by PyInstaller.
"""PyInstaller spec for the Windows desktop build.

Build:  python -m PyInstaller --noconfirm --clean PA_Agent.spec
Output: dist/PA_Agent/  (folder build; user data is written next to the .exe)
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()

# Read-only assets.  prompt_engineering/*.txt is the whole prompt library and
# is loaded by PromptAssembler at runtime; dark.qss is the Qt stylesheet and
# qclaw_relay.py is the reasoning-relay helper that is spawned as a script.
datas = [
    (str(ROOT / "prompt_engineering"), "prompt_engineering"),
    (str(ROOT / "pa_agent" / "gui" / "theme" / "dark.qss"), "pa_agent/gui/theme"),
    (str(ROOT / "pa_agent" / "ai" / "qclaw_relay.py"), "pa_agent/ai"),
    (str(ROOT / "config" / "settings.example.json"), "config"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "PA_Agent使用文档.md"), "."),
    (str(ROOT / "LICENSE"), "."),
]

# Data sources are imported lazily inside factory functions, and the optional
# providers are wrapped in try/except; collect the package wholesale so a
# lazily imported module can never be missing at runtime.
hiddenimports = collect_submodules("pa_agent")

block_cipher = None

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Two Qt bindings in one frozen app abort the build: something in the
        # optional data-source stack imports PyQt5/PySide, which must never be
        # collected alongside PyQt6 (the app is PyQt6-only).
        "PyQt5",
        "PySide2",
        "PySide6",
        "shiboken2",
        "shiboken6",
        "pytest",
        "_pytest",
        "hypothesis",
        "tests",
        # scipy (pulled in by the optional indicator stack) imports dask and,
        # under its conftest, torch.  None of it is on any runtime path here,
        # and collecting them turns a ~200 MB build into >1 GB.
        "dask",
        "distributed",
        "torch",
        "numba",
        "llvmlite",
        "sphinx",
        "zmq",
        # Heavy scientific/plotting stacks that live in the build environment
        # (pulled in by the anaconda base image) but are never imported by this
        # app or by akshare/baostock/yfinance at runtime.  Verified with
        # "import pa_agent.app_context; import pa_agent.gui.main_window" ->
        # none of them appear in sys.modules.  Together they were ~730 MB of
        # a 980 MB build.
        "plotly",
        "panel",
        "playwright",
        "sklearn",
        "scikit_learn",
        "skimage",
        "statsmodels",
        "botocore",
        "boto3",
        "tables",
        "h5py",
        "polars",
        "polars_runtime_32",
        "altair",
        "nbconvert",
        "nbformat",
        "docutils",
        "mpi4py",
        "patsy",
        "IPython",
        "notebook",
        "jupyter",
        "matplotlib.tests",
        "numpy.tests",
        "pandas.tests",
        "scipy.tests",
        "tkinter",
        "IPython",
        "jupyter",
        "notebook",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.QtQuick",
        "PyQt6.QtQml",
        "PyQt6.Qt3DCore",
        "PyQt6.QtMultimedia",
        "PyQt6.QtBluetooth",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PA_Agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PA_Agent",
)

# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

PROJECT_ROOT = Path(r"X:\Projects\ActiveProjects\OmniCore")

datas = []
binaries = []
hiddenimports = [
    "langchain_core",
    "langchain_groq",
    "langchain_google_genai",
    "langchain_community",
    "google.genai",
    "psutil",
    "mss",
    "pyautogui",
    "PIL",
    "httpx",
    "chromadb",
    "apscheduler",
    "edge_tts",
    "speech_recognition",
    "pyreadline3",
    "wcwidth",
    "anyio",
    "dotenv",
    "sounddevice",
    "ctypes",
    "ctypes.wintypes",
    "email",
    "email.mime",
    "sqlite3",
]

# Dynamically collect all modules inside tools/
tools_dir = PROJECT_ROOT / "tools"
for py_file in tools_dir.glob("*.py"):
    mod_name = py_file.stem
    if not mod_name.startswith("__"):
        hiddenimports.append(f"tools.{mod_name}")

# Include package submodules for all internal packages
for pkg in ["config", "core", "interfaces", "memory", "models", "scheduler", "tools"]:
    try:
        hiddenimports.extend(collect_submodules(pkg))
    except Exception:
        pass
    pkg_path = PROJECT_ROOT / pkg
    if pkg_path.exists():
        datas.append((str(pkg_path), pkg))

# Comprehensive collection of 3rd party packages with data and submodules
packages_to_collect = [
    "pydantic",
    "pydantic_settings",
    "pydantic_core",
    "prompt_toolkit",
    "pyfiglet",
    "structlog",
    "fastapi",
    "uvicorn",
    "starlette",
    "chromadb",
    "posthog",
    "apscheduler",
    "langchain_core",
    "langchain_groq",
    "langchain_google_genai",
    "imageio",
]

for pkg in packages_to_collect:
    try:
        d, b, h = collect_all(pkg)
        datas.extend(d)
        binaries.extend(b)
        hiddenimports.extend(h)
    except Exception as e:
        print(f"Warning: collect_all({pkg}) error: {e}")

# Copy metadata
metadata_packages = [
    "omnicore",
    "pydantic",
    "pydantic-settings",
    "pydantic-core",
    "prompt-toolkit",
    "pyfiglet",
    "fastapi",
    "uvicorn",
    "starlette",
    "structlog",
    "imageio",
    "imageio-ffmpeg",
]
for meta in metadata_packages:
    try:
        datas.extend(copy_metadata(meta))
    except Exception:
        pass

# Deduplicate hidden imports
hiddenimports = sorted(list(set(hiddenimports)))

a = Analysis(
    [str(PROJECT_ROOT / "scripts" / "run.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
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
    name='OmniCore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

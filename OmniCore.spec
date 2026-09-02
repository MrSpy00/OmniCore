# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['X:\\Projects\\ActiveProjects\\OmniCore\\scripts\\run.py'],
    pathex=['X:\\Projects\\ActiveProjects\\OmniCore'],
    binaries=[],
    datas=[],
    hiddenimports=['langchain_core', 'langchain_groq', 'langchain_google_genai', 'langchain_community', 'pydantic', 'pydantic_settings', 'structlog', 'psutil', 'mss', 'pyautogui', 'google.genai', 'PIL', 'fastapi', 'uvicorn', 'httpx', 'chromadb', 'apscheduler'],
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
    name='OmniCore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

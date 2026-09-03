"""Build script for creating OmniCore EXE with PyInstaller.

Usage:
    uv run python build.py

    Or with options:
    uv run python build.py --onefile --console
    uv run python build.py --onedir --console --name OmniCore
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def build(
    onefile: bool = True,
    console: bool = True,
    name: str = "OmniCore",
    icon: str | None = None,
    use_spec: bool = True,
) -> None:
    """Build the OmniCore EXE using PyInstaller."""
    spec_path = PROJECT_ROOT / "OmniCore.spec"
    if use_spec and spec_path.exists():
        args = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec_path),
        ]
    else:
        args = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            f"--name={name}",
            f"--distpath={DIST_DIR}",
            f"--workpath={BUILD_DIR}",
        ]

        if onefile:
            args.append("--onefile")
        else:
            args.append("--onedir")

        if console:
            args.append("--console")
        else:
            args.append("--windowed")

        if icon and Path(icon).exists():
            args.append(f"--icon={icon}")

        # Hidden imports that PyInstaller might miss
        hidden = [
            "langchain_core",
            "langchain_groq",
            "langchain_google_genai",
            "langchain_community",
            "pydantic",
            "pydantic_settings",
            "structlog",
            "psutil",
            "mss",
            "pyautogui",
            "google.genai",
            "PIL",
            "fastapi",
            "uvicorn",
            "httpx",
            "chromadb",
            "apscheduler",
        ]
        for h in hidden:
            args.append(f"--hidden-import={h}")

        # Collect all project data
        args.append(f"--paths={PROJECT_ROOT}")

        # Entry point
        args.append(str(PROJECT_ROOT / "scripts" / "run.py"))

    print(f"Building {name}...")
    print(f"Command: {' '.join(args)}")
    print()

    result = subprocess.run(args, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        exe_path = DIST_DIR / (name + ".exe")
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print("\nBuild successful!")
            print(f"EXE: {exe_path}")
            print(f"Size: {size_mb:.1f} MB")
        else:
            print(f"\nBuild completed but EXE not found at {exe_path}")
    else:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build OmniCore EXE")
    parser.add_argument("--onefile", action="store_true", default=True,
                        help="Create single EXE file (default)")
    parser.add_argument("--onedir", action="store_true",
                        help="Create directory with EXE + deps")
    parser.add_argument("--console", action="store_true", default=True,
                        help="Show console window (default)")
    parser.add_argument("--windowed", action="store_true",
                        help="Hide console window")
    parser.add_argument("--name", default="OmniCore",
                        help="EXE filename (default: OmniCore)")
    parser.add_argument("--icon", help="Icon file path (.ico)")
    args = parser.parse_args()

    build(
        onefile=not args.onedir,
        console=not args.windowed,
        name=args.name,
        icon=args.icon,
    )

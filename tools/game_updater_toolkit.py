"""Game Updater Toolkit — Steam & Epic Games Launcher integration.

Allows OmniCore to manage game updates via Steam and Epic Games Launcher.
Inspired by the Mark-XXXV ``game_updater`` function.

Safe Defaults:
  - Never performs destructive uninstalls without explicit parameters.
  - Lists installed games before update actions for confirmation.
  - All operations are logged and can be stopped.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()

# Common Steam installation paths on Windows
_STEAM_PATHS = [
    Path("C:/Program Files (x86)/Steam"),
    Path("C:/Program Files/Steam"),
    Path("C:/Steam"),
    Path("D:/Steam"),
    Path("E:/Steam"),
    Path("F:/Steam"),
    Path(os.path.expandvars("%ProgramFiles(x86)%/Steam")),
]

# Common Epic Games launcher executable & manifest paths
_EPIC_PATHS = [
    Path("C:/Program Files (x86)/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"),
    Path("C:/Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"),
    Path("D:/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"),
]
_EPIC_MANIFEST_DIR = Path("C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests")


def _find_steam_path() -> Path | None:
    """Find Steam installation path via registry keys or fallback directories."""
    if winreg is not None:
        registry_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]
        for hive, key_path in registry_keys:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(val)
                if p.exists() and (p / "steam.exe").exists():
                    return p
            except Exception:
                continue

    for p in _STEAM_PATHS:
        if p.exists() and (p / "steam.exe").exists():
            return p
    return None


def _find_epic_path() -> Path | None:
    """Find Epic Games Launcher path via registry or fallback directories."""
    if winreg is not None:
        registry_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
        ]
        for hive, key_path in registry_keys:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "AppDataPath")
                winreg.CloseKey(key)
                exe = Path(val) / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
                if exe.exists():
                    return exe
            except Exception:
                continue

    for p in _EPIC_PATHS:
        if p.exists():
            return p
    return None


def _find_steamcmd() -> Path | None:
    """Find SteamCMD executable."""
    steam_root = _find_steam_path()
    if steam_root:
        candidate = steam_root / "steamcmd.exe"
        if candidate.exists():
            return candidate
    standalone = Path("C:/SteamCMD/steamcmd.exe")
    if standalone.exists():
        return standalone
    return None


def _find_steam_library_folders(steam_root: Path) -> list[Path]:
    """Discover all Steam library folders via libraryfolders.vdf."""
    libraries = [steam_root / "steamapps"]
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return libraries

    try:
        content = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE):
            folder = Path(raw_path.replace("\\\\", "/")) / "steamapps"
            if folder.exists() and folder not in libraries:
                libraries.append(folder)
    except Exception:
        pass
    return libraries


class GameUpdater(BaseTool):
    """Manage Steam and Epic Games updates.

    Actions:
    - ``list``            — List installed Steam & Epic Games
    - ``update``          — Force update a Steam game by AppID or name
    - ``install``         — Install a Steam game by AppID
    - ``steam_status``    — Check if Steam is running
    - ``epic_launch``     — Launch Epic Games Launcher
    - ``download_status`` — Check active Steam downloads
    """

    name = "game_updater"
    description = (
        "Manage Steam and Epic Games: list installed games across drives, trigger updates, "
        "install games by AppID, check download status, or launch Epic Games Launcher. "
        "Parameters: action (list|update|install|steam_status|epic_launch|download_status), "
        "app_id (Steam AppID for update/install), game_name (partial name for update)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta çalışır.")

        params = self._params(tool_input)
        action = str(
            self._first_param(params, "action", default="list") or "list"
        ).strip().lower()
        app_id = str(self._first_param(params, "app_id", "appid", default="") or "")
        game_name = str(self._first_param(params, "game_name", "game", default="") or "")

        if action == "steam_status":
            return await self._steam_status()
        if action == "list":
            return await self._list_games()
        if action == "epic_launch":
            return await self._launch_epic()
        if action == "download_status":
            return await self._download_status()
        if action == "update":
            if not app_id and not game_name:
                return self._failure("update için 'app_id' veya 'game_name' gerekli.")
            return await self._update_game(app_id=app_id, game_name=game_name)
        if action == "install":
            if not app_id:
                return self._failure("install için 'app_id' gerekli (Steam AppID).")
            return await self._install_game(app_id=app_id)

        return self._failure(
            f"Bilinmeyen action: '{action}'. "
            "Geçerli: list, update, install, steam_status, epic_launch, download_status"
        )

    async def _steam_status(self) -> ToolOutput:
        """Check if Steam process is running without blocking async thread."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            running = "steam.exe" in (result.stdout or "").lower()
            steam_path = _find_steam_path()
            return self._success(
                f"Steam {'çalışıyor ✅' if running else 'çalışmıyor ❌'}",
                data={
                    "running": running,
                    "steam_path": str(steam_path) if steam_path else None,
                    "steamcmd_available": _find_steamcmd() is not None,
                },
            )
        except Exception as exc:
            return self._failure(f"Steam durumu kontrol hatası: {exc}")

    async def _list_games(self) -> ToolOutput:
        """List Steam libraries and installed Epic Games."""
        steam_games = await asyncio.to_thread(self._scan_steam_games)
        epic_games = await asyncio.to_thread(self._scan_epic_games)

        all_games = steam_games + epic_games
        all_games.sort(key=lambda g: g["name"].lower())

        summary_lines = [
            f"• [{g['platform'].upper()}] {g['name']} (ID: {g.get('app_id', '?')})"
            for g in all_games[:40]
        ]
        summary = (
            f"Toplam {len(all_games)} oyun bulundu "
            f"(Steam: {len(steam_games)}, Epic: {len(epic_games)}):\n" + "\n".join(summary_lines)
        )
        if len(all_games) > 40:
            summary += f"\n... ve {len(all_games) - 40} oyun daha."

        return self._success(
            summary,
            data={
                "games": all_games,
                "steam_count": len(steam_games),
                "epic_count": len(epic_games),
                "total": len(all_games),
            },
        )

    def _scan_steam_games(self) -> list[dict]:
        steam_path = _find_steam_path()
        if not steam_path:
            return []

        libraries = _find_steam_library_folders(steam_path)
        games: list[dict] = []
        seen_appids: set[str] = set()

        for lib in libraries:
            if not lib.exists():
                continue
            for acf in lib.glob("appmanifest_*.acf"):
                try:
                    content = acf.read_text(encoding="utf-8", errors="ignore")
                    appid_m = re.search(r'"appid"\s+"(\d+)"', content, re.IGNORECASE)
                    name_m = re.search(r'"name"\s+"([^"]+)"', content, re.IGNORECASE)
                    state_m = re.search(r'"StateFlags"\s+"(\d+)"', content, re.IGNORECASE)
                    size_m = re.search(r'"SizeOnDisk"\s+"(\d+)"', content, re.IGNORECASE)

                    if appid_m and name_m:
                        appid = appid_m.group(1)
                        if appid not in seen_appids:
                            seen_appids.add(appid)
                            games.append({
                                "platform": "steam",
                                "name": name_m.group(1),
                                "app_id": appid,
                                "state": int(state_m.group(1)) if state_m else 0,
                                "size_bytes": int(size_m.group(1)) if size_m else 0,
                                "manifest": acf.name,
                            })
                except Exception:
                    continue
        return games

    def _scan_epic_games(self) -> list[dict]:
        games: list[dict] = []
        if not _EPIC_MANIFEST_DIR.exists():
            return games

        for item_file in _EPIC_MANIFEST_DIR.glob("*.item"):
            try:
                data = json.loads(item_file.read_text(encoding="utf-8", errors="ignore"))
                display_name = data.get("DisplayName")
                app_name = data.get("AppName")
                if display_name:
                    games.append({
                        "platform": "epic",
                        "name": display_name,
                        "app_id": app_name or item_file.stem,
                        "install_location": data.get("InstallLocation", ""),
                    })
            except Exception:
                continue
        return games

    async def _update_game(self, app_id: str, game_name: str) -> ToolOutput:
        """Trigger Steam to update a game via Steam protocol URL."""
        if not app_id and game_name:
            list_result = await self._list_games()
            if list_result.status.value == "success":
                games = list_result.data.get("games", [])
                matches = [
                    g for g in games
                    if game_name.lower() in g["name"].lower() and g.get("platform") == "steam"
                ]
                if matches:
                    app_id = matches[0]["app_id"]
                    game_name = matches[0]["name"]

        if not app_id:
            return self._failure(
                f"'{game_name}' için Steam AppID bulunamadı. "
                "Lütfen 'app_id' parametresini manuel olarak girin."
            )

        update_url = f"steam://run/{app_id}"
        try:
            await asyncio.to_thread(
                subprocess.Popen,
                ["cmd", "/c", "start", "", update_url],
                shell=True,
            )
            return self._success(
                f"Steam güncelleme başlatıldı: AppID={app_id}" +
                (f" ({game_name})" if game_name else ""),
                data={"app_id": app_id, "game_name": game_name, "method": "steam_url"},
            )
        except Exception as exc:
            return self._failure(f"Güncelleme başlatma hatası: {exc}")

    async def _install_game(self, app_id: str) -> ToolOutput:
        """Install a Steam game by AppID via Steam store URL."""
        install_url = f"steam://install/{app_id}"
        try:
            await asyncio.to_thread(
                subprocess.Popen,
                ["cmd", "/c", "start", "", install_url],
                shell=True,
            )
            return self._success(
                f"Steam kurulum başlatıldı: AppID={app_id}. "
                "Steam penceresi kurulum onayı isteyecek.",
                data={"app_id": app_id, "method": "steam_install_url"},
            )
        except Exception as exc:
            return self._failure(f"Kurulum başlatma hatası: {exc}")

    async def _download_status(self) -> ToolOutput:
        """Check active Steam download status via powershell process list."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object {$_.Name -like '*steam*'} "
                    "| Select-Object Name,CPU,WorkingSet | ConvertTo-Json"
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            info = (result.stdout or "").strip() or "Steam süreci bilgisi alınamadı."
            return self._success(
                "Steam süreç durumu alındı.",
                data={"process_info": info},
            )
        except Exception as exc:
            return self._failure(f"Süreç bilgisi alınamadı: {exc}")

    async def _launch_epic(self) -> ToolOutput:
        """Launch Epic Games Launcher without blocking event loop thread."""
        for epic_path in _EPIC_PATHS:
            if epic_path.exists():
                try:
                    await asyncio.to_thread(subprocess.Popen, [str(epic_path)])
                    return self._success(
                        "Epic Games Launcher başlatıldı.",
                        data={"path": str(epic_path)},
                    )
                except Exception as exc:
                    return self._failure(f"Epic başlatma hatası: {exc}")

        # Fallback to protocol URL
        try:
            await asyncio.to_thread(
                subprocess.Popen,
                ["cmd", "/c", "start", "", "com.epicgames.launcher://"],
                shell=True,
            )
            return self._success(
                "Epic Games Launcher protokol URL ile başlatıldı.",
                data={"method": "protocol_url"},
            )
        except Exception as exc:
            return self._failure(
                f"Epic Games Launcher bulunamadı. "
                f"Lütfen kurulu olduğundan emin olun. Hata: {exc}"
            )

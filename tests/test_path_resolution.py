from __future__ import annotations

import tools.base as base_mod
from tools.base import resolve_user_path


def test_resolve_user_path_maps_relative_paths_to_userprofile(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        base_mod,
        "_windows_special_folders",
        lambda: {
            "desktop": (tmp_path / "Desktop").resolve(),
            "documents": (tmp_path / "Documents").resolve(),
            "downloads": (tmp_path / "Downloads").resolve(),
        },
    )

    resolved, is_cross = resolve_user_path("Desktop/file.txt")

    assert resolved == (tmp_path / "Desktop" / "file.txt").resolve()
    assert is_cross is False


def test_resolve_user_path_replaces_placeholder_username(monkeypatch, tmp_path):
    home = tmp_path / "mrSpy"
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(
        base_mod,
        "_windows_special_folders",
        lambda: {
            "desktop": (home / "Desktop").resolve(),
            "documents": (home / "Documents").resolve(),
            "downloads": (home / "Downloads").resolve(),
        },
    )

    resolved, is_cross = resolve_user_path(r"C:\Users\<Username>\Desktop")

    assert resolved == (home / "Desktop").resolve()
    assert is_cross is False


def test_resolve_user_path_allows_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    absolute = tmp_path / "outside" / "note.txt"

    resolved, is_cross = resolve_user_path(str(absolute))

    assert resolved == absolute.resolve()
    assert is_cross is False

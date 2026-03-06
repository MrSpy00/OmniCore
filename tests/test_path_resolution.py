from __future__ import annotations

from pathlib import Path

from tools.base import resolve_user_path


def test_resolve_user_path_maps_relative_paths_to_userprofile(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    resolved, is_cross = resolve_user_path("Desktop/file.txt")

    assert resolved == (tmp_path / "Desktop" / "file.txt").resolve()
    assert is_cross is False


def test_resolve_user_path_replaces_placeholder_username(monkeypatch, tmp_path):
    home = tmp_path / "mrSpy"
    monkeypatch.setenv("USERPROFILE", str(home))

    resolved, is_cross = resolve_user_path(r"C:\Users\<Username>\Desktop")

    assert resolved == (home / "Desktop").resolve()
    assert is_cross is False


def test_resolve_user_path_allows_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    absolute = tmp_path / "outside" / "note.txt"

    resolved, is_cross = resolve_user_path(str(absolute))

    assert resolved == absolute.resolve()
    assert is_cross is False

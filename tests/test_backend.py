"""WSL path translation and the Backend argv builder."""

import pytest

from luna_tpx3_gui.functions.backend import Backend, detect_backend, drive_letter, win_to_wsl


def test_win_to_wsl():
    assert win_to_wsl(r"C:\Users\me\data x\a.tpx3") == "/mnt/c/Users/me/data x/a.tpx3"
    assert win_to_wsl("D:/tpx3cam data") == "/mnt/d/tpx3cam data"
    assert win_to_wsl("/already/posix") == "/already/posix"


def test_win_to_wsl_rejects_unc():
    with pytest.raises(ValueError):
        win_to_wsl(r"\\server\share\file.tpx3")


def test_drive_letter():
    assert drive_letter(r"E:\data") == "e"
    assert drive_letter("/mnt/e") == ""


def test_backend_argv():
    wsl = Backend("wsl", "/mnt/c/luna/bin/tpx3dump")
    assert wsl.argv(["--version"]) == ["wsl.exe", "-e", "/mnt/c/luna/bin/tpx3dump", "--version"]
    assert wsl.translate(r"C:\a\b.tpx3") == "/mnt/c/a/b.tpx3"
    assert wsl.usable

    native = Backend("native", "/opt/luna/bin/tpx3dump")
    assert native.argv(["process"]) == ["/opt/luna/bin/tpx3dump", "process"]
    assert native.translate("/x/y") == "/x/y"
    assert not Backend().usable


def test_detect_backend_reports_problems(tmp_path):
    assert not detect_backend("").usable
    assert not detect_backend(str(tmp_path / "missing")).usable
    empty = detect_backend(str(tmp_path))
    assert not empty.usable
    assert "No tpx3dump" in empty.detail

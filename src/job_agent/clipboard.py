from __future__ import annotations

import subprocess
import sys


class ClipboardError(RuntimeError):
    pass


def read_clipboard_text() -> str:
    if sys.platform == "win32":
        text = _read_windows_clipboard()
    else:
        text = _read_tkinter_clipboard()

    text = _clean_clipboard_text(text)
    if not text:
        raise ClipboardError("Буфер обмена пустой или в нём нет текста.")
    return text


def _read_windows_clipboard() -> str:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); Get-Clipboard -Raw",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ClipboardError(f"Не удалось прочитать буфер обмена: {error}") from error

    return result.stdout.decode("utf-8", errors="replace")


def _read_tkinter_clipboard() -> str:
    try:
        import tkinter
    except ImportError as error:
        raise ClipboardError("Чтение буфера обмена недоступно в этой среде.") from error

    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tkinter.TclError as error:
        raise ClipboardError(f"Не удалось прочитать буфер обмена: {error}") from error
    finally:
        root.destroy()


def _clean_clipboard_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()

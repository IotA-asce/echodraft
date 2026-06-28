from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


WINDOWS_PACKAGE_DIRS: dict[str, tuple[str, ...]] = {
    "pdftoppm": ("oschwartz10612.Poppler",),
    "tesseract": ("UB-Mannheim.TesseractOCR",),
}


def resolve_system_tool(command: str) -> str | None:
    executable = shutil.which(command)
    if executable:
        return executable
    if platform.system() != "Windows":
        return None
    return _resolve_windows_tool(command)


def _resolve_windows_tool(command: str) -> str | None:
    executable_name = command if command.lower().endswith(".exe") else f"{command}.exe"
    for candidate in _windows_tool_candidates(command, executable_name):
        if candidate.is_file():
            return str(candidate)
    return None


def _windows_tool_candidates(command: str, executable_name: str) -> list[Path]:
    candidates: list[Path] = []
    program_roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    existing_roots = [Path(root) for root in program_roots if root]

    if command == "tesseract":
        candidates.extend(root / "Tesseract-OCR" / executable_name for root in existing_roots)

    if command == "pdftoppm":
        for root in existing_roots:
            candidates.extend(root.glob("poppler*/Library/bin/pdftoppm.exe"))
            candidates.extend(root.glob("poppler*/bin/pdftoppm.exe"))

    candidates.extend(_winget_package_candidates(command, executable_name))
    return candidates


def _winget_package_candidates(command: str, executable_name: str) -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not package_root.is_dir():
        return []

    candidates: list[Path] = []
    for package_prefix in WINDOWS_PACKAGE_DIRS.get(command, ()):
        for package_dir in package_root.glob(f"{package_prefix}*"):
            if package_dir.is_dir():
                candidates.extend(package_dir.rglob(executable_name))
    return candidates

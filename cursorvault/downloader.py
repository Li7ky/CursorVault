"""光标包下载与解压模块.

支持从致美化下载 .rar/.zip 光标包并自动解压，
提取 .cur/.ani 文件，映射到标准游标类型。

解压依赖:
    - .zip: Python 内置 zipfile
    - .rar: 优先 rarfile 库 (需安装 unrar.exe)，回退到 7z / WinRAR
"""

from __future__ import annotations

import shutil
import zipfile
import subprocess
from pathlib import Path
from typing import Optional

from .models import CursorType


# 游标文件名 -> CursorType 的映射规则
# 致美化光标包的文件命名有一定规律
CURSOR_FILE_PATTERNS: list[tuple[CursorType, list[str]]] = [
    (CursorType.UPARROW,     ["uparrow", "cur14", "14"]),
    (CursorType.HAND,        ["pointerlink", "hand", "link", "cur15", "15"]),
    (CursorType.ARROW,       ["arrow", "normal", "select", "pointer", "default", "cur01", "01"]),
    (CursorType.HELP,        ["help", "cur02", "02"]),
    (CursorType.APPSTARTING, ["appstarting", "app_starting", "working", "cur03", "03"]),
    (CursorType.WAIT,        ["wait", "busy", "loading", "cur04", "04"]),
    (CursorType.CROSSHAIR,   ["crosshair", "cross", "precision", "cur05", "05"]),
    (CursorType.IBEAM,       ["ibeam", "text", "cur06", "06"]),
    (CursorType.PEN,         ["pen", "nwpen", "handwriting", "cur07", "07"]),
    (CursorType.NO,          ["no", "unavailable", "cur08", "08"]),
    (CursorType.SIZEALL,     ["sizeall", "move", "cur09", "09"]),
    (CursorType.SIZENESW,    ["sizenesw", "nesw", "cur10", "10"]),
    (CursorType.SIZENS,      ["sizens", "ns", "vertical", "cur11", "11"]),
    (CursorType.SIZENWSE,    ["sizenwse", "nwse", "diagonal", "cur12", "12"]),
    (CursorType.SIZEWE,      ["sizewe", "we", "horizontal", "ew", "cur13", "13"]),
]


def find_cursor_files(directory: Path) -> list[Path]:
    """递归查找目录中的所有 .cur 和 .ani 文件."""
    files = []
    for ext in ("*.cur", "*.ani", "*.CUR", "*.ANI"):
        files.extend(directory.rglob(ext))
    # 去重
    seen = set()
    result = []
    for f in files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(f)
    return result


def match_cursor_type(filename: str) -> Optional[CursorType]:
    """根据文件名匹配游标类型.

    尝试多种命名规则:
    1. 文件名包含 arrow/help/wait 等关键词
    2. 文件名包含数字编号 01-15
    3. Windows 标准名称 (如 aero_arrow.cur)
    """
    name = filename.lower().replace(" ", "").replace("_", "").replace("-", "")

    # Windows' standard names are exact identifiers; check these before the
    # broader substring rules below.
    win_names = {
        "aeroarrow": CursorType.ARROW,
        "aerohelpsel": CursorType.HELP,
        "aeroworking": CursorType.APPSTARTING,
        "aerobusy": CursorType.WAIT,
        "aerocross": CursorType.CROSSHAIR,
        "aeroibeam": CursorType.IBEAM,
        "aeropen": CursorType.PEN,
        "aerounavail": CursorType.NO,
        "aeromove": CursorType.SIZEALL,
        "aeroup": CursorType.UPARROW,
        "aerolink": CursorType.HAND,
        "aeronesw": CursorType.SIZENESW,
        "aerons": CursorType.SIZENS,
        "aeronwse": CursorType.SIZENWSE,
        "aeroew": CursorType.SIZEWE,
    }
    for win_name, ct in win_names.items():
        if win_name in name:
            return ct

    for cursor_type, keywords in CURSOR_FILE_PATTERNS:
        for kw in keywords:
            if kw in name:
                return cursor_type

    return None


def build_cursor_map(cursor_files: list[Path]) -> dict[CursorType, Path]:
    """将光标文件列表映射到 CursorType.

    优先匹配文件名最明确的文件。
    """
    result: dict[CursorType, Path] = {}
    # 按文件名长度排序，更具体的名字优先
    sorted_files = sorted(cursor_files, key=lambda f: len(f.stem))

    for f in sorted_files:
        ct = match_cursor_type(f.name)
        if ct and ct not in result:
            result[ct] = f

    return result


def _find_extractor(name: str) -> Optional[str]:
    """查找解压工具，优先 PATH 中的，其次项目自带的."""
    # 先查 PATH
    path = shutil.which(name)
    if path:
        return path
    # 查项目自带的 bin 目录
    bin_dir = Path(__file__).resolve().parent / "bin"
    candidates = [
        bin_dir / f"{name}.exe",
        bin_dir / name,
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _safe_member_path(dest_dir: Path, member_name: str) -> bool:
    """Reject archive members that would escape the extraction directory."""
    normalized = member_name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/")[0]:
        return False
    try:
        return (dest_dir / normalized).resolve().is_relative_to(dest_dir.resolve())
    except OSError:
        return False


def extract_archive(archive_path: Path, dest_dir: Path) -> bool:
    """解压压缩包到目标目录.

    支持 .zip 和 .rar 格式。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()

    if suffix == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                if not all(_safe_member_path(dest_dir, info.filename) for info in zf.infolist()):
                    return False
                zf.extractall(dest_dir)
            return True
        except (zipfile.BadZipFile, Exception):
            return False

    if suffix == ".rar":
        # 方案 1: 尝试 rarfile 库 (需要 unrar)
        try:
            import rarfile
            # 设置 unrar 路径
            unrar = _find_extractor("unrar")
            if unrar:
                rarfile.UNRAR_TOOL = unrar
            rf = rarfile.RarFile(str(archive_path))
            if not all(_safe_member_path(dest_dir, info.filename) for info in rf.infolist()):
                return False
            rf.extractall(str(dest_dir))
            return True
        except ImportError:
            pass
        except Exception:
            pass

        # 方案 2: use the command line extractor only after validating member paths.
        unrar = _find_extractor("unrar")
        if unrar:
            try:
                import rarfile
                rf = rarfile.RarFile(str(archive_path))
                if not all(_safe_member_path(dest_dir, info.filename) for info in rf.infolist()):
                    return False
                result = subprocess.run(
                    [unrar, "x", "-y", str(archive_path), str(dest_dir) + "\\"],
                    capture_output=True, timeout=120,
                )
                return result.returncode == 0
            except Exception:
                pass

        return False

    if suffix == ".7z":
        # 方案 1: py7zr 库 (纯 Python)
        try:
            import py7zr
            with py7zr.SevenZipFile(str(archive_path), mode="r") as z:
                if not all(_safe_member_path(dest_dir, info.filename) for info in z.list()):
                    return False
                z.extractall(str(dest_dir))
            return True
        except (ImportError, Exception):
            pass

    return False


def install_pack_from_archive(
    archive_path: Path,
    theme_dir: Path,
    theme_name: str = "",
) -> dict[CursorType, Path]:
    """从压缩包安装光标主题.

    1. 解压到临时目录
    2. 查找所有 .cur/.ani 文件
    3. 映射到标准游标类型
    4. 复制到主题目录 (以 cursor_type.value.cur 命名)

    Returns:
        {CursorType: Path} 映射表
    """
    # 解压到临时目录
    extract_dir = theme_dir / ".extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)

    if not extract_archive(archive_path, extract_dir):
        return {}

    # 查找光标文件
    cursor_files = find_cursor_files(extract_dir)
    if not cursor_files:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return {}

    # 映射游标类型
    cursor_map = build_cursor_map(cursor_files)

    # 复制到主题目录，使用标准命名
    theme_dir.mkdir(parents=True, exist_ok=True)
    installed: dict[CursorType, Path] = {}

    for ct, src_path in cursor_map.items():
        suffix = src_path.suffix.lower()
        dst = theme_dir / f"{ct.value}{suffix}"
        try:
            shutil.copy2(src_path, dst)
            alternate = theme_dir / f"{ct.value}{'.ani' if suffix == '.cur' else '.cur'}"
            alternate.unlink(missing_ok=True)
            installed[ct] = dst
        except Exception:
            pass

    # 复制预览图（如果有）
    for img_name in ("preview", "preview.png", "preview.jpg"):
        for img_path in extract_dir.rglob(img_name + "*"):
            if img_path.is_file():
                try:
                    shutil.copy2(img_path, theme_dir / "preview.png")
                except Exception:
                    pass
                break

    # 清理临时目录
    shutil.rmtree(extract_dir, ignore_errors=True)

    return installed

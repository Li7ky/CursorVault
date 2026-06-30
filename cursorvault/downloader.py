"""光标包下载与解压模块.

支持下载 .rar/.zip/.7z 光标包并自动解压，
提取 .cur/.ani 文件，映射到标准游标类型。
兼容中文 Windows 命名与方案 .inf 映射。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import CursorType


@dataclass
class InstallResult:
    """安装结果（成功时 files 非空；失败时 error 有说明）."""

    files: dict[CursorType, Path] = field(default_factory=dict)
    error: str = ""
    extracted_count: int = 0
    matched_count: int = 0


# 精确 stem（去分隔符后）映射
EXACT_STEM_MAP: dict[str, CursorType] = {
    "arrow": CursorType.ARROW,
    "normal": CursorType.ARROW,
    "select": CursorType.ARROW,
    "pointer": CursorType.ARROW,
    "default": CursorType.ARROW,
    "normalselect": CursorType.ARROW,
    "help": CursorType.HELP,
    "helpsel": CursorType.HELP,
    "appstarting": CursorType.APPSTARTING,
    "appstart": CursorType.APPSTARTING,
    "working": CursorType.APPSTARTING,
    "workinginbackground": CursorType.APPSTARTING,
    "wait": CursorType.WAIT,
    "busy": CursorType.WAIT,
    "loading": CursorType.WAIT,
    "crosshair": CursorType.CROSSHAIR,
    "cross": CursorType.CROSSHAIR,
    "precision": CursorType.CROSSHAIR,
    "ibeam": CursorType.IBEAM,
    "text": CursorType.IBEAM,
    "textselect": CursorType.IBEAM,
    "pen": CursorType.PEN,
    "nwpen": CursorType.PEN,
    "handwriting": CursorType.PEN,
    "no": CursorType.NO,
    "unavailable": CursorType.NO,
    "unavail": CursorType.NO,
    "forbidden": CursorType.NO,
    "sizeall": CursorType.SIZEALL,
    "move": CursorType.SIZEALL,
    "sizenesw": CursorType.SIZENESW,
    "nesw": CursorType.SIZENESW,
    "sizens": CursorType.SIZENS,
    "ns": CursorType.SIZENS,
    "vertical": CursorType.SIZENS,
    "sizenwse": CursorType.SIZENWSE,
    "nwse": CursorType.SIZENWSE,
    "diagonal": CursorType.SIZENWSE,
    "sizewe": CursorType.SIZEWE,
    "we": CursorType.SIZEWE,
    "ew": CursorType.SIZEWE,
    "horizontal": CursorType.SIZEWE,
    "uparrow": CursorType.UPARROW,
    "up": CursorType.UPARROW,
    "hand": CursorType.HAND,
    "link": CursorType.HAND,
    "pointerlink": CursorType.HAND,
    "linkselect": CursorType.HAND,
}

# Windows Aero 标准名（子串匹配，足够独特）
WIN_NAME_MAP: list[tuple[str, CursorType]] = [
    ("aerohelpsel", CursorType.HELP),
    ("aeroworking", CursorType.APPSTARTING),
    ("aerobusy", CursorType.WAIT),
    ("aerocross", CursorType.CROSSHAIR),
    ("aeroibeam", CursorType.IBEAM),
    ("aeropen", CursorType.PEN),
    ("aerounavail", CursorType.NO),
    ("aeromove", CursorType.SIZEALL),
    ("aeronesw", CursorType.SIZENESW),
    ("aeronwse", CursorType.SIZENWSE),
    ("aerolink", CursorType.HAND),
    ("aeroarrow", CursorType.ARROW),
    ("aerons", CursorType.SIZENS),
    ("aeroew", CursorType.SIZEWE),
    ("aeroup", CursorType.UPARROW),
]

# 长关键词：按长度降序，避免短串误匹配
LONG_KEYWORDS: list[tuple[str, CursorType]] = sorted(
    [
        ("pointerlink", CursorType.HAND),
        ("appstarting", CursorType.APPSTARTING),
        ("handwriting", CursorType.PEN),
        ("unavailable", CursorType.NO),
        ("crosshair", CursorType.CROSSHAIR),
        ("precision", CursorType.CROSSHAIR),
        ("horizontal", CursorType.SIZEWE),
        ("vertical", CursorType.SIZENS),
        ("uparrow", CursorType.UPARROW),
        ("sizeall", CursorType.SIZEALL),
        ("sizenesw", CursorType.SIZENESW),
        ("sizenwse", CursorType.SIZENWSE),
        ("sizewe", CursorType.SIZEWE),
        ("sizens", CursorType.SIZENS),
        ("loading", CursorType.WAIT),
        ("working", CursorType.APPSTARTING),
        ("diagonal", CursorType.SIZENWSE),
        ("default", CursorType.ARROW),
        ("pointer", CursorType.ARROW),
        ("normal", CursorType.ARROW),
        ("select", CursorType.ARROW),
        ("arrow", CursorType.ARROW),
        ("ibeam", CursorType.IBEAM),
        ("nwpen", CursorType.PEN),
        ("busy", CursorType.WAIT),
        ("wait", CursorType.WAIT),
        ("help", CursorType.HELP),
        ("hand", CursorType.HAND),
        ("link", CursorType.HAND),
        ("move", CursorType.SIZEALL),
        ("text", CursorType.IBEAM),
        ("pen", CursorType.PEN),
        ("nesw", CursorType.SIZENESW),
        ("nwse", CursorType.SIZENWSE),
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)

# cur01 / 01 编号映射（仅精确编号，禁止 shadow10 这类误匹配）
NUMBER_MAP: dict[str, CursorType] = {
    "01": CursorType.ARROW,
    "1": CursorType.ARROW,
    "02": CursorType.HELP,
    "2": CursorType.HELP,
    "03": CursorType.APPSTARTING,
    "3": CursorType.APPSTARTING,
    "04": CursorType.WAIT,
    "4": CursorType.WAIT,
    "05": CursorType.CROSSHAIR,
    "5": CursorType.CROSSHAIR,
    "06": CursorType.IBEAM,
    "6": CursorType.IBEAM,
    "07": CursorType.PEN,
    "7": CursorType.PEN,
    "08": CursorType.NO,
    "8": CursorType.NO,
    "09": CursorType.SIZEALL,
    "9": CursorType.SIZEALL,
    "10": CursorType.SIZENESW,
    "11": CursorType.SIZENS,
    "12": CursorType.SIZENWSE,
    "13": CursorType.SIZEWE,
    "14": CursorType.UPARROW,
    "15": CursorType.HAND,
}

_NUM_RE = re.compile(r"^(?:cur)?0*([1-9]\d?)$", re.IGNORECASE)

# 中文 Windows 游标包常见文件名（致美化/主题站大量使用）
ZH_NAME_MAP: dict[str, CursorType] = {
    "正常选择": CursorType.ARROW,
    "标准选择": CursorType.ARROW,
    "普通选择": CursorType.ARROW,
    "默认": CursorType.ARROW,
    "帮助选择": CursorType.HELP,
    "帮助": CursorType.HELP,
    "后台运行": CursorType.APPSTARTING,
    "工作中": CursorType.APPSTARTING,
    "忙": CursorType.WAIT,
    "忙碌": CursorType.WAIT,
    "等待": CursorType.WAIT,
    "精确选择": CursorType.CROSSHAIR,
    "精确定位": CursorType.CROSSHAIR,
    "文本选择": CursorType.IBEAM,
    "文本": CursorType.IBEAM,
    "手写": CursorType.PEN,
    "笔": CursorType.PEN,
    "不可用": CursorType.NO,
    "禁止": CursorType.NO,
    "移动": CursorType.SIZEALL,
    "沿对角线调整大小1": CursorType.SIZENWSE,
    "对角线调整大小1": CursorType.SIZENWSE,
    "对角线调整1": CursorType.SIZENWSE,
    "沿对角线调整大小2": CursorType.SIZENESW,
    "对角线调整大小2": CursorType.SIZENESW,
    "对角线调整2": CursorType.SIZENESW,
    "垂直调整大小": CursorType.SIZENS,
    "垂直调整": CursorType.SIZENS,
    "水平调整大小": CursorType.SIZEWE,
    "水平调整": CursorType.SIZEWE,
    "候选": CursorType.UPARROW,
    "备用选择": CursorType.UPARROW,
    "备选": CursorType.UPARROW,
    "链接选择": CursorType.HAND,
    "链接": CursorType.HAND,
    "手指": CursorType.HAND,
    # 部分包里的扩展命名
    "位置选择": CursorType.CROSSHAIR,
    "个人选择": CursorType.UPARROW,
}

# .inf 注册表值 -> CursorType
INF_REG_TO_TYPE: dict[str, CursorType] = {
    "arrow": CursorType.ARROW,
    "help": CursorType.HELP,
    "appstarting": CursorType.APPSTARTING,
    "wait": CursorType.WAIT,
    "crosshair": CursorType.CROSSHAIR,
    "ibeam": CursorType.IBEAM,
    "nwpen": CursorType.PEN,
    "no": CursorType.NO,
    "sizeall": CursorType.SIZEALL,
    "sizenesw": CursorType.SIZENESW,
    "sizens": CursorType.SIZENS,
    "sizenwse": CursorType.SIZENWSE,
    "sizewe": CursorType.SIZEWE,
    "uparrow": CursorType.UPARROW,
    "hand": CursorType.HAND,
}


def find_cursor_files(directory: Path) -> list[Path]:
    """递归查找目录中的所有 .cur 和 .ani 文件."""
    files: list[Path] = []
    for ext in ("*.cur", "*.ani", "*.CUR", "*.ANI"):
        files.extend(directory.rglob(ext))
    seen: set[Path] = set()
    result: list[Path] = []
    for f in files:
        try:
            resolved = f.resolve()
        except OSError:
            resolved = f
        if resolved not in seen:
            seen.add(resolved)
            result.append(f)
    return result


def _compact_name(filename: str) -> str:
    stem = Path(filename).stem.strip().lower()
    return stem.replace(" ", "").replace("_", "").replace("-", "")


def match_cursor_type(filename: str) -> Optional[CursorType]:
    """根据文件名匹配游标类型（精确优先，支持中文命名）."""
    raw_stem = Path(filename).stem.strip()
    compact = _compact_name(filename)
    if not compact and not raw_stem:
        return None

    # 0) 中文文件名（完整包含关系，长词优先）
    stem_no_space = re.sub(r"\s+", "", raw_stem)
    for zh, ct in sorted(ZH_NAME_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if zh in stem_no_space or zh in raw_stem:
            return ct

    # 1) 完整 stem 精确匹配
    if compact in EXACT_STEM_MAP:
        return EXACT_STEM_MAP[compact]

    # 2) Windows Aero 标准名
    for win_name, ct in WIN_NAME_MAP:
        if win_name in compact:
            return ct

    # 3) 精确编号：仅 cur10 / 10 / cur01，不含 shadow10
    num_match = _NUM_RE.fullmatch(compact)
    if num_match:
        num = num_match.group(1)
        if num in NUMBER_MAP:
            return NUMBER_MAP[num]
        padded = num.zfill(2)
        if padded in NUMBER_MAP:
            return NUMBER_MAP[padded]

    # 4) 长关键词子串（最短 3 字符，已按长度排序）
    for kw, ct in LONG_KEYWORDS:
        if kw in compact:
            return ct

    return None


def parse_scheme_inf(inf_path: Path) -> dict[CursorType, str]:
    """解析游标方案 .inf，返回 {CursorType: 文件名}."""
    text = None
    for enc in ("utf-8-sig", "gbk", "gb2312", "utf-8"):
        try:
            text = inf_path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, OSError):
            continue
    if not text:
        return {}

    # [Strings] 变量 = 文件名
    strings: dict[str, str] = {}
    in_strings = False
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("'"):
            continue
        if s.startswith("[") and s.endswith("]"):
            in_strings = s.lower() == "[strings]"
            continue
        if not in_strings:
            continue
        if "=" in s:
            key, val = s.split("=", 1)
            key = key.strip().lower()
            val = val.strip().strip('"').strip("'")
            if key and val:
                strings[key] = val

    # [Wreg] 或任意行: ...,Arrow,0x..,"%10%\%CUR_DIR%\%pointer%"
    result: dict[CursorType, str] = {}
    for line in text.splitlines():
        if "Control Panel\\Cursors" not in line and "Control Panel/Cursors" not in line:
            continue
        # 拆 CSV 风格
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 4:
            continue
        reg_name = parts[1].strip().strip('"')
        if not reg_name or reg_name in {"", "Schemes"}:
            # 可能是 HKCU,"Control Panel\Cursors",Arrow,...
            # parts[0]=HKCU  parts[1]=path  parts[2]=value name
            if len(parts) >= 3:
                reg_name = parts[2].strip().strip('"')
        ct = INF_REG_TO_TYPE.get(reg_name.lower())
        if not ct:
            continue
        # 取最后一个字段里的 %var% 或文件名
        tail = parts[-1]
        m = re.search(r"%([^%]+)%\s*$", tail.replace("\\", "/").split("/")[-1])
        if m:
            var = m.group(1).lower()
            fname = strings.get(var)
            if fname:
                result[ct] = Path(fname).name
                continue
        # 直接是文件名
        fname = Path(tail.replace("\\", "/").split("/")[-1].strip("%")).name
        if fname.lower().endswith((".cur", ".ani")):
            result[ct] = fname

    # 也从 Strings 里的 pointer/help/... 映射
    alias_to_type = {
        "pointer": CursorType.ARROW,
        "help": CursorType.HELP,
        "work": CursorType.APPSTARTING,
        "working": CursorType.APPSTARTING,
        "busy": CursorType.WAIT,
        "cross": CursorType.CROSSHAIR,
        "text": CursorType.IBEAM,
        "hand": CursorType.PEN,  # 部分 inf 里 hand=手写
        "unavailiable": CursorType.NO,
        "unavailable": CursorType.NO,
        "vert": CursorType.SIZENS,
        "horz": CursorType.SIZEWE,
        "dgn1": CursorType.SIZENWSE,
        "dgn2": CursorType.SIZENESW,
        "move": CursorType.SIZEALL,
        "alternate": CursorType.UPARROW,
        "link": CursorType.HAND,
    }
    for alias, ct in alias_to_type.items():
        if ct in result:
            continue
        fname = strings.get(alias)
        if fname and fname.lower().endswith((".cur", ".ani")):
            result[ct] = Path(fname).name

    return result


def build_cursor_map_from_inf(
    cursor_files: list[Path],
    extract_dir: Path,
) -> dict[CursorType, Path]:
    """优先用 .inf 方案文件建立映射，再回退文件名匹配."""
    by_name: dict[str, Path] = {}
    for f in cursor_files:
        by_name[f.name.lower()] = f
        by_name[f.name] = f

    result: dict[CursorType, Path] = {}
    for inf in extract_dir.rglob("*.inf"):
        mapping = parse_scheme_inf(inf)
        for ct, fname in mapping.items():
            path = by_name.get(fname) or by_name.get(fname.lower())
            if path is None:
                # 宽松：仅比文件名主体
                stem = Path(fname).stem.strip().lower()
                for f in cursor_files:
                    if f.stem.strip().lower() == stem:
                        path = f
                        break
            if path is not None:
                result[ct] = path
        if result:
            break

    # 文件名匹配补全缺失类型
    for f in sorted(cursor_files, key=lambda p: len(p.stem), reverse=True):
        ct = match_cursor_type(f.name)
        if ct and ct not in result:
            result[ct] = f
    return result


def build_cursor_map(cursor_files: list[Path]) -> dict[CursorType, Path]:
    """将光标文件列表映射到 CursorType.

    优先保留文件名更具体（更长 stem）的匹配。
    """
    # 先按 stem 长度降序，具体名优先写入
    ranked = sorted(cursor_files, key=lambda f: len(f.stem), reverse=True)
    result: dict[CursorType, Path] = {}
    for f in ranked:
        ct = match_cursor_type(f.name)
        if ct and ct not in result:
            result[ct] = f
    return result


def _project_roots() -> list[Path]:
    """项目相关搜索根：cursorvault/、仓库根."""
    here = Path(__file__).resolve().parent  # cursorvault/
    return [here, here.parent]


def _find_extractor(name: str) -> Optional[str]:
    """查找解压工具：PATH → 项目目录 → 常见安装路径（含 7-Zip / NVIDIA 自带 7z）."""
    path = shutil.which(name)
    if path:
        return path
    for alt in (name, name.lower(), name.upper(), name.capitalize()):
        path = shutil.which(alt)
        if path:
            return path

    candidates: list[Path] = []
    basenames = {
        "unrar": ["UnRAR.exe", "unrar.exe", "UnRAR", "unrar"],
        "7z": ["7z.exe", "7za.exe", "7z", "7za"],
        "7za": ["7za.exe", "7z.exe", "7za", "7z"],
    }
    names = basenames.get(name.lower(), [f"{name}.exe", name])

    for root in _project_roots():
        for n in names:
            candidates.append(root / "bin" / n)
            candidates.append(root / n)
            candidates.append(root / "cursorvault" / "bin" / n)

    if name.lower() in {"unrar", "winrar"}:
        candidates.extend(
            [
                Path(r"C:\Program Files\WinRAR\UnRAR.exe"),
                Path(r"C:\Program Files (x86)\WinRAR\UnRAR.exe"),
                Path(r"C:\Program Files\WinRAR\WinRAR.exe"),
            ]
        )

    if name.lower() in {"7z", "7za"}:
        candidates.extend(
            [
                Path(r"C:\Program Files\7-Zip\7z.exe"),
                Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
                Path(r"C:\Program Files\NVIDIA Corporation\NVIDIA App\7z.exe"),
                Path(r"C:\Program Files\Bandizip\7z.exe"),
                Path(r"C:\Program Files\PeaZip\res\bin\7z\7z.exe"),
            ]
        )

    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _safe_member_path(dest_dir: Path, member_name: str) -> bool:
    """Reject archive members that would escape the extraction directory."""
    normalized = member_name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/")[0]:
        return False
    if any(part == ".." for part in normalized.split("/")):
        return False
    try:
        return (dest_dir / normalized).resolve().is_relative_to(dest_dir.resolve())
    except OSError:
        return False


def detect_archive_kind(path: Path) -> str:
    """根据文件头识别压缩格式: rar/zip/7z/html/unknown."""
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return "unknown"
    if not head:
        return "empty"
    if head.startswith(b"Rar!"):
        return "rar"
    if head.startswith(b"PK"):
        return "zip"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    stripped = head.lstrip()
    if stripped.startswith((b"<!DOCTYPE", b"<html", b"<HTML", b"{", b"[")):
        return "html"
    # 扩展名兜底
    suf = path.suffix.lower()
    if suf in {".rar", ".zip", ".7z"}:
        return suf[1:]
    return "unknown"


def _run_7z_extract(seven: str, archive_path: Path, dest_dir: Path) -> bool:
    """调用 7z 解压，使用绝对路径，兼容中文路径."""
    archive_path = archive_path.resolve()
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 7z 的 -o 与路径之间不能有空格
    out_switch = f"-o{dest_dir}"
    try:
        result = subprocess.run(
            [seven, "x", out_switch, "-y", "-aoa", str(archive_path)],
            capture_output=True,
            timeout=180,
            cwd=str(dest_dir),
        )
        if result.returncode == 0:
            return True
        # 部分 7z 对 RAR5 返回非 0 但仍解压出文件
        if any(dest_dir.rglob("*")):
            return True
        return False
    except Exception:
        return False


def extract_archive(archive_path: Path, dest_dir: Path) -> bool:
    """解压压缩包到目标目录。支持 .zip / .rar / .7z（按文件头识别）."""
    archive_path = Path(archive_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists() or archive_path.stat().st_size < 16:
        return False

    kind = detect_archive_kind(archive_path)
    if kind in {"html", "empty", "unknown"}:
        return False

    # 优先 7z（本机常有，且可解 rar/zip/7z）
    seven = _find_extractor("7z") or _find_extractor("7za")

    if kind == "zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                if not all(_safe_member_path(dest_dir, info.filename) for info in zf.infolist()):
                    return False
                zf.extractall(dest_dir)
            return True
        except Exception:
            if seven and _run_7z_extract(seven, archive_path, dest_dir):
                return True
            return False

    if kind == "rar":
        # 1) 7z 优先（当前环境已验证可解 RAR5）
        if seven and _run_7z_extract(seven, archive_path, dest_dir):
            return True

        unrar = _find_extractor("unrar")
        try:
            import rarfile

            if unrar:
                rarfile.UNRAR_TOOL = unrar
            rf = rarfile.RarFile(str(archive_path))
            members = rf.infolist()
            if not all(_safe_member_path(dest_dir, info.filename) for info in members):
                return False
            rf.extractall(str(dest_dir))
            return True
        except Exception:
            pass

        if unrar:
            try:
                result = subprocess.run(
                    [unrar, "x", "-y", str(archive_path.resolve()), str(dest_dir.resolve()) + "\\"],
                    capture_output=True,
                    timeout=180,
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    if kind == "7z":
        try:
            import py7zr

            with py7zr.SevenZipFile(str(archive_path), mode="r") as z:
                names = [info.filename for info in z.list()]
                if not all(_safe_member_path(dest_dir, n) for n in names):
                    return False
                z.extractall(str(dest_dir))
            return True
        except Exception:
            pass
        if seven and _run_7z_extract(seven, archive_path, dest_dir):
            return True
        return False

    return False


def install_pack_from_archive(
    archive_path: Path,
    theme_dir: Path,
    theme_name: str = "",
) -> InstallResult:
    """从压缩包安装光标主题到 theme_dir."""
    extract_dir = theme_dir / ".extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)

    kind = detect_archive_kind(archive_path)
    if kind == "html":
        shutil.rmtree(extract_dir, ignore_errors=True)
        return InstallResult(
            error=(
                "下载到的文件是网页而不是压缩包。\n"
                "请换一个素材，或到浏览器打开来源页手动下载后再「导入游标目录」。"
            )
        )
    if kind in {"empty", "unknown"}:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return InstallResult(
            error=(
                f"无法识别文件格式（{archive_path.name}）。\n"
                "可能不是 rar/zip/7z，或下载不完整。"
            )
        )

    if not extract_archive(archive_path, extract_dir):
        shutil.rmtree(extract_dir, ignore_errors=True)
        seven = _find_extractor("7z") or _find_extractor("7za")
        unrar = _find_extractor("unrar")
        if kind == "rar" and not seven and not unrar:
            return InstallResult(
                error=(
                    "无法解压 .rar：未找到 7-Zip / UnRAR。\n"
                    "请安装 7-Zip（https://www.7-zip.org/）后重启本程序再试。"
                )
            )
        tool_hint = f"7z={seven or '无'}, unrar={unrar or '无'}"
        return InstallResult(
            error=(
                f"解压失败（检测到格式：{kind}，{tool_hint}）。\n"
                f"文件：{archive_path.name}\n"
                "请确认已安装 7-Zip，或手动解压后使用「导入游标目录」。"
            )
        )

    # 嵌套压缩包：部分素材包套了两层
    nested = []
    for ext in ("*.rar", "*.zip", "*.7z", "*.RAR", "*.ZIP", "*.7Z"):
        nested.extend(extract_dir.rglob(ext))
    for nest in nested:
        nest_dir = nest.parent / f"_nested_{nest.stem}"
        if extract_archive(nest, nest_dir):
            pass

    cursor_files = find_cursor_files(extract_dir)
    if not cursor_files:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return InstallResult(
            error=(
                "压缩包已解开，但未找到任何 .cur / .ani 文件。\n"
                "该资源可能不是游标包，或需要手动解压后导入。"
            )
        )

    cursor_map = build_cursor_map_from_inf(cursor_files, extract_dir)
    if not cursor_map:
        # 再尝试纯文件名
        cursor_map = build_cursor_map(cursor_files)

    if not cursor_map:
        sample = "、".join(f.name for f in cursor_files[:6])
        more = "…" if len(cursor_files) > 6 else ""
        shutil.rmtree(extract_dir, ignore_errors=True)
        return InstallResult(
            extracted_count=len(cursor_files),
            error=(
                f"找到 {len(cursor_files)} 个光标文件，但无法识别命名规则。\n"
                f"示例：{sample}{more}\n"
                "可手动解压后，用「导入游标目录」安装。"
            ),
        )

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
        except OSError:
            pass

    for pattern in ("preview.png", "preview.jpg", "preview.jpeg", "preview.webp"):
        matches = list(extract_dir.rglob(pattern))
        if matches:
            try:
                shutil.copy2(matches[0], theme_dir / "preview.png")
            except OSError:
                pass
            break

    shutil.rmtree(extract_dir, ignore_errors=True)

    if not installed:
        return InstallResult(
            extracted_count=len(cursor_files),
            matched_count=len(cursor_map),
            error="光标文件复制失败，请检查磁盘权限。",
        )

    return InstallResult(
        files=installed,
        extracted_count=len(cursor_files),
        matched_count=len(installed),
    )

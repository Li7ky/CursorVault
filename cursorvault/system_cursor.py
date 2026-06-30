"""Windows 系统游标 API 封装.

使用 ctypes 调用 Windows API 来替换系统游标。
推荐路径：写 HKCU 注册表 + SPI_SETCURSORS 刷新（即时且持久）。
"""

from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Optional

import winreg

from .models import CursorType, OCR_MAP, REGISTRY_VALUE_MAP


# --- Windows API 常量 ---
SPI_SETCURSORS = 0x0057
SPI_SETCURSOR = 0x005C
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

# 注册表路径
REG_CURSORS_PATH = r"Control Panel\Cursors"
REG_CURSORS_SCHEMES_PATH = r"Control Panel\Cursors\Schemes"


class SystemCursorAPI:
    """Windows 系统游标 API."""

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._user32.SystemParametersInfoW.argtypes = [
            wintypes.UINT,
            wintypes.UINT,
            wintypes.LPVOID,
            wintypes.UINT,
        ]
        self._user32.SystemParametersInfoW.restype = wintypes.BOOL

        self._user32.LoadCursorFromFileW.argtypes = [wintypes.LPCWSTR]
        self._user32.LoadCursorFromFileW.restype = wintypes.HANDLE

        self._user32.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._user32.SetSystemCursor.restype = wintypes.BOOL

        self._user32.DestroyCursor.argtypes = [wintypes.HANDLE]
        self._user32.DestroyCursor.restype = wintypes.BOOL

    def refresh_cursors(self) -> bool:
        """从注册表重新加载系统游标."""
        result = self._user32.SystemParametersInfoW(
            SPI_SETCURSORS, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        return bool(result)

    def set_single_cursor(self, cursor_file: Path, cursor_type: CursorType) -> bool:
        """仅替换当前会话中的单个系统游标（不写注册表，不持久）."""
        ocr_id = OCR_MAP.get(cursor_type)
        if ocr_id is None:
            return False

        cursor_path = str(cursor_file.absolute())
        h_cursor = self._user32.LoadCursorFromFileW(cursor_path)
        if not h_cursor:
            return False

        # SetSystemCursor 会拥有游标句柄，不需要 DestroyCursor
        result = self._user32.SetSystemCursor(h_cursor, ocr_id)
        return bool(result)

    def apply_theme_session(self, cursor_files: dict[CursorType, Path]) -> dict[CursorType, bool]:
        """仅会话级应用（不持久）."""
        results: dict[CursorType, bool] = {}
        for cursor_type, filepath in cursor_files.items():
            if filepath and filepath.exists():
                results[cursor_type] = self.set_single_cursor(filepath, cursor_type)
            else:
                results[cursor_type] = False
        return results

    def apply_theme(
        self,
        cursor_files: dict[CursorType, Path],
        scheme_name: str = "CursorVault",
        persistent: bool = True,
    ) -> dict[CursorType, bool]:
        """应用主题到系统.

        默认 persistent=True：写注册表后 SPI_SETCURSORS 刷新，重启后仍生效。
        """
        valid = {
            ct: path
            for ct, path in cursor_files.items()
            if path and Path(path).exists()
        }
        results: dict[CursorType, bool] = {ct: False for ct in cursor_files}

        if not valid:
            return results

        if persistent:
            ok = registry_manager.apply_theme_registry(valid, scheme_name=scheme_name)
            if ok:
                for ct in valid:
                    results[ct] = True
                return results
            # 注册表失败时回退到会话级
            session = self.apply_theme_session(valid)
            results.update(session)
            return results

        session = self.apply_theme_session(valid)
        results.update(session)
        return results

    def backup_current_cursors(self, backup_dir: Path) -> bool:
        """备份当前系统游标注册表设置到文件."""
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            reg_path = backup_dir / "cursors_backup.reg"
            result = subprocess.run(
                [
                    "reg",
                    "export",
                    f"HKEY_CURRENT_USER\\{REG_CURSORS_PATH}",
                    str(reg_path.absolute()),
                    "/y",
                ],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def restore_from_backup(self, backup_dir: Path) -> bool:
        """从备份恢复游标."""
        reg_path = backup_dir / "cursors_backup.reg"
        if not reg_path.exists():
            return False
        try:
            result = subprocess.run(
                ["reg", "import", str(reg_path.absolute())],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return self.refresh_cursors()
            return False
        except Exception:
            return False


class RegistryManager:
    """Windows 注册表游标管理（持久化方案）."""

    @staticmethod
    def get_current_scheme() -> str:
        """获取当前游标方案名称."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_CURSORS_PATH, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, "")
                return str(value) if value else "Windows 默认"
        except OSError:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, REG_CURSORS_PATH, 0, winreg.KEY_READ
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "Scheme Source")
                    return str(value) if value else "Windows 默认"
            except OSError:
                return "Windows 默认"

    @staticmethod
    def get_scheme_list() -> list[str]:
        """获取系统已安装的游标方案列表."""
        schemes: list[str] = []
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_CURSORS_SCHEMES_PATH,
                0,
                winreg.KEY_READ,
            ) as key:
                i = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, i)
                        schemes.append(name)
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            pass
        return schemes

    @staticmethod
    def apply_theme_registry(
        cursor_files: dict[CursorType, Path],
        scheme_name: str = "CursorVault",
    ) -> bool:
        """通过注册表持久化应用游标主题，并刷新系统游标."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_CURSORS_PATH,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            ) as key:
                for cursor_type, filepath in cursor_files.items():
                    if filepath and Path(filepath).exists():
                        reg_name = REGISTRY_VALUE_MAP.get(cursor_type)
                        if reg_name:
                            winreg.SetValueEx(
                                key,
                                reg_name,
                                0,
                                winreg.REG_EXPAND_SZ,
                                str(Path(filepath).resolve()),
                            )

                # 标记为自定义方案，便于系统识别
                try:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, scheme_name)
                except OSError:
                    pass
                try:
                    winreg.SetValueEx(key, "Scheme Source", 0, winreg.REG_DWORD, 1)
                except OSError:
                    pass

            api = SystemCursorAPI()
            return api.refresh_cursors()
        except Exception:
            return False


# 单例
system_cursor_api = SystemCursorAPI()
registry_manager = RegistryManager()

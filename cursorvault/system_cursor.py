"""Windows 系统游标 API 封装.

使用 ctypes 调用 Windows API 来替换系统游标。
支持两种方式：
1. 直接替换当前会话（SystemParametersInfo）
2. 修改注册表（持久化）
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import winreg
from pathlib import Path
from typing import Optional

from .models import CursorType, OCR_MAP, REGISTRY_VALUE_MAP


# --- Windows API 常量 ---
SPI_SETCURSORS = 0x0057
SPI_SETCURSOR = 0x005C
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

# 注册表路径
REG_CURSORS_PATH = r"Control Panel\Cursors"
REG_CURSORS_SCHEMES_PATH = r"Control Panel\Cursors\Schemes"


# --- Windows API 函数签名 ---
class SystemCursorAPI:
    """Windows 系统游标 API."""

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._user32.SystemParametersInfoW.argtypes = [
            wintypes.UINT,  # uiAction
            wintypes.UINT,  # uiParam
            wintypes.LPVOID,  # pvParam
            wintypes.UINT,  # fWinIni
        ]
        self._user32.SystemParametersInfoW.restype = wintypes.BOOL

        self._user32.LoadCursorFromFileW.argtypes = [wintypes.LPCWSTR]
        self._user32.LoadCursorFromFileW.restype = wintypes.HANDLE

        self._user32.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._user32.SetSystemCursor.restype = wintypes.BOOL

        self._user32.DestroyCursor.argtypes = [wintypes.HANDLE]
        self._user32.DestroyCursor.restype = wintypes.BOOL

    def refresh_cursors(self) -> bool:
        """刷新系统游标（从注册表重新加载）. """
        result = self._user32.SystemParametersInfoW(
            SPI_SETCURSORS, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        return bool(result)

    def set_single_cursor(self, cursor_file: Path, cursor_type: CursorType) -> bool:
        """替换单个系统游标."""
        ocr_id = OCR_MAP.get(cursor_type)
        if ocr_id is None:
            return False

        cursor_path = str(cursor_file.absolute())

        # 加载游标文件
        h_cursor = self._user32.LoadCursorFromFileW(cursor_path)
        if not h_cursor:
            return False

        # 设置系统游标
        result = self._user32.SetSystemCursor(h_cursor, ocr_id)
        # SetSystemCursor 会拥有游标句柄，不需要 DestroyCursor
        return bool(result)

    def apply_theme(self, cursor_files: dict[CursorType, Path]) -> dict[CursorType, bool]:
        """应用整个主题到系统."""
        results: dict[CursorType, bool] = {}
        for cursor_type, filepath in cursor_files.items():
            if filepath and filepath.exists():
                results[cursor_type] = self.set_single_cursor(filepath, cursor_type)
            else:
                results[cursor_type] = False
        return results

    def backup_current_cursors(self, backup_dir: Path) -> bool:
        """备份当前系统游标注册表设置到文件."""
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            reg_path = backup_dir / "cursors_backup.reg"

            # 导出当前游标配置
            import subprocess
            result = subprocess.run(
                ["reg", "export",
                 f"HKEY_CURRENT_USER\\{REG_CURSORS_PATH}",
                 str(reg_path.absolute()),
                 "/y"],
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
            import subprocess
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
    """Windows 注册表游标管理（持久化方案）. """

    @staticmethod
    def get_current_scheme() -> str:
        """获取当前游标方案名称."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_CURSORS_PATH, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Scheme Source")
                return value or "Windows 默认"
        except FileNotFoundError:
            return "Windows 默认"

    @staticmethod
    def get_scheme_list() -> list[str]:
        """获取系统已安装的游标方案列表."""
        schemes = []
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_CURSORS_SCHEMES_PATH,
                0, winreg.KEY_READ
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
        """通过注册表持久化应用游标主题."""
        try:
            # 打开游标注册表键
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_CURSORS_PATH,
                0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            ) as key:
                for cursor_type, filepath in cursor_files.items():
                    if filepath and filepath.exists():
                        reg_name = REGISTRY_VALUE_MAP.get(cursor_type)
                        if reg_name:
                            winreg.SetValueEx(
                                key, reg_name, 0, winreg.REG_EXPAND_SZ,
                                str(filepath.absolute()),
                            )

            # 刷新
            api = SystemCursorAPI()
            return api.refresh_cursors()

        except Exception:
            return False


# 单例
system_cursor_api = SystemCursorAPI()
registry_manager = RegistryManager()

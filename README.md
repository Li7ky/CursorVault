# CursorVault 鼠标素材库 🖱️

> 一款开源免费的 Windows 鼠标光标主题管理与替换工具

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ 功能特色

- **🎨 致美化素材集成**：直接使用 [致美化 (zhutix.com)](https://zhutix.com/tag/cursors/) 下载的游标包
- **⚡ 一键应用**：选中主题即可替换系统所有游标
- **👁️ 实时预览**：可视化预览每个游标样式
- **💾 备份恢复**：一键备份/恢复系统游标设置
- **📂 导入支持**：支持导入自定义 `.cur` 游标文件目录
- **🖥️ Windows 原生**：直接调用系统 API 替换游标

## 🖼️ 截图

*(运行后截图)*

## 📦 安装

### 前置条件

- Python 3.10 或更高版本
- Windows 10/11

### 安装步骤

```bash
# 1. 克隆或下载本项目
git clone https://github.com/yourusername/cursorvault.git
cd cursorvault

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python -m cursorvault
```

> **注意**：替换系统游标需要管理员权限。建议以管理员身份运行终端再执行 `python -m cursorvault`。

## 🚀 使用指南

### 快速上手

1. 从 [致美化 - 鼠标指针](https://zhutix.com/tag/cursors/) 下载喜欢的游标包
2. 解压后放入 `themes/imported/` 目录（每个主题一个子目录）
3. 运行 `python -m cursorvault` 启动程序
4. 左侧选择主题
5. 点击「应用到系统」替换系统游标

### 菜单功能

| 菜单 | 功能 |
|------|------|
| 文件 → 导入游标目录 | 导入自定义 .cur 文件目录 |
| 文件 → 退出 | 退出程序 |
| 工具 → 备份当前游标 | 备份当前系统游标配置 |
| 工具 → 恢复游标 | 从备份恢复游标 |
| 工具 → 刷新系统游标 | 重新加载系统游标设置 |
| 帮助 → 关于 | 查看版本信息 |

## 🏗️ 项目结构

```
cursorvault/
├── __main__.py                # 入口文件
├── requirements.txt           # 依赖清单
├── LICENSE                    # MIT 协议
├── README.md                  # 本文档
├── cursorvault/               # 核心模块
│   ├── __init__.py            # 包定义
│   ├── app.py                 # 应用初始化
│   ├── main_window.py         # 主窗口 UI
│   ├── cursor_preview.py      # 预览控件
│   ├── theme_manager.py       # 主题管理（致美化导入）
│   ├── system_cursor.py       # Windows 游标 API
│   ├── zhutix_client.py       # 致美化数据抓取
│   └── models.py              # 数据模型
├── themes/                    # 游标文件
│   └── imported/              # 用户导入的主题
└── backup/                    # 备份目录
```

## 🛠️ 技术栈

- **Python 3.12** - 核心语言
- **PyQt6** - 桌面 GUI 框架
- **ctypes** - Windows 系统 API 调用
- **winreg** - 注册表操作

## 📝 开发计划

- [ ] macOS/Linux 支持
- [ ] 在线主题浏览（致美化集成）
- [ ] 游标编辑器（自定义游标）
- [ ] 动画游标 (.ani) 支持
- [ ] HiDPI 适配

## 🤝 贡献指南

欢迎贡献！请提交 Issue 或 Pull Request。

1. Fork 本仓库
2. 创建特性分支: `git checkout -b feature/amazing-feature`
3. 提交改动: `git commit -m 'Add amazing feature'`
4. 推送分支: `git push origin feature/amazing-feature`
5. 提交 Pull Request

## 📄 许可

本项目采用 MIT 协议 - 详见 [LICENSE](LICENSE) 文件。

---

**CursorVault** - 让你的鼠标指针与众不同 ✨

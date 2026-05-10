# TermiTransfer v2 诊断报告

> 评估时间: 2026-05-10
> 文件: TermiTransfer.py (1228 行)
> 对标: WinSCP / FileZilla / Cyberduck / VS Code Dark Theme

---

## 一、版本演进对比 (v1 → v2)

| 改进项 | v1 | v2 | 状态 |
|--------|----|----|------|
| 字体常量 | 内联硬编码 5 处 | `FONT` / `FONT_BOLD` / `FONT_TEXT` 顶部定义 | ✅ 已修复 |
| 连接字段折叠 | 始终展开 | 可折叠 + `user@host:port` 摘要 | ✅ 已修复 |
| 摘要同步 | 切 profile 才更新 | `KeyRelease` 实时同步 host/port/user | ✅ 已修复 |
| Profile 切换 | 销毁重建整个 Tab 区域 | `_refresh_presets()` + `_refresh_download_fields()` 增量刷新 | ✅ 已修复 |
| Log 区域 | 随 Tab 一起销毁 | 独立 `_build_log_area()`，永不销毁 | ✅ 已修复 |
| 传输按钮状态 | 无反馈 | `disabled` + 文字变 "Uploading.../Downloading..." | ✅ 已修复 |
| 传输进度 | 无 | `ttk.Progressbar` + 百分比 + 计数器，3s 后自动隐藏 | ✅ 新增 |
| 白色边框 | `TLabelframe` 无 bordercolor | 加了 `bordercolor=t["bg"], relief="flat"` | ✅ 已修复 |
| disabled 按钮 hover | 会变色 | 加了 `btn["state"] != "disabled"` 检查 | ✅ 已修复 |
| `_rebuild_dynamic_area` 命名 | 暗示可重复调用 | 改名为 `_build_tabs()`，语义清晰 | ✅ 已修复 |

---

## 二、仍未解决的问题

### 2.1 tk/ttk 控件混用 [严重]

**现状**: `_make_btn()` 返回 `tk.Button`，所有输入框用 `ttk.Entry`，容器用 `ttk.Frame`。两套渲染引擎共存。

**影响**:
- `_apply_theme` 需要同时操作 `ttk.Style()` 和逐个 `widget.configure()`
- `_restyle_buttons()` 递归遍历整棵 widget 树刷新 tk.Button
- tk.Button 和 ttk.Button 的内边距、字体渲染、对齐方式有微妙差异

**代码位置**: L243-268 (`_make_btn`), L270-279 (`_restyle_buttons`)

**行业做法**: 统一用 ttk.Button + Style class 管理。或者用 ttkbootstrap 一行切换主题。

### 2.2 `_apply_theme` 仍为 115 行 [严重]

**现状**: L284-398，逐个 widget 名字硬编码刷新，6 个 Text widget + 5 个 Entry + 1 个 Combobox + 递归 `_style_entries`。

**风险**: 新增任何 widget 都要记得在这里加一行，否则主题切换后颜色不对。没有编译器检查，全靠人肉维护。

**行业做法**: ttkbootstrap 的 `Style(theme='darkly')` 自动覆盖所有 ttk widget。手动方案用 Style class（如 `"Accent.TButton"`）统一管理。

### 2.3 RoundedTabBar hover bug 未根治 [中等]

**现状**: `_unhover()` 无条件恢复 `t["btn_bg"]`。如果鼠标快速划过选中态的 tab 按钮，leave 事件会把它从 accent 色变灰。

**代码位置**: L195-197

```python
def _unhover(self, idx):
    if idx != self.selected:  # 保护了非选中态
        self.tabs[idx][2].configure(bg=self.theme["btn_bg"])
    # 但 _make_btn 的 on_leave 没有这层保护
```

**注意**: `_make_btn` 的 `on_leave` (L262-264) 已加 `disabled` 检查，但没有 selected/active 状态保护。

### 2.4 日志无颜色编码 [中等]

**现状**: 所有日志（连接成功、传输进度、错误信息）都是同一种颜色的纯文本。

**行业做法**:
- FileZilla: 绿色=成功，红色=错误，默认色=信息
- WinSCP: 不同操作用不同颜色高亮
- 实现方式: `ScrolledText.tag_configure("error", foreground="#f44747")`

### 2.5 `_refresh_presets` 仍全量销毁重建 [低]

**现状**: L644 `w.destroy()` 销毁所有 preset 行，然后重新创建。切 profile 时会闪屏。

**优化**: 当新旧 preset 数量相同时，复用已有 widget，只更新 Entry 内容和 BooleanVar。

### 2.6 无确认机制 [低]

**现状**: Upload/Download 点击即发，删除 Profile 只检查"是否最后一个"。

**行业做法**: WinSCP 在覆盖同名文件时弹确认框；删除操作有 "Are you sure?" 对话框。

### 2.7 进度条只有文件级粒度 [低]

**现状**: `progress_var` 按文件数量计算百分比（3/8 = 37%），不反映单文件的字节级进度。

**行业做法**: `sftp.put(local, remote, callback=progress_callback)` 可以拿到字节级回调。双层进度条：薄的显示队列，厚的显示当前文件。

---

## 三、架构质量评分

| 维度 | v1 | v2 | 行业标杆 | 说明 |
|------|----|----|----------|------|
| **主题系统** | 2/10 | 3/10 | 9/10 | 白色边框修了，但 115 行 `_apply_theme` 仍是技术债 |
| **控件一致性** | 3/10 | 3/10 | 9/10 | tk/ttk 混用未解决 |
| **信息架构** | 3/10 | 5/10 | 9/10 | 折叠连接字段是正确方向 |
| **传输反馈** | 1/10 | 5/10 | 9/10 | 进度条 + 按钮状态，缺字节级进度 |
| **Profile 切换性能** | 2/10 | 7/10 | 9/10 | 增量刷新，但 preset 仍全量重建 |
| **代码可维护性** | 3/10 | 4/10 | 8/10 | 字体常量提取了，但主题逻辑仍是硬编码 |
| **错误处理** | 2/10 | 2/10 | 8/10 | 仍写灰色日志，无颜色区分 |
| **确认机制** | 0/10 | 0/10 | 7/10 | 无二次确认 |
| **快捷键** | 4/10 | 6/10 | 8/10 | KeyRelease 同步是加分项 |
| **代码量** | 1196 行 | 1228 行 | - | 增加 32 行，新增了进度条功能 |

---

## 四、依赖分析

| 依赖 | 类型 | 用途 | 必要性 |
|------|------|------|--------|
| `paramiko` | 三方 (C 扩展) | SSH/SFTP 核心 | 必须 |
| `cryptography` | 三方 (C 扩展) | Fernet 密码加密 | 必须 (paramiko 间接依赖) |
| `ttkbootstrap` | 三方 (纯 Python) | 主题系统 | **已安装但未使用** |
| `tkinter` | 标准库 | GUI | 必须 |
| `json/os/sys/...` | 标准库 | 基础功能 | 无额外依赖 |

**打包体积预估**:
- PyInstaller `--onefile`: ~30-40 MB (Python 解释器 ~12MB + paramiko/cryptography ~15MB)
- 若改用 Go + TUI: ~5-8 MB
- 若改用 Go + Fyne GUI: ~15-20 MB

---

## 五、优先级排序 (投入产出比)

| 优先级 | 改进项 | 预估工作量 | 收益 |
|--------|--------|-----------|------|
| P0 | 接入 ttkbootstrap（替代手动 `_apply_theme`） | 1-2h | 消灭白色边框 + 115 行主题代码砍到 0 |
| P1 | 日志颜色编码（tag_configure） | 30min | 错误一目了然 |
| P1 | `_refresh_presets` widget 复用 | 1h | 消除切 profile 闪屏 |
| P2 | sftp.put/get 字节级进度回调 | 1-2h | 进度条从"文件级"升级到"字节级" |
| P2 | 二次确认（删除 profile、覆盖文件） | 30min | 防误操作 |
| P3 | tk.Button → ttk.Button 统一 | 2-3h | 消灭 tk/ttk 混用（与 P0 联动） |
| P3 | Go 重写 / Nuitka 编译 | 1-2d | 体积从 30MB 降到 5-20MB |

---

## 六、代码结构图

```
TermiTransfer.py (1228 行)
│
├── 常量区 (L1-20)
│   CONFIG_PATH, FONT, FONT_BOLD, FONT_TEXT
│
├── 密码加密 (L22-47)
│   _get_fernet_key() → encrypt_pw() / decrypt_pw()
│
├── 配置管理 (L49-133)
│   DEFAULT_PROFILES → load_config() → save_config()
│
├── RoundedTabBar (L135-197)
│   自绘 tk.Button tab 栏，hover bug 未根治
│
└── TermuxTransferApp (L199-1228)
    │
    ├── 主题系统 (L230-398)
    │   THEMES dict → _make_btn() → _restyle_buttons()
    │   └── _apply_theme() ← 115 行，最大技术债
    │
    ├── UI 构建 (L444-596)
    │   setup_ui()
    │   ├── _build_connection_frame()  ← 可折叠，KeyRelease 同步
    │   ├── _build_tabs()              ← 一次性构建
    │   └── _build_log_area()          ← 独立，含 Progressbar
    │
    ├── Tab 内容 (L598-740)
    │   ├── _build_upload_tab() → _refresh_presets()
    │   ├── _build_download_tab() → _refresh_download_fields()
    │   └── _build_config_tab() → _refresh_config_preview()
    │
    ├── Profile 管理 (L825-990)
    │   _get/_load/_save → _on_change/_add/_remove/_cycle
    │   全部走增量刷新，不销毁 widget
    │
    └── 传输逻辑 (L1024-1218)
        _make_ssh_client() → _sftp_put/get_recursive()
        → _run_sftp() ← 后台线程，进度条 + 按钮状态管理
```

---

## 七、与上次评估的改进总结

上次指出的 20 个问题，本次修复了 **8 个**:

| # | 问题 | 状态 |
|---|------|------|
| 1 | 白色边框 (TLabelframe) | ✅ 已修 (bordercolor + relief="flat") |
| 5 | tk/ttk 混用 | ❌ 仍在 |
| 6 | _apply_theme 150 行 | ⚠️ 缩到 115 行，本质未变 |
| 7 | hover bug | ⚠️ disabled 检查加了，selected 态未保护 |
| 9 | 零进度反馈 | ✅ 已修 (Progressbar + 计数器) |
| 10 | 无确认机制 | ❌ 仍在 |
| 13 | 字体硬编码 | ✅ 已修 (提取常量) |
| 15 | 快捷键 `(&A)` 误导 | ✅ 已修 (改用 underline) |
| 18 | Profile 切换销毁重建 | ✅ 已修 (增量刷新) |
| 连接摘要不同步 | | ✅ 已修 (KeyRelease) |
| Log 随 Tab 销毁 | | ✅ 已修 (独立构建) |

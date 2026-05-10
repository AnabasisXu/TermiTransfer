# TermiTransfer

常用文件传输工具：把要传的文件/目录保存成配置，一键调用；全键盘操作，依赖少，启动快。

## 为什么不用 WinSCP / LocalSend

| | WinSCP | LocalSend | TermiTransfer |
|---|---|---|---|
| 重复任务 | 需要每次重新选路径或写脚本 | 不支持 | Preset 一键勾选 |
| 键盘操作 | 有限 | 无 | 全键盘快捷键 |
| 配置迁移 | 手动导出注册表/INI | 无 | JSON 导入导出连接与路径（密码不随配置迁移） |
| 目标场景 | 通用文件管理 | 局域网点对点传文件 | 固定主机间的常用路径反复传输 |
| 依赖 | 安装包 ~10MB | 需要两端都装 | 本地 pip install 依赖即可 |

WinSCP 功能更强，但对"每天往同一台机器的同一目录传文件"这个场景来说操作步骤太多。LocalSend 解决的是"临时给旁边的人传个文件"，不支持路径预设和重复执行。

## 定位

- 面向日常文件传输场景，重点解决常用路径和常用任务的快速重复执行
- 案例：
    - 把 PC 上的 note 目录传输到 Termux ，方便在手机上查看
    - 把手机上的照片同步到PC
    - 把服务器上的配置文件同步到PC

## 特色

- 配置驱动：常用文件、目录、目标路径都保存在配置中，随时调用；配置可自动保存
- 配置可复用：支持导入导出，方便在不同机器间迁移（密码不随配置迁移）
- 全键盘化：主要操作都能用快捷键完成，减少鼠标操作
- 轻量启动：依赖少，启动快，适合随手使用

## 安装

```bash
pip install paramiko
```
## 使用

```bash
python TermiTransfer.py
```

首次运行时，如果当前没有可用配置，可在界面中手动填写并保存 Host、Port、User、Key。密码每次启动需重新输入。

## 平台支持

| 平台 | 状态 |
|------|------|
| Windows | 已测试 |
| Linux | 未验证 |
| macOS | 未验证 |

配置文件路径为 `~/.termi_transfer_config.json`。

## 完整用法

### 1) 用 Profile 保存连接

- Host / Port / User / Key（可保存）
- Password（每次启动临时输入）
- 保存后可在下拉框快速切换

### 2) 用 Preset 保存常用传输任务

- 上传：选择本地文件/目录 + 指定远端目标目录
- 下载：填写远端路径 + 本地保存目录
- Preset 支持新增、编辑、删除，执行时直接勾选

### 3) 复用配置

- 在 **Config** 页导出当前配置
- 在另一台机器导入，即可复用同一套任务设置

## 常用操作

| 场景 | 操作 |
|---|---|
| 快速上传 | 选文件 -> 勾选目标 -> 开始上传 |
| 快速下载 | 填远端路径 -> 填本地目录 -> 开始下载 |
| 切换目标机 | 切换 Profile |
| 复制到其他机器 | 导出/导入配置 |

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt-Up` / `Alt-Down` | 切换 Upload/Download 标签页 |
| `Alt-c` | 切换到 Config 标签页 |
| `Alt-a` | 添加文件 |
| `Alt-f` | 聚焦文件列表 |
| `Alt-l` | 清空文件列表 |
| `Alt-s` | 开始上传 |
| `Alt-b` | 浏览本地目录 |
| `Alt-d` | 开始下载 |
| `Alt-u` | 聚焦第一个 Preset |
| `Alt-p` | 循环切换 Profile |
| `Alt-Insert` | 新建 Profile |
| `Alt-m` | 删除 Profile |
| `Alt-h` | 聚焦 Host 输入框 |
| `Alt-t` | 聚焦 Port 输入框 |
| `Alt-r` | 聚焦 User 输入框 |
| `Alt-k` | 聚焦 Key 输入框 |
| `Alt-w` | 聚焦 Password 输入框 |
| `Alt-i` | 导入配置 |
| `Alt-e` | 导出配置 |
| `Ctrl-Alt-m` | 切换主题 |

## 配置

配置保存在 `~/.termi_transfer_config.json`，Windows路径一般是`C:\Users\Username\.termi_transfer_config.json`。

示例如下：

```json
{
  "active_profile": "Default",
  "profiles": {
    "Default": {
      "host": "192.168.1.100",
      "port": "22",
      "user": "myuser",
      "key": "/path/to/ssh_key",
      "presets": {
        "~/": "~/",
        "/var/www/": "/var/www/"
      }
    }
  }
}
```

## 行为说明

- **密码不会保存到配置文件**，每次启动需要重新输入，主要是不想引入复杂的密码加密。
- 相同 `host:port:user` 会复用已有 SSH 连接，避免重复握手
- 执行前会先同步当前界面到配置，保证下次可直接复用
- 关闭窗口时保存当前状态

## 许可证

MIT


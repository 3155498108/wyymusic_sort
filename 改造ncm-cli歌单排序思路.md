# ncm-cli 歌单排序改造记录

## 目标

给 `@music163/ncm-cli` 添加一个 `playlist reorder` 子命令，或者让 Python 版歌单排序器能够直接调用 ncm-cli 的登录态来完成歌单操作（加载歌曲、排序）。

---

## 已确认的事实

### 1. 环境

- Node.js: `C:\Program Files\nodejs\node.exe` (v24.11.0)
- npm 全局路径: `C:\Users\spenc\AppData\Roaming\npm`
- ncm-cli 路径: `C:\Users\spenc\AppData\Roaming\npm\node_modules\@music163\ncm-cli\dist\index.js`
- ncm-cli 版本: 0.1.2
- PowerShell 脚本: `C:\Users\spenc\AppData\Roaming\npm\ncm-cli.ps1`
- 配置目录: `C:\Users\spenc\.config\ncm-cli\`
  - `credentials.enc.json` — 登录凭证（DPAPI 加密，无法从 Python 读取）
  - `tokens.enc.json` — token（DPAPI 加密）
  - `bg-worker.log` — 后台登录轮询日志

### 2. ncm-cli 现有命令

可用命令（`ncm-cli commands` 输出）：
```
play, pause, resume, stop, next, prev, seek, volume,
queue, state, login, logout, configure, upgrade,
config (set/get/list), cloudupload (upload/status/stop/list), help, commands
```

**注意：没有 `playlist` 子命令**。之前测试中 `ncm-cli playlist created` 报错 `unknown command 'playlist'`。

### 3. ncm-cli login 状态

- `ncm-cli login --check` 返回 `{"success": false, "message": "未登录，请执行 ncm-cli login 完成登录"}`
- 但 `bg-worker.log` 里反复出现"登录成功，欢迎在某登录"，说明后台轮询进程中曾成功登录过
- `ncm-cli login --background` 可以生成新的扫码 URL（`https://163cn.tv/5XV4uNH`）
- 登录状态检查（`ncm-cli login --check`）和后台轮询不共享同一个进程上下文，所以 check 返回未登录

### 4. 从 Python 调用 ncm-cli

以下方式从 Python subprocess 调用均**失败**（`unknown command 'playlist'`）：

```python
subprocess.run(['node', NCM_PATH, 'playlist', 'created', '--output', 'json'])
subprocess.run(['ncm-cli', 'playlist', 'created', '--output', 'json'], shell=True)
subprocess.run(['powershell', '-Command', 'ncm-cli playlist created --output json'])
```

以下方式从 Python 调用**成功**（但不能用于 playlist 命令，因为该命令不存在）：

```python
subprocess.run(['ncm-cli', 'login', '--check', '--output', 'json'], shell=True)  # 成功
subprocess.run(['ncm-cli', 'login', '--background', '--output', 'json'])  # 成功
```

### 5. 网易云音乐 API

**匿名登录（设备校验失败）：**
- `GET /openapi/music/basic/oauth2/login/anonymous` 返回 400：`os/channel/brand 校验失败`
- 已尝试组合：web/web/web, windows/web/windows, pc/web/pc, android/app/Android 等，均失败
- 文档中 channel 示例值 `iotapitest` 也失败

**QR 登录端点：**
- `POST /openapi/music/basic/oauth2/login/qrcode` 返回 404（接口未找到）

**歌单 API（不需要签名，只需要 cookie）：**
```
GET  /api/v3/playlist/detail?id={playlist_id}&n=1000000
GET  /api/v3/playlist/track/update?ids={id1,id2,...}  (更新排序)
```
这些接口只需要登录后的 cookie，不需要 RSA 签名。

### 6. DPAPI 加密

`credentials.enc.json` 和 `tokens.enc.json` 使用 Windows DPAPI 加密：
```json
{"iv": "...", "data": "..."}
```
无法在 Python 中解密（需要当前用户会话的 DPAPI key）。

---

## 待解决的核心问题

### 问题 1：ncm-cli 没有 playlist 子命令

需要给 ncm-cli 添加这个命令。可选方案：

**方案 A：在 ncm-cli 源码中添加 playlist 子命令**
- 克隆或修改 `@music163/ncm-cli` 源码
- 添加 `playlist created`、`playlist tracks`、`playlist reorder` 命令
- 调用网易云音乐 API（带签名或不带签名）
- 重新 link 到全局 npm

**方案 B：用 ncm-cli 的 `play` 命令间接操作歌单**
- `ncm-cli play --playlist --original-id {id}` 可以播放歌单
- 但无法用它来获取歌曲列表或修改排序

### 问题 2：从 Python 无法获取 ncm-cli 的登录态

ncm-cli 的 token 是 DPAPI 加密的，Python 无法直接读取。

可行的解决思路：

1. **让 Python 操控 ncm-cli 扫码登录**：调用 `ncm-cli login --background` 生成二维码 URL，显示给用户，用户扫码后 Python 轮询直到登录成功，然后通过其他方式获取 cookie

2. **修改 ncm-cli 源码输出明文 token**：在 ncm-cli 的 `login --check` 实现里，如果已登录就把 token 明文输出到 stdout（而非加密格式）

3. **让 ncm-cli 把 token 写到可读的 JSON 文件**：修改 ncm-cli 源码，在登录成功后把 token 以明文 JSON 形式写到一个文件，Python 读取该文件

### 问题 3：歌单 API 的签名问题

网易云音乐的部分 API 需要带签名才能访问（如 `/api/v3/playlist/track/update`）。签名需要：
- AppID: `b3010d0000000000877a84a1e79acb4b`
- Private Key（PKCS#1，已确认有效）

Python 可以独立完成 RSA 签名，不需要 ncm-cli。

---

## 建议的改造路线（供 Claude Code 参考）

### Phase 1: 给 ncm-cli 添加 playlist 子命令

在 ncm-cli 源码（`dist/index.js` 或源码 ts 文件）中添加：

```typescript
// playlist created  → 列出当前用户创建的歌单
// playlist tracks <playlistId>  → 列出歌单里的所有歌曲
// playlist reorder <playlistId> --track-ids <json-array>  → 更新歌单歌曲顺序
```

关键 API（不需要签名，需要 cookie）：
```
GET /api/v3/playlist/detail?id={encrypted_id}&n=1000000
POST /api/v3/playlist/track/update with cookie
```

### Phase 2: 让 Python 能获取登录态

在 ncm-cli 的登录流程里，当 `login --check` 发现已登录时，把 token/cookie 以明文输出到特定文件（如 `~/.config/ncm-cli/token_plain.json`），格式：
```json
{
  "cookie": "appver=2.0; os=pc; __remember_me=true; ...",
  "userId": 316064264,
  "nickname": "炮灰海"
}
```

### Phase 3: Python 端实现

```python
# 1. 调用 ncm-cli login --background 获取二维码 URL
# 2. 显示二维码给用户
# 3. 轮询 ncm-cli login --check 直到成功
# 4. 读取 ncm-cli 输出的明文 token 文件
# 5. 用 cookie 调用歌单 API（/api/v3/playlist/detail）
# 6. Python 端做多级排序
# 7. 调用 ncm-cli playlist reorder 或直接用 cookie 调用更新 API
```

---

## 参考资料

- AppID: `b3010d0000000000877a84a1e79acb4b`
- 私钥（PKCS#1，2048-bit）：已保存在 `E:\jsjzy\music163\pyqt_app\main.py`
- 测试歌单：`Bang Dream! 系列歌曲合集（更新中）`
  - 加密 ID: `A7587AF9528A4B9F00436694359E35AA`
  - 原始 ID: `4943170241`
  - 歌曲数: 1148 首
- 已有 Python 实现（签名、API 调用）：`E:\jsjzy\music163\pyqt_app\main.py`
- ncm-cli 源码：`C:\Users\spenc\AppData\Roaming\npm\node_modules\@music163\ncm-cli\`
- ncm-cli 文档：`E:\jsjzy\music163\网易云音乐开发平台.txt`

---

## 备注

- 用户的 app 是"网页应用"类型，`os/channel/brand` 的校验逻辑不明，匿名登录失败
- ncm-cli 内部使用的设备参数是混淆的，无法直接提取
- 从 PowerShell 直接调用 `ncm-cli playlist created` 也报错，说明 `playlist` 命令确实不存在于 0.1.2 版本
- ncm-cli 的 `bg-worker.log` 显示后台轮询"登录成功"，说明扫码登录流程本身是通的，只是 check 命令读不到登录结果
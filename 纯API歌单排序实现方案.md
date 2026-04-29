# 网易云歌单排序器 — 纯 API 实现方案

不依赖 ncm-cli，直接调网易云音乐开放平台 API 完成扫码登录、歌单读取、多级排序。

---

## 一、整体架构

```
用户操作（PyQt6 界面）
    ├── 扫码登录 → 获取 cookie / accessToken
    ├── 加载歌单列表（/api/v3/playlist/detail）
    ├── 加载歌曲（/api/v3/playlist/detail）
    ├── Python 内存排序（多级 sort key）
    └── 执行排序（/api/v3/playlist/track/update 或 openapi 签名接口）
```

---

## 二、已知 API 端点

### 2.1 登录相关

| 端点 | 方法 | 签名 | 说明 |
|------|------|------|------|
| `/openapi/music/basic/oauth2/login/anonymous` | GET | ✅ RSA | 匿名登录，**设备校验失败** |
| `/openapi/music/basic/oauth2/login/qrcode` | POST | ✅ RSA | 扫码登录，**返回 404** |
| `/api/v3/playlist/detail` | GET | ❌ | 只需要 cookie，不需要签名 |

**问题 1：`/openapi/music/basic/oauth2/login/qrcode` 返回 404**
- 测试结果：POST 返回 `{"code":404,"message":"接口未找到"}`
- 可能原因：
  - QR 登录走了不同的域名或路径
  - 需要带正确的 `Content-Type` 或 body 格式
  - 端点本身不存在，需要从其他入口进入

**问题 2：匿名登录设备校验失败**
- 所有 `os/channel/brand` 组合均返回 400：`os/channel/brand 校验失败`
- 已测试（全部失败）：web/web/web, windows/web/windows, pc/web/pc, android/app/Android, iOS/app/Apple, openapi/openapi/openapi
- 文档中示例 `channel=iotapitest` 也失败
- 平台要求的 os/channel/brand 值不明确，无法绕过

### 2.2 歌单相关（已验证可用）

```
GET /api/v3/playlist/detail?id={encrypted_id}&n=1000000
  → 返回歌单详情，包含 tracks[]（歌曲 id、name、ar、al）
  → 不需要签名，需要登录 cookie
  → 已确认可用（ncm-cli 内部调用成功）

POST /api/v3/playlist/track/update
  → 更新歌单歌曲顺序
  → 参数：ids（逗号分隔的歌曲 id）
  → 可能需要登录 cookie 或签名
```

### 2.3 用户相关

```
GET /api/v3/playlist/detail?uid={userId}&limit=50&offset=0
  → 获取用户创建的歌单列表
  → 不需要签名，需要登录 cookie
```

---

## 三、核心问题与解决思路

### 问题 1：如何登录（绕过设备校验）

**方案 A：找正确的 QR 登录端点**

之前测试 `POST /openapi/music/basic/oauth2/login/qrcode` 返回 404，
但 ncm-cli 的 QR 登录是成功的，说明存在一个有效的 QR 登录接口。

可能路径：
- `/api/user/qrcode` 或类似
- ncm-cli 内部调用的实际接口（需要抓包）

建议：用 Fiddler 或 Charles 抓包 ncm-cli 的 QR 登录过程，
找到它实际调用的 URL 和参数。

**方案 B：绕过设备校验（获取有效 device params）**

设备校验失败的本质：平台要求特定的 os/channel/brand 组合，
这些值在注册应用时分配，但文档中没有说明。

可行的方向：
1. 抓包 ncm-cli 的 HTTP 请求，提取它实际使用的 device 参数
2. 查看 ncm-cli 源码中 device 对象的构建逻辑（dist/index.js 是混淆的，
   但 deviceType/os/channel/brand 等字段名是明确的，可搜索字符串）
3. 询问网易云音乐开放平台技术支持，获取 channel 的合法取值列表

**方案 C：从 ncm-cli 获取登录态（不读 DPAPI）**

ncm-cli 已经成功登录过（bg-worker.log 显示"登录成功"），
token 存在 DPAPI 加密文件里，无法从 Python 读取。

但可以做：
1. 修改 ncm-cli 源码，让它在登录成功后把 token 明文输出到指定文件
2. 或者让 ncm-cli 启动一个本地 HTTP 服务，Python 请求 localhost 获取 token
3. 或者利用 ncm-cli 的 `--background` 模式，登录成功后写入明文文件

**方案 D：换一种登录方式**

除了匿名登录和 QR 登录，还有：
- 手机号 + 验证码登录
- 账号密码登录（加密）
- 第三方登录

但开放平台文档中没有提及这些方式，可能只对特定类型的应用开放。

---

### 问题 2：歌单排序接口

`POST /api/v3/playlist/track/update` 是否需要签名？

根据文档：
- `/api/v3/playlist/track/update` 属于"歌单"相关接口
- 文档中示例请求没有签名（只带 cookie）
- ncm-cli 的 `playlist reorder` 也调用的同一接口

需要验证：从 Python 带上登录 cookie 调用是否成功。

---

## 四、实现步骤

### Step 1：抓包 ncm-cli，找到正确的 API

工具：Fiddler Classic（推荐，免费）
- 开启 HTTPS 解密
- 设置过滤规则只显示 music.163.com
- 运行 `ncm-cli login --background`，抓包找到 QR 登录的真实请求

关键要找到：
1. 获取 QR 图片的 URL（GET 还是 POST？参数是什么？）
2. 轮询扫码状态的 URL（间隔多久？）
3. 登录成功后返回的 token/cookie 格式

### Step 2：验证歌单 API

用 Python 带上 cookie 直接调：
```python
import requests

cookie = "appver=2.0; os=pc; ..."
headers = {"Cookie": cookie}

# 获取歌单详情
r = requests.get(
    "https://music.163.com/api/v3/playlist/detail",
    params={"id": "A7587AF9528A4B9F00436694359E35AA", "n": 1000000},
    headers=headers,
    timeout=10
)
print(r.json())
```

### Step 3：验证排序 API

```python
# 更新歌单排序
r = requests.post(
    "https://music.163.com/api/v3/playlist/track/update",
    data={"ids": "123,456,789"},
    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    timeout=10
)
print(r.json())
```

### Step 4：解决设备校验（或绕过）

找到正确的 QR 登录端点后，实现完整流程：

1. 调用获取二维码接口 → 得到 qrcode_key 和图片 URL
2. 显示二维码（直接用 URL 或生成图片）
3. 每 3 秒轮询扫码状态（GET /qrcode/check?qrcode_key=xxx）
4. 扫码成功后得到 cookie / accessToken
5. 保存到本地文件（JSON 格式，Python 可读）

### Step 5：实现多级排序 UI

用 PyQt6 实现（已有基础框架在 `E:\jsjzy\music163\pyqt_app\main.py`）：

```
┌─────────────────────┬──────────────────────────────┐
│ 歌单列表（左）        │ 歌曲预览表（右）               │
│                     │                              │
│ - Bang Dream 合集    │ #  歌曲名  艺人  专辑         │
│ - xxx歌单           │ 1  xxx   AAA   BBB           │
│ - yyy歌单           │ 2  yyy   CCC   DDD           │
│                     │                              │
│ [刷新] [退出]        │ 第1层: [艺人▼] 第2层: [专辑▼] │
│                     │ 升序☑️                          │
│                     │ [预览] [执行排序]              │
└─────────────────────┴──────────────────────────────┘
```

---

## 五、API 签名实现（供参考）

虽然歌单 API 不需要签名，但其他接口可能需要。
签名方式（Python 实现，已验证有效）：

```python
import base64, time, json, hashlib
from urllib.parse import quote
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256

PRIVATE_KEY = "MIIEvgIB..."  # 你的私钥（PKCS#1）
APP_ID = "b3010d0000000000877a84a1e79acb4b"

def make_sign(content_str):
    pem = "-----BEGIN RSA PRIVATE KEY-----\n" + PRIVATE_KEY + "\n-----END RSA PRIVATE KEY-----"
    key = RSA.import_key(pem)
    return base64.b64encode(pkcs1_15.new(key).sign(SHA256.new(content_str.encode("utf-8")))).decode()

def build_signed_url(path, params):
    ts = str(int(time.time() * 1000))
    device = json.dumps({"clientIp": "127.0.0.1", "deviceId": "...", ...}, ensure_ascii=False)
    p = {"appId": APP_ID, "timestamp": ts, "signType": "RSA_SHA256", "device": device}
    p.update(params)
    content = "&".join(f"{k}={v}" for k, v in sorted(p.items(), key=lambda x: x[0]) if k != "sign")
    p["sign"] = make_sign(content)
    parts = []
    for k, v in sorted(p.items(), key=lambda x: x[0]):
        if k in ("device", "bizContent"):
            parts.append(f"{k}={quote(v, safe='')}")
        else:
            parts.append(f"{k}={v}")
    return "https://openapi.music.163.com" + path + "?" + "&".join(parts)
```

---

## 六、关键文件路径

| 文件 | 说明 |
|------|------|
| `E:\jsjzy\music163\pyqt_app\main.py` | 现有 PyQt6 实现（含签名代码） |
| `E:\jsjzy\music163\网易云音乐开发平台.txt` | 官方文档 |
| `E:\jsjzy\music163\改造ncm-cli歌单排序思路.md` | ncm-cli 改造方案（备选） |

---

## 七、测试用数据

- AppID: `b3010d0000000000877a84a1e79acb4b`
- 私钥: PKCS#1，2048-bit（已确认有效）
- 测试歌单: `Bang Dream! 系列歌曲合集（更新中）`
  - 加密 ID: `A7587AF9528A4B9F00436694359E35AA`
  - 原始 ID: `4943170241`
  - 歌曲数: 1148 首

---

## 八、推荐实现顺序

1. **先抓包** ncm-cli，找到 QR 登录的真实端点（最关键）
2. **验证歌单读取** — 带上 cookie 调 `/api/v3/playlist/detail`
3. **验证排序更新** — 带上 cookie 调 `/api/v3/playlist/track/update`
4. **实现扫码登录完整流程** — 获取二维码→轮询→保存 token
5. **接入 PyQt6 界面** — 在现有框架上修改
6. **实现多级排序** — 3 层 sort key + 预览 + 确认执行
"""ncm-cli 封装模块"""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from logger import _log

def _get_storage_state_path() -> str:
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "ncm-cli")
    session_dir = os.path.join(config_dir, "session")
    return os.path.join(session_dir, "storage-state.json")


def _load_cookies_from_credentials() -> tuple[str, str]:
    """
    从 ncm-cli 的 credentials.enc.json 获取 cookie
    使用 Node.js 调用 dpapi 解密
    """
    # Node.js 脚本：使用 Windows DPAPI 解密 credentials
    node_script = r"""
const path = require('path');
const fs = require('fs');
const dpapi = require('dpapi');

const homeDir = process.env.USERPROFILE || process.env.HOME;
const credPath = path.join(homeDir, '.config/ncm-cli/credentials.enc.json');

if (!fs.existsSync(credPath)) {
    console.log(JSON.stringify({ music_u: '', csrf: '' }));
    process.exit(0);
}

const data = JSON.parse(fs.readFileSync(credPath, 'utf8'));
const buf = Buffer.from(data.data, 'hex');
const iv = Buffer.from(data.iv, 'hex');
const decrypted = dpapi.decrypt(buf, { iv: iv });
const cred = JSON.parse(decrypted.toString('utf8'));

console.log(JSON.stringify({
    music_u: cred.cookie?.MUSIC_U || '',
    csrf: cred.cookie?.__csrf || cred.cookie?.oscs || ''
}));
"""

    try:
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0 and result.stdout.strip():
            parsed = json.loads(result.stdout.strip())
            _log(f"[_load_cookies_from_credentials] got music_u={bool(parsed.get('music_u'))}, csrf={bool(parsed.get('csrf'))}")
            return parsed.get("csrf", ""), parsed.get("music_u", "")
        else:
            _log(f"[_load_cookies_from_credentials] node failed rc={result.returncode} err={result.stderr[:200]}")
    except Exception as e:
        _log(f"[_load_cookies_from_credentials] exception: {e}")
    return "", ""


def _load_cookies_from_storage_state() -> tuple[str, str]:
    state_path = _get_storage_state_path()
    if not os.path.exists(state_path):
        return "", ""
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        cookies = state.get("cookies", [])
        csrf = ""
        music_u = ""
        for c in cookies:
            name = c.get("name", "")
            if name == "__csrf" or name == "oscs":
                csrf = c.get("value", "")
            if name == "MUSIC_U":
                music_u = c.get("value", "")
        return csrf, music_u
    except Exception:
        return "", ""


def _find_npm() -> str:
    """查找 npm.cmd 路径"""
    possible_npm = [
        r"C:\Program Files\nodejs\npm.cmd",
        r"C:\Program Files (x86)\nodejs\npm.cmd",
    ]
    for p in possible_npm:
        if os.path.exists(p):
            return p
    import shutil
    return shutil.which("npm.cmd") or ""


def run_ncm(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """用系统 npm exec --global 调用全局 ncm-cli（login/logout/check 等基本命令）"""
    npm = _find_npm()
    _log(f"[run_ncm] using npm: {npm}")
    if not npm or not os.path.exists(npm):
        return -1, "", ("错误：未找到 npm。请确保已安装 Node.js。\n"
                           "下载地址：https://nodejs.org/")
    env = {
        **os.environ,
        "USERPROFILE": os.path.expanduser("~"),
        "HOME": os.path.expanduser("~"),
        "XDG_CONFIG_HOME": os.path.join(os.path.expanduser("~"), ".config"),
    }
    cmd = [npm, "exec", "--global", "ncm-cli", "--"] + args
    _log(f"[run_ncm] cmd: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    _log(f"[run_ncm] rc={r.returncode}, stdout_len={len(r.stdout)}, stderr_len={len(r.stderr)}")
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


def run_ncm_global(args: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """用系统 npm exec --global 调用全局 ncm-cli（playlist 等命令）"""
    npm = _find_npm()
    if not npm or not os.path.exists(npm):
        return -1, "", ("错误：未找到 npm。请确保已安装 Node.js。\n"
                           "下载地址：https://nodejs.org/")
    env = {
        **os.environ,
        "USERPROFILE": os.path.expanduser("~"),
        "HOME": os.path.expanduser("~"),
    }
    cmd = [npm, "exec", "--global", "ncm-cli", "--"] + args
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


def _parse_json_output(raw: str) -> dict | None:
    """从 ncm-cli 输出中提取 JSON"""
    text = raw.strip()
    brace = text.find("{")
    if brace >= 0:
        text = text[brace:]
    try:
        return json.loads(text)
    except Exception:
        return None


def ncm_login_check() -> dict:
    rc, out, _ = run_ncm(["login", "--check", "--output", "json"])
    if not (rc == 0 and out.strip()):
        rc, out, _ = run_ncm_global(["login", "--check", "--output", "json"])
    if rc == 0 and out.strip():
        result = _parse_json_output(out)
        if result:
            return result
    return {"success": False}


def ncm_logout() -> bool:
    """退出登录"""
    rc, out, _ = run_ncm(["logout", "--output", "json"])
    return rc == 0


def ncm_login() -> dict | None:
    """发起扫码登录"""
    rc, out, err = run_ncm(["login", "--output", "json"], timeout=8)
    if not (rc == 0 and out.strip()):
        rc, out, err = run_ncm_global(["login", "--output", "json"])
    if rc == 0 and out.strip():
        result = _parse_json_output(out)
        if result:
            return result
    return None


def ncm_get_tracks(playlist_enc_id: str, progress_callback=None, load_publish_time=True) -> tuple[list, list]:
    """获取歌单 tracks（分页获取最多1000首）：返回 (enc_ids列表, tracks_info列表)"""
    _log(f"[ncm_get_tracks] playlistId={playlist_enc_id}")
    all_tracks = []
    offset = 0
    while True:
        rc, out, err = run_ncm_global([
            "playlist", "tracks",
            "--playlistId", playlist_enc_id,
            "--limit", "500",
            "--offset", str(offset),
            "--output", "json"
        ])
        if rc != 0:
            _log(f"[ncm_get_tracks] FAILED at offset={offset}: {err[:300]}")
            break
        parsed = _parse_json_output(out)
        if not parsed:
            _log(f"[ncm_get_tracks] JSON parse error at offset={offset}")
            break
        batch = parsed.get("data") or []
        all_tracks.extend(batch)
        _log(f"[ncm_get_tracks] offset={offset}, got {len(batch)} tracks, total={len(all_tracks)}")
        if len(batch) < 500:
            break
        offset += 500

    # 补充 publishTime（可选）
    album_ids_seen = {}
    if load_publish_time:
        for t in all_tracks:
            al = t.get("album") or t.get("al")
            if isinstance(al, dict):
                al_enc = al.get("id") or al.get("originalId")
                if al_enc:
                    album_ids_seen[al_enc] = None

        if album_ids_seen:
            _log(f"[ncm_get_tracks] fetching publishTime for {len(album_ids_seen)} unique albums via album get")

            def _fetch_album(al_enc):
                rc_al, out_al, _ = run_ncm_global([
                    "album", "get", "--albumId", str(al_enc), "--output", "json"
                ])
                pt = 0
                if rc_al == 0:
                    parsed_al = _parse_json_output(out_al)
                    if parsed_al:
                        pt = parsed_al.get("data", {}).get("publishTime") or 0
                return al_enc, pt

            fetched_count = 0
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(_fetch_album, al_enc): al_enc for al_enc in album_ids_seen}
                for future in as_completed(futures):
                    al_enc, pt = future.result()
                    album_ids_seen[al_enc] = pt
                    fetched_count += 1
                    if progress_callback:
                        progress_callback(fetched_count, len(album_ids_seen))
            _log(f"[ncm_get_tracks] album publishTime results: {dict((k, v) for k, v in album_ids_seen.items())}")

    # 把 publishTime 注入每条 track
    for t in all_tracks:
        al = t.get("album") or t.get("al")
        pt = 0
        if load_publish_time and isinstance(al, dict):
            al_enc = al.get("id") or al.get("originalId")
            if al_enc and al_enc in album_ids_seen:
                pt = album_ids_seen[al_enc] or 0
        t["publishTime"] = pt

    enc_ids = [t["id"] for t in all_tracks]
    return enc_ids, all_tracks


def _do_reorder(playlist_enc_id: str, track_ids: list[str]) -> dict | None:
    """执行单次 ncm-cli playlist reorder"""
    _log(f"[_do_reorder] calling with {len(track_ids)} tracks, playlistId={playlist_enc_id}")
    track_ids_json = json.dumps(track_ids)
    rc, out, err = run_ncm_global([
        "playlist", "reorder",
        "--playlistId", playlist_enc_id,
        "--trackIds", track_ids_json,
        "--output", "json"
    ])
    _log(f"[_do_reorder] rc={rc}, out_len={len(out)}, err_len={len(err)}")
    if rc != 0:
        err_result = _parse_json_output(out) or {}
        err_result["_raw_err"] = err[:500] if err else ""
        err_result["code"] = -1
        _log(f"[_do_reorder] failed: {err_result}")
        return err_result
    result = _parse_json_output(out)
    if result is None:
        _log(f"[_do_reorder] rc=0 but JSON parse failed. out={out[:200]}")
        return {"code": -1, "message": f"JSON parse failed, out={out[:200]}"}
    code = result.get("code")
    data = result.get("data")
    if code != 200 or data is not True:
        _log(f"[_do_reorder] returned code={code}, data={data}")
        result["code"] = code if code else -1
        return result
    _log(f"[_do_reorder] success, code=200")
    return {"code": 200, "data": True}


def ncm_reorder(playlist_enc_id: str, track_ids_ordered: list[str]) -> dict | None:
    """
    调用 ncm-cli playlist reorder，分批执行（每批50首）
    重要：每批包含到当前位置的全部 ID，因为 API 是替换操作
    例如 371 首分批：
      Batch 1: IDs 1-50    → 服务器歌单 = 1-50
      Batch 2: IDs 1-100   → 服务器歌单 = 1-100
      Batch 3: IDs 1-150   → 服务器歌单 = 1-150
      ...
      Batch 8: IDs 1-371   → 服务器歌单 = 1-371
    """
    _log(f"[ncm_reorder] total tracks={len(track_ids_ordered)}")
    batch_size = 50
    all_ok = True
    last_result = None
    total_batches = (len(track_ids_ordered) + batch_size - 1) // batch_size
    for i in range(0, len(track_ids_ordered), batch_size):
        # 关键修复：每批包含从头到当前位置的全部 ID
        # 而不是只包含当前批次的 ID
        batch = track_ids_ordered[:i + batch_size]
        batch_num = i // batch_size + 1
        _log(f"[ncm_reorder] executing batch {batch_num}/{total_batches} with {len(batch)} tracks")
        result = _do_reorder(playlist_enc_id, batch)
        if result is None or result.get("code") != 200:
            _log(f"[ncm_reorder] batch {batch_num} failed: {result}")
            all_ok = False
            last_result = result
        else:
            _log(f"[ncm_reorder] batch {batch_num} success")
    if all_ok:
        return {"code": 200, "data": True}
    return last_result or {"code": -1, "message": "reorder failed"}


def _ncm_reorder_direct(playlist_enc_id: str, track_ids_ordered: list[str]) -> dict | None:
    """
    使用直接 API 调用网易云音乐进行歌单排序（绕过 ncm-cli 命令行长度限制）
    端点：POST /api/v3/playlist/track/update
    参数：ids 是逗号分隔的歌曲 ID 字符串
    """
    import requests

    # 先尝试从 storage_state 获取 cookie
    csrf, music_u = _load_cookies_from_storage_state()
    # 如果没有，尝试从 credentials 解密获取
    if not csrf or not music_u:
        csrf, music_u = _load_cookies_from_credentials()
    if not csrf or not music_u:
        _log("[_ncm_reorder_direct] No cookies found, falling back to ncm-cli")
        return _do_reorder(playlist_enc_id, track_ids_ordered)

    _log(f"[_ncm_reorder_direct] Using direct API with {len(track_ids_ordered)} tracks")

    # 构建请求参数 - ids 是逗号分隔的字符串，不是数组
    ids_str = ",".join(str(tid) for tid in track_ids_ordered)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://music.163.com/",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": f"MUSIC_U={music_u}; __csrf={csrf}",
    }

    data = {
        "ids": ids_str,
    }

    try:
        resp = requests.post(
            "https://music.163.com/api/v3/playlist/track/update",
            data=data,
            headers=headers,
            timeout=30,
        )
        result = resp.json()
        _log(f"[_ncm_reorder_direct] result code={result.get('code')}, message={result.get('message', '')}")
        return result
    except Exception as e:
        _log(f"[_ncm_reorder_direct] exception: {e}")
        return {"code": -1, "message": str(e)}


def ncm_get_playlists() -> list:
    """获取我创建的歌单（分页最多500）"""
    all_playlists = []
    offset = 0
    while True:
        _log(f"[ncm_get_playlists] fetching offset={offset}")
        rc, out, _ = run_ncm_global([
            "playlist", "created",
            "--limit", "500",
            "--offset", str(offset),
            "--output", "json"
        ])
        if rc != 0:
            _log(f"[ncm_get_playlists] rc={rc} at offset={offset}")
            break
        parsed = _parse_json_output(out)
        if not parsed:
            _log(f"[ncm_get_playlists] JSON parse error at offset={offset}")
            break
        records = parsed.get("data", {}).get("records", [])
        total = parsed.get("data", {}).get("recordCount", 0)
        all_playlists.extend(records)
        _log(f"[ncm_get_playlists] offset={offset}, got {len(records)} playlists, total={total}")
        if len(records) < 500 or offset + len(records) >= total:
            break
        offset += 500
    _log(f"[ncm_get_playlists] returning {len(all_playlists)} playlists")
    return all_playlists
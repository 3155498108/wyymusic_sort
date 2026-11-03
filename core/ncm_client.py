"""ncm-cli 封装模块"""
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from logger import _log
from utils.match import (
    FIELD_ARTIST, normalize_keywords, track_matches,
)

# 专辑发行时间缓存：专辑发行时间不会变，持久化后可跳过大量 album get 调用
_ALBUM_PT_CACHE_FILE = os.path.join(tempfile.gettempdir(), "ncm_album_publish_cache.json")
_album_pt_cache: dict[str, int] | None = None


def _load_album_pt_cache() -> dict[str, int]:
    """加载专辑发行时间缓存（内存一次读盘，失败静默降级为空缓存）"""
    global _album_pt_cache
    if _album_pt_cache is None:
        try:
            with open(_ALBUM_PT_CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            _album_pt_cache = {str(k): int(v) for k, v in raw.items() if v}
            _log(f"[album_pt_cache] loaded {len(_album_pt_cache)} entries")
        except Exception:
            _album_pt_cache = {}
    return _album_pt_cache


def _save_album_pt_cache() -> None:
    """原子写入缓存文件"""
    if _album_pt_cache is None:
        return
    try:
        tmp = _ALBUM_PT_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_album_pt_cache, f, ensure_ascii=False)
        os.replace(tmp, _ALBUM_PT_CACHE_FILE)
    except Exception as e:
        _log(f"[album_pt_cache] save failed: {e}")

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


def _get_bundled_ncm_cli() -> str | None:
    """查找打包目录内的 ncm-cli.exe"""
    # PyInstaller 打包后的临时目录
    if hasattr(os, '_MEIPASS'):
        bundled = os.path.join(os._MEIPASS, 'ncm-cli.exe')
        if os.path.exists(bundled):
            return bundled
    # 回退到 exe 所在目录
    exe_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(exe_dir)
    bundled = os.path.join(parent_dir, 'ncm-cli.exe')
    if os.path.exists(bundled):
        return bundled
    return None


def run_ncm(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """用系统 npm exec --global 调用全局 ncm-cli（login/logout/check 等基本命令）
    或使用打包目录内的 ncm-cli.exe"""
    bundled = _get_bundled_ncm_cli()
    if bundled:
        _log(f"[run_ncm] using bundled ncm-cli: {bundled}")
        env = {
            "USERPROFILE": os.path.expanduser("~"),
            "HOME": os.path.expanduser("~"),
            "XDG_CONFIG_HOME": os.path.join(os.path.expanduser("~"), ".config"),
        }
        cmd = [bundled] + args
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        _log(f"[run_ncm] rc={r.returncode}")
        return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")

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
    """用系统 npm exec --global 调用全局 ncm-cli（playlist 等命令）
    或使用打包目录内的 ncm-cli.exe"""
    bundled = _get_bundled_ncm_cli()
    if bundled:
        _log(f"[run_ncm_global] using bundled ncm-cli: {bundled}")
        env = {
            "USERPROFILE": os.path.expanduser("~"),
            "HOME": os.path.expanduser("~"),
        }
        cmd = [bundled] + args
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")

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

    if load_publish_time:
        ncm_fill_publish_time(all_tracks, progress_callback)
    else:
        for t in all_tracks:
            t.setdefault("publishTime", 0)

    enc_ids = [t["id"] for t in all_tracks]
    return enc_ids, all_tracks


def ncm_fill_publish_time(tracks: list[dict], progress_callback=None) -> int:
    """为 tracks 原地补齐专辑发行时间（publishTime，毫秒）

    专辑发行时间不会变化，全部落盘缓存；重复加载同一批专辑几乎不产生请求。
    返回本次新获取的专辑数量。
    """
    album_pt: dict[str, int] = {}
    album_ids: dict[str, None] = {}
    for t in tracks:
        al = t.get("album") or t.get("al")
        if isinstance(al, dict):
            al_enc = al.get("id") or al.get("originalId")
            if al_enc:
                album_ids[str(al_enc)] = None

    fetched = 0
    if album_ids:
        cache = _load_album_pt_cache()
        total_albums = len(album_ids)
        cached = {k: cache[k] for k in album_ids if k in cache}
        album_pt.update(cached)
        missing = [k for k in album_ids if k not in cache]
        _log(f"[ncm_fill_publish_time] {len(cached)} cached / {len(missing)} to fetch")

        if missing:
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

            done = len(cached)
            if progress_callback and cached:
                progress_callback(done, total_albums)
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_fetch_album, al_enc): al_enc for al_enc in missing}
                for future in as_completed(futures):
                    try:
                        al_enc, pt = future.result()
                    except Exception as e:
                        _log(f"[ncm_fill_publish_time] album get exception: {e}")
                        continue
                    if pt:
                        album_pt[al_enc] = pt
                        cache[al_enc] = pt
                        fetched += 1
                    done += 1
                    if progress_callback:
                        progress_callback(done, total_albums)
            _save_album_pt_cache()
            _log(f"[ncm_fill_publish_time] fetched {fetched} album publishTime, cache={len(cache)}")

    for t in tracks:
        al = t.get("album") or t.get("al")
        pt = 0
        if isinstance(al, dict):
            al_enc = al.get("id") or al.get("originalId")
            if al_enc:
                pt = album_pt.get(str(al_enc), 0) or 0
        t["publishTime"] = pt
    return fetched


def _do_reorder(playlist_enc_id: str, track_ids: list[str]) -> dict | None:
    """执行单次 ncm-cli playlist reorder"""
    _log(f"[_do_reorder] calling with {len(track_ids)} tracks, playlistId={playlist_enc_id}")
    # 逗号分隔格式，避免 JSON 数组格式产生的额外字符 []"
    track_ids_csv = ",".join(str(tid) for tid in track_ids)
    rc, out, err = run_ncm_global([
        "playlist", "reorder",
        "--playlistId", playlist_enc_id,
        "--trackIds", track_ids_csv,
        "--output", "json"
    ])
    _log(f"[_do_reorder] rc={rc}, out={out[:500]}, err={err[:200]}")
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
    _log("[_do_reorder] success, code=200")
    return {"code": 200, "data": True}


def ncm_reorder(playlist_enc_id: str, track_ids_ordered: list[str]) -> dict | None:
    """
    调用 ncm-cli playlist reorder，分批执行（每批30首）
    重要：每批包含到当前位置的全部 ID，因为 API 是替换操作
    例如 371 首分批：
      Batch 1: IDs 1-30    → 服务器歌单 = 1-30
      ...
      Batch 13: IDs 1-371  → 服务器歌单 = 1-371
    """
    _log(f"[ncm_reorder] total tracks={len(track_ids_ordered)}")
    batch_size = 30
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


def ncm_create_and_fill_playlist(playlist_name: str, track_ids: list[str], progress_callback=None) -> dict | None:
    """
    创建新歌单并分批添加歌曲（追加到末尾）
    适用于大歌单排序，也适用于小歌单（作为备选方案）
    小歌单（<=200）可以直接用 ncm_reorder 更快，但这个方法更稳定
    """
    _log(f"[ncm_create_and_fill_playlist] name={playlist_name}, total tracks={len(track_ids)}")

    # 创建新歌单
    rc_create, out_create, err_create = run_ncm_global([
        "playlist", "create",
        "--playlistName", playlist_name,
        "--output", "json"
    ])
    if rc_create != 0:
        _log(f"[ncm_create_and_fill_playlist] create failed: {err_create[:300]}")
        return {"code": -1, "message": f"创建歌单失败: {err_create[:200]}"}

    parsed_create = _parse_json_output(out_create)
    if not parsed_create or parsed_create.get("code") != 200:
        _log(f"[ncm_create_and_fill_playlist] create parse error: {out_create[:200]}")
        return {"code": -1, "message": f"创建歌单解析失败: {out_create[:200]}"}

    new_playlist_id = parsed_create.get("data", {}).get("id")
    if not new_playlist_id:
        _log(f"[ncm_create_and_fill_playlist] no playlist id in response: {out_create[:200]}")
        return {"code": -1, "message": f"创建歌单无返回ID: {out_create[:200]}"}

    _log(f"[ncm_create_and_fill_playlist] created playlist id={new_playlist_id}")

    # 分批添加歌曲，每批最多 100 首（JSON 数组格式安全范围内）
    # ncm-cli playlist add 每批内部会反转，批次顺序也会反转
    # 所以：先反转每批 + 倒序添加批次，双重反转修正
    batch_size = 100
    total_batches = (len(track_ids) + batch_size - 1) // batch_size
    # 预处理所有批次
    batches = []
    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i:i + batch_size]
        batches.append(batch)
    # 倒序处理批次 + 每批内部反转
    for bi in range(len(batches) - 1, -1, -1):
        batch = batches[bi]
        # 每批内部反转
        reversed_batch = list(reversed(batch))
        track_ids_json = json.dumps(reversed_batch)
        display_batch = total_batches - bi
        _log(f"[ncm_create_and_fill_playlist] adding batch {display_batch}/{total_batches} with {len(batch)} tracks")

        rc_add, out_add, err_add = run_ncm_global([
            "playlist", "add",
            "--playlistId", new_playlist_id,
            "--songIdList", track_ids_json,
            "--output", "json"
        ])

        if rc_add != 0:
            _log(f"[ncm_create_and_fill_playlist] batch {display_batch} failed: {err_add[:300]}")
            return {"code": -1, "message": f"添加歌曲失败 batch{display_batch}: {err_add[:200]}"}

        parsed_add = _parse_json_output(out_add)
        if not parsed_add or parsed_add.get("code") != 200:
            _log(f"[ncm_create_and_fill_playlist] batch {display_batch} add parse error: {out_add[:200]}")
            return {"code": -1, "message": f"添加歌曲解析失败 batch{display_batch}: {out_add[:200]}"}

        _log(f"[ncm_create_and_fill_playlist] batch {display_batch} success")
        if progress_callback:
            try:
                progress_callback(display_batch, total_batches, f"正在创建歌单... {display_batch}/{total_batches}")
            except TypeError:
                progress_callback(display_batch, total_batches)

    _log(f"[ncm_create_and_fill_playlist] all {total_batches} batches done, playlist id={new_playlist_id}")
    return {
        "code": 200,
        "data": {
            "id": new_playlist_id,
            "name": playlist_name,
            "trackCount": len(track_ids)
        }
    }


def ncm_search_tracks_in_playlists(
    playlist_enc_ids: list[str],
    keywords: list[str],
    fields: list[str] | tuple[str, ...] = ("artist", "album", "song"),
    exclude_keywords: list[str] | None = None,
    progress_callback=None,
    load_publish_time: bool = False,
) -> tuple[list[str], list[dict]]:
    """在多个歌单中按关键词（歌手/专辑/歌名）筛选歌曲并去重

    每个歌单只请求一次（旧实现为了估算进度会把所有歌单抓两遍）。

    Args:
        playlist_enc_ids: 歌单加密ID列表
        keywords: 关键词列表（包含即匹配，会自动归一化）
        fields: 匹配字段，可选 "artist" / "album" / "song"
        exclude_keywords: 排除关键词
        progress_callback: 回调 (current_playlist, total_playlists, status_msg)
        load_publish_time: 是否顺带加载专辑发行时间（筛选一般不需要）

    Returns:
        (enc_ids列表, tracks_info列表)
    """
    include = normalize_keywords(keywords)
    exclude = normalize_keywords(exclude_keywords or [])
    fields = list(fields) or ["artist"]
    total_pls = len(playlist_enc_ids)
    _log(f"[ncm_search_tracks_in_playlists] keywords={include}, exclude={exclude}, "
         f"fields={fields}, playlists={total_pls}")

    if not include:
        return [], []

    seen: set[str] = set()
    result_tracks: list[dict] = []

    for idx, pl_enc_id in enumerate(playlist_enc_ids):
        if progress_callback:
            progress_callback(idx, total_pls,
                              f"正在加载第 {idx + 1}/{total_pls} 个歌单（已匹配 {len(result_tracks)} 首）...")
        _, tracks = ncm_get_tracks(
            pl_enc_id, progress_callback=None, load_publish_time=load_publish_time
        )
        for track in tracks:
            if not track_matches(track, include, exclude, fields):
                continue
            enc_id = track.get("id") or track.get("encId")
            if enc_id and enc_id not in seen:
                seen.add(enc_id)
                result_tracks.append(track)
        _log(f"[ncm_search_tracks_in_playlists] playlist {idx + 1}/{total_pls}: "
             f"{len(tracks)} tracks, total matched={len(result_tracks)}")

    if progress_callback:
        progress_callback(total_pls, total_pls,
                          f"搜索完成，共匹配 {len(result_tracks)} 首")

    _log(f"[ncm_search_tracks_in_playlists] found {len(result_tracks)} unique tracks")
    enc_ids_result = [t.get("id") or t.get("encId") for t in result_tracks]
    return enc_ids_result, result_tracks


def ncm_search_artists_in_playlists(
    playlist_enc_ids: list[str],
    artist_names: list[str],
    progress_callback=None
) -> tuple[list[str], list[dict]]:
    """兼容旧接口：只按歌手名筛选"""
    return ncm_search_tracks_in_playlists(
        playlist_enc_ids, artist_names, fields=(FIELD_ARTIST,),
        progress_callback=progress_callback,
    )


def ncm_search_albums(keyword: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """在线搜索专辑（走 ncm-cli search album）"""
    _log(f"[ncm_search_albums] keyword={keyword}, limit={limit}, offset={offset}")
    rc, out, err = run_ncm_global([
        "search", "album",
        "--keyword", keyword,
        "--limit", str(limit),
        "--offset", str(offset),
        "--output", "json",
    ])
    if rc != 0:
        _log(f"[ncm_search_albums] rc={rc}, err={err[:300]}")
        return []
    parsed = _parse_json_output(out)
    if not parsed or parsed.get("code") != 200:
        _log(f"[ncm_search_albums] bad response: {out[:200]}")
        return []
    data = parsed.get("data") or {}
    records = data.get("records") or []
    _log(f"[ncm_search_albums] got {len(records)} albums (recordCount={data.get('recordCount')})")
    return records


def ncm_get_album_tracks(album_enc_id: str) -> list[dict]:
    """获取某个专辑的全部歌曲"""
    rc, out, err = run_ncm_global([
        "album", "tracks",
        "--albumId", str(album_enc_id),
        "--output", "json",
    ])
    if rc != 0:
        _log(f"[ncm_get_album_tracks] rc={rc} albumId={album_enc_id}, err={err[:200]}")
        return []
    parsed = _parse_json_output(out)
    if not parsed or parsed.get("code") != 200:
        _log(f"[ncm_get_album_tracks] bad response for {album_enc_id}: {out[:200]}")
        return []
    data = parsed.get("data")
    return data if isinstance(data, list) else []


def ncm_collect_album_tracks(
    albums: list[dict],
    progress_callback=None,
    max_workers: int = 3,
) -> tuple[list[str], list[dict]]:
    """批量拉取多个专辑的全部歌曲并按专辑顺序去重合并

    Args:
        albums: [{"id": 专辑加密ID, "name": 专辑名, ...}, ...]
        progress_callback: 回调 (done, total, status_msg)

    Returns:
        (enc_ids列表, tracks列表)
    """
    albums = [a for a in albums if a.get("id")]
    total = len(albums)
    _log(f"[ncm_collect_album_tracks] collecting {total} albums")

    album_tracks: dict[str, list[dict]] = {}
    if total:
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(ncm_get_album_tracks, a["id"]): a for a in albums
            }
            for future in as_completed(futures):
                album = futures[future]
                try:
                    tracks = future.result() or []
                except Exception as e:
                    _log(f"[ncm_collect_album_tracks] album {album.get('id')} failed: {e}")
                    tracks = []
                album_tracks[album["id"]] = tracks
                done += 1
                if progress_callback:
                    progress_callback(
                        done, total,
                        f"正在获取专辑歌曲 {done}/{total}：{album.get('name', '')}",
                    )

    seen: set[str] = set()
    result: list[dict] = []
    for album in albums:
        for track in album_tracks.get(album["id"], []):
            enc_id = track.get("id") or track.get("encId")
            if enc_id and enc_id not in seen:
                seen.add(enc_id)
                result.append(track)

    _log(f"[ncm_collect_album_tracks] collected {len(result)} unique tracks from {total} albums")
    enc_ids = [t.get("id") or t.get("encId") for t in result]
    return enc_ids, result
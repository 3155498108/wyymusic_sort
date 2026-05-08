"""ncm-cli 封装模块"""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from logger import _log


def _find_npm() -> str:
    """查找系统 npm.cmd 的路径"""
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
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


def run_ncm_global(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
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
        if offset >= 1000:
            break

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


def ncm_reorder(playlist_enc_id: str, track_ids_ordered: list[str]) -> dict | None:
    """调用 ncm-cli playlist reorder"""
    track_ids_str = ",".join(track_ids_ordered)
    rc, out, _ = run_ncm_global([
        "playlist", "reorder",
        "--playlistId", playlist_enc_id,
        "--trackIds", track_ids_str,
        "--output", "json"
    ])
    if rc != 0:
        return None
    result = _parse_json_output(out)
    return result


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

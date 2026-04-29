"""
批量查专辑发行时间的辅助脚本。
用法：python fetch_album_publish_times.py
输出：album_publish_times.json（albumId -> publishTime 映射）
"""
import json, time, subprocess, os

def run_ncm_global(args, timeout=30):
    npm = r"C:\Program Files\nodejs\npm.cmd"
    env = {**os.environ, "USERPROFILE": os.path.expanduser("~"), "HOME": os.path.expanduser("~")}
    cmd = [npm, "exec", "--global", "ncm-cli", "--"] + args
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")

def get_album_tracks(album_id, limit=500, offset=0):
    """获取专辑歌曲列表，从中提取第一首的发行时间（同一专辑同一发行时间）"""
    rc, out, err = run_ncm_global([
        "album", "tracks",
        "--albumId", album_id,
        "--limit", str(limit),
        "--offset", str(offset),
        "--output", "json"
    ])
    if rc != 0:
        return None
    text = out.strip()
    brace = text.find("{")
    if brace >= 0:
        text = text[brace:]
    try:
        parsed = json.loads(text)
        data = parsed.get("data", [])
        if data and isinstance(data, list) and len(data) > 0:
            # 专辑歌曲里每首有 publishTime，取第一首的就行
            pt = data[0].get("publishTime")
            return pt
    except:
        pass
    return None

# 从 bangdream_tracks.json 收集所有专辑ID
src = r"E:\jsjzy\pyqt_app\bangdream_tracks.json"
with open(src, 'r', encoding='utf-8', errors='replace') as f:
    tracks = json.load(f)

album_ids = []
seen = set()
for t in tracks:
    al = t.get('al', {})
    if isinstance(al, dict):
        aid = al.get('id')
        if aid and aid not in seen:
            seen.add(aid)
            album_ids.append(str(aid))

print(f"共 {len(album_ids)} 个唯一专辑")

# 用 album tracks 命令查每张专辑
# 但 ncm-cli album tracks 也没有 publishTime...
# 换策略：用 playlist collected 查用户收藏的专辑，然后专辑详情里有 publishTime

# 其实更简单：专辑详情在 ncm-cli 里没有单独命令，但我们可以用 search album 试试
# 或者直接用网易云 web API

# 试一下 album get 命令
rc, out, err = run_ncm_global(["album", "get", "--albumId", album_ids[0], "--output", "json"])
print(f"album get response: {out[:300]}")

# 检查 search album
rc2, out2, err2 = run_ncm_global(["search", "album", "--keywords", "Resonant Strings", "--output", "json"])
print(f"search album response: {out2[:500]}")
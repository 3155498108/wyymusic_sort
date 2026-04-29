"""
根据 bangdream_trackids.json 的 ID 顺序，从播放列表 API 重新拉取 publishTime，
补充到每首歌曲，输出 bangdream_tracks_with_pt.json。
"""
import json, time, requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://music.163.com/',
}

src = r"E:\jsjzy\pyqt_app\bangdream_tracks.json"
out = r"E:\jsjzy\pyqt_app\bangdream_tracks_with_pt.json"

# 从播放列表 API 获取 publishTime
pid = "4943170241"
r = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=headers, timeout=15)
d = r.json()
pl_tracks = d.get("playlist", {}).get("tracks", [])
print(f"播放列表共 {len(pl_tracks)} 首")

# 建立 track_id -> publishTime 的映射
pt_map = {}
for t in pl_tracks:
    tid = t.get("id")
    pt = t.get("publishTime")
    if tid and pt:
        pt_map[tid] = pt

print(f"获取到 {len(pt_map)} 个 publishTime")

# 读取现有 tracks，补充 publishTime
with open(src, 'r', encoding='utf-8', errors='replace') as f:
    tracks = json.load(f)

updated = 0
for t in tracks:
    tid = t.get("id")
    if tid in pt_map:
        t["publishTime"] = pt_map[tid]
        updated += 1

print(f"更新了 {updated}/{len(tracks)} 首的 publishTime")

with open(out, 'w', encoding='utf-8', errors='replace') as f:
    json.dump(tracks, f, ensure_ascii=False, indent=2)

print(f"已保存到 {out}")
print("\npublishTime 示例：")
for aid, pt in list(pt_map.items())[:5]:
    import datetime
    dt = datetime.datetime.fromtimestamp(pt / 1000)
    print(f"  track {aid}: {dt.strftime('%Y-%m-%d')}")
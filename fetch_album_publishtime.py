"""
根据 bangdream_tracks.json 里的专辑ID列表，批量拉取专辑详情，
把 publishTime 补充到每首歌曲的 al 字段里，输出 bangdream_tracks_with_pt.json。
"""
import json, time, requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://music.163.com/',
}

src = r"E:\jsjzy\pyqt_app\bangdream_tracks.json"
out = r"E:\jsjzy\pyqt_app\bangdream_tracks_with_pt.json"

with open(src, 'r', encoding='utf-8') as f:
    tracks = json.load(f)

# 收集所有专辑ID（保持顺序）
album_ids = []
seen = set()
for t in tracks:
    al = t.get('al', {})
    if isinstance(al, dict):
        aid = al.get('id')
        if aid and aid not in seen:
            seen.add(aid)
            album_ids.append(aid)

print(f"共 {len(album_ids)} 个唯一专辑待查询")

album_map = {}
for i in range(0, len(album_ids), 20):
    batch = album_ids[i:i+20]
    ids_str = ','.join(str(aid) for aid in batch)
    try:
        r = requests.get(
            f"https://music.163.com/api/album/detail?id={ids_str}",
            headers=headers, timeout=15
        )
        d = r.json()
        albums = d.get('albums', []) or [d.get('album', {})]
        for al in albums:
            aid = al.get('id')
            pt = al.get('publishTime', 0)
            album_map[aid] = pt
            print(f"  [{aid}] publishTime={pt}")
        time.sleep(0.3)
    except Exception as e:
        print(f"批次 {i//20+1} 失败: {e}")

print(f"\n共拿到 {len(album_map)} 个专辑的发行时间")

# 把 publishTime 写回 tracks
updated = 0
for t in tracks:
    al = t.get('al', {})
    if isinstance(al, dict):
        aid = al.get('id')
        if aid in album_map:
            al['publishTime'] = album_map[aid]
            updated += 1

print(f"更新了 {updated}/{len(tracks)} 首歌曲的专辑发行时间")

with open(out, 'w', encoding='utf-8', errors='replace') as f:
    json.dump(tracks, f, ensure_ascii=False, indent=2)

print(f"已保存到 {out}")
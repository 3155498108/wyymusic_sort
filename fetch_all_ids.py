import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
}

pid = "4943170241"

# 1. 获取 trackIds 列表
r = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=headers, timeout=10)
d = r.json()
pl = d.get("playlist", {})
track_ids_raw = pl.get("trackIds", [])
print(f"trackIds 总数: {len(track_ids_raw)}")
if track_ids_raw:
    print(f"第一个: {track_ids_raw[0]}")

# 2. 批量获取歌曲详情（用逗号分隔 IDs）
all_ids = [str(t['id']) for t in track_ids_raw]
print(f"\n待查询歌曲数: {len(all_ids)}")

# 测试批量查询 - 先查前 1000 个
test_ids = all_ids[:1000]
r2 = requests.get(
    "https://music.163.com/api/v3/song/detail",
    params={"ids": ",".join(test_ids)},
    headers=headers,
    timeout=15
)
d2 = r2.json()
songs = d2.get("songs", [])
print(f"批量查询返回歌曲数: {len(songs)}")
if songs:
    s = songs[0]
    print(f"第一首: name={s.get('name')}, ar={[a.get('name') for a in s.get('ar',[])]}, al={s.get('al',{}).get('name')}")

# 保存 trackIds 供 main.py 使用
with open('E:/jsjzy/pyqt_app/bangdream_trackids.json', 'w', encoding='utf-8') as f:
    json.dump({
        "playlist_id": pid,
        "name": pl.get("name", ""),
        "total": len(all_ids),
        "track_ids": all_ids
    }, f, ensure_ascii=False)
print(f"\n已保存 {len(all_ids)} 个 track ids 到 bangdream_trackids.json")
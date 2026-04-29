import requests, json, time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
}

pid = "4943170241"

# 获取 trackIds（按顺序）
r = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=headers, timeout=10)
d = r.json()
pl = d.get("playlist", {})
track_ids_raw = pl.get("trackIds", [])
ordered_ids = [str(t['id']) for t in track_ids_raw]
print(f"trackIds 总数: {len(ordered_ids)}")
print(f"前5个: {ordered_ids[:5]}")
print(f"后5个: {ordered_ids[-5:]}")

# 批量查歌曲详情，每次 100 个
all_songs = []
for i in range(0, len(ordered_ids), 100):
    batch = ordered_ids[i:i+100]
    # 试 v1 API
    r2 = requests.get(
        "https://music.163.com/api/v1/song/detail",
        params={"ids": ",".join(batch)},
        headers=headers,
        timeout=15
    )
    try:
        d2 = r2.json()
        songs = d2.get("songs", [])
        print(f"批次 {i//100+1}: 拿到 {len(songs)} 首")
        all_songs.extend(songs)
        time.sleep(0.3)
    except Exception as e:
        print(f"批次 {i//100+1} 失败: {e}, text={r2.text[:100]}")

print(f"\n总获取: {len(all_songs)} 首")
if all_songs:
    print(f"第一首: {all_songs[0].get('name')} - {[a.get('name') for a in all_songs[0].get('ar',[])]}")
    print(f"最后一首: {all_songs[-1].get('name')} - {[a.get('name') for a in all_songs[-1].get('ar',[])]}")

    # 保存
    with open('E:/jsjzy/pyqt_app/bangdream_full.json', 'w', encoding='utf-8', errors='replace') as f:
        json.dump([
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "ar": [{"name": a.get("name", "")} for a in s.get("ar", [])],
                "al": {"name": (s.get("al") or {}).get("name", "")}
            }
            for s in all_songs
        ], f, ensure_ascii=False, indent=2)
    print("已保存到 bangdream_full.json")
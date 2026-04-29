import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
}

# Bang Dream 歌单
pid = "4943170241"

# 1. 尝试分页获取所有歌曲
all_tracks = []
for offset in range(0, 1200, 100):
    r = requests.get(
        f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=100",
        params={"id": pid, "n": 100, "offset": offset, "limit": 100},
        headers=headers,
        timeout=10
    )
    d = r.json()
    tracks = d.get('playlist', {}).get('tracks', [])
    if not tracks:
        break
    all_tracks.extend(tracks)
    print(f'offset={offset}: 获取到 {len(tracks)} 首, 累计 {len(all_tracks)} 首')
    if len(tracks) < 100:
        break

print(f'\n总共获取: {len(all_tracks)} 首')

if all_tracks:
    print('第1首:', all_tracks[0].get('name'), 'id:', all_tracks[0].get('id'))
    # 保存
    with open('E:/jsjzy/pyqt_app/bangdream_all.json', 'w', encoding='utf-8') as f:
        json.dump([{'id': t['id'], 'name': t['name'], 'ar': [{'name': a.get('name','')} for a in (t.get('ar') or [])], 'al': {'name': (t.get('al') or {}).get('name', '')}} for t in all_tracks], f, ensure_ascii=False)
    print('已保存到 bangdream_all.json')
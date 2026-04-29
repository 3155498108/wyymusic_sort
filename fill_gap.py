import requests, json, time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
    'Cookie': 'os=linux'
}

# 加载 trackIds
with open('E:/jsjzy/pyqt_app/bangdream_trackids.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
all_ids = data['track_ids']
print(f"总ID数: {len(all_ids)}")

# 先拿前 1000 首（已经有了，跳过）
# 收集缺失的 ID
missing_ids = all_ids[1000:]
print(f"缺失: {len(missing_ids)} 个")

# 尝试单首查询方式，逐个获取（限速）
found = {}
failed = []
for i, sid in enumerate(missing_ids):
    r = requests.get(f"https://music.163.com/api/v3/playlist/detail?id=4943170241&n=1&offset=0", headers=headers, timeout=10)
    time.sleep(0.1)
    if (i+1) % 20 == 0:
        print(f"进度: {i+1}/{len(missing_ids)}")

# 换个思路：试试 /api/song/player/detail
print("\n尝试 /api/song/player/detail")
r = requests.get(
    "https://music.163.com/api/song/player/detail",
    params={"id": missing_ids[0] if missing_ids else all_ids[1000]},
    headers=headers, timeout=10
)
print(f"code={r.json().get('code')}, keys={list(r.json().keys())}")
print(f"text={r.text[:200]}")

# 试试 v2 格式
print("\n尝试 /api/v2/playlist/track")
r2 = requests.get(
    "https://music.163.com/api/v2/playlist/track",
    params={"id": "4943170241", "n": 1148, "offset": 0, "total": "true"},
    headers=headers, timeout=10
)
d2 = r2.json()
print(f"code={d2.get('code')}, tracks={len(d2.get('tracks', []))}, keys={list(d2.keys())[:10]}")

# 试试小程序接口
print("\n尝试 /api/playlist/v2/track")
r3 = requests.get(
    "https://music.163.com/api/playlist/v2/track",
    params={"id": "4943170241"},
    headers=headers, timeout=10
)
d3 = r3.json()
print(f"code={d3.get('code')}, keys={list(d3.keys())[:10]}")
if d3.get('tracks'):
    print(f"tracks={len(d3['tracks'])}")
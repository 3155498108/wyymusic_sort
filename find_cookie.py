import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
}

pid = "4943170241"

# 测试哪个 cookie 参数导致返回 1000 tracks
test_cookies = [
    "appver=1.0; os=linux; channel=",
    "appver=1.0; os=pc; channel=",
    "appver=; os=linux; channel=",
    "appver=1.0; os=linux; channel=web",
    "appver=1.0; os=windows; channel=",
    "os=linux; channel=",
    "appver=1.0; channel=",
    "appver=; os=; channel=",
    # 最简版
    "appver=1.0",
    "os=linux",
    "channel=",
]

for ck in test_cookies:
    h2 = {**headers, 'Cookie': ck}
    r = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=h2, timeout=10)
    d = r.json()
    tracks = d.get("playlist", {}).get("tracks", [])
    print(f"Cookie='{ck}': tracks={len(tracks)}, trackCount={d.get('playlist',{}).get('trackCount',0)}")

# 找到关键参数后，测试是否能返回更多（接近 1148）
print("\n=== 验证最优 cookie ===")
best_cookie = "appver=1.0; os=linux; channel="
h3 = {**headers, 'Cookie': best_cookie}
r2 = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=h3, timeout=15)
d2 = r2.json()
pl2 = d2.get("playlist", {})
tracks2 = pl2.get("tracks", [])
print(f"tracks: {len(tracks2)}, trackCount: {pl2.get('trackCount')}")
if tracks2:
    print(f"first: {tracks2[0].get('name')} | {[a.get('name') for a in tracks2[0].get('ar',[])]}")
    print(f"last: {tracks2[-1].get('name')} | {[a.get('name') for a in tracks2[-1].get('ar',[])]}")
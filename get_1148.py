import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
    'Cookie': 'os=linux',
}

pid = "4943170241"

# 用 os=linux 先拿 1000，看看有没有更多
r = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=headers, timeout=15)
d = r.json()
pl = d.get("playlist", {})
tracks = pl.get("tracks", [])
print(f"os=linux + n=1000000: tracks={len(tracks)}, trackCount={pl.get('trackCount')}")

# 用 offset 看能不能再拿到更多
for offset in [0, 1000]:
    r2 = requests.get(
        f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000&offset={offset}",
        headers=headers, timeout=15
    )
    d2 = r2.json()
    tracks2 = d2.get("playlist", {}).get("tracks", [])
    print(f"offset={offset}: tracks={len(tracks2)}")
    if tracks2:
        print(f"  first: {tracks2[0].get('name')}")

# 试试 os=android
h_android = {**headers, 'Cookie': 'os=android'}
r3 = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=h_android, timeout=15)
d3 = r3.json()
tracks3 = d3.get("playlist", {}).get("tracks", [])
print(f"\nos=android: tracks={len(tracks3)}, trackCount={d3.get('playlist',{}).get('trackCount')}")

# 试试 os=linux + total=true
h_linux = {**headers, 'Cookie': 'os=linux'}
r4 = requests.get(
    f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000&total=true",
    headers=h_linux, timeout=15
)
d4 = r4.json()
tracks4 = d4.get("playlist", {}).get("tracks", [])
print(f"\nos=linux + total=true: tracks={len(tracks4)}")

# 核心发现：也许 os=linux 的版本支持 n>1000？
# 测试 n=2000
r5 = requests.get(
    f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=2000",
    headers=h_linux, timeout=15
)
d5 = r5.json()
tracks5 = d5.get("playlist", {}).get("tracks", [])
print(f"\nos=linux + n=2000: tracks={len(tracks5)}")

# n=1148
r6 = requests.get(
    f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1148",
    headers=h_linux, timeout=15
)
d6 = r6.json()
tracks6 = d6.get("playlist", {}).get("tracks", [])
print(f"os=linux + n=1148: tracks={len(tracks6)}")

# 用 ncm-cli 的 cookies 试试
import os
ncm_cookie_path = r"C:\Users\spenc\.config\ncm-cli\cookies.json"
if os.path.exists(ncm_cookie_path):
    with open(ncm_cookie_path, 'r') as f:
        ncm_cookies = json.load(f)
    cookie_str = "; ".join(f"{k}={v}" for k, v in ncm_cookies.items())
    h_ncm = {**headers, 'Cookie': cookie_str}
    r7 = requests.get(f"https://music.163.com/api/v3/playlist/detail?id={pid}&n=1000000", headers=h_ncm, timeout=15)
    d7 = r7.json()
    tracks7 = d7.get("playlist", {}).get("tracks", [])
    print(f"\nncm-cli cookies: tracks={len(tracks7)}")
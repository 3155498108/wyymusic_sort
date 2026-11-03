"""关键词匹配工具（歌手 / 专辑 / 歌曲名 模糊匹配）

匹配规则：
- 归一化：NFKC（全角转半角）+ 转小写 + 去掉所有空白
  这样「逆転裁判 4」和「逆転裁判4」、「OST（限定）」和「ost(限定)」都能互相匹配
- 包含即命中（模糊匹配）
- 多个关键词之间是「或」关系
- 以 - 或 ! 开头的行表示排除关键词

纯函数模块，不发任何网络请求，方便单独测试。
"""
import re
import unicodedata

FIELD_ARTIST = "artist"
FIELD_ALBUM = "album"
FIELD_SONG = "song"

FIELD_LABELS = {
    FIELD_ARTIST: "歌手",
    FIELD_ALBUM: "专辑",
    FIELD_SONG: "歌曲名",
}

_SPLIT_RE = re.compile(r"[,，|｜/、]")
_WS_RE = re.compile(r"\s+")


def normalize(text) -> str:
    """归一化文本：NFKC → casefold → 去掉空白"""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).casefold()
    if not s:
        return ""
    return _WS_RE.sub("", s)


def parse_keywords(raw: str) -> tuple[list[str], list[str]]:
    """把用户输入的多行文本解析为 (包含关键词, 排除关键词)

    每行一个关键词，一行内也支持用逗号/竖线/斜杠分隔多个；
    以 - 或 ! 开头的行/片段为排除项。
    """
    include: list[str] = []
    exclude: list[str] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        neg = line[0] in "-!"
        body = line[1:] if neg else line
        for part in _SPLIT_RE.split(body):
            val = normalize(part)
            if not val:
                continue
            (exclude if neg else include).append(val)
    # 去重但保持顺序
    include = list(dict.fromkeys(include))
    exclude = list(dict.fromkeys(exclude))
    return include, exclude


def normalize_keywords(keywords) -> list[str]:
    """把已拆分的关键词列表归一化（支持传入原始字符串列表）"""
    if not keywords:
        return []
    if isinstance(keywords, str):
        return parse_keywords(keywords)[0]
    return list(dict.fromkeys(normalize(k) for k in keywords if normalize(k)))


def artist_text(track: dict) -> str:
    """取一首歌的艺人文本（多个艺人和声用 / 连接）"""
    artists = (track.get("fullArtists") or track.get("artists")
               or track.get("ar") or [])
    names = []
    for a in artists:
        if isinstance(a, dict):
            name = a.get("name", "")
            if name:
                names.append(name)
    return " / ".join(names)


def album_text(track: dict) -> str:
    """取一首歌的专辑名"""
    al = track.get("album") or track.get("al")
    if isinstance(al, dict):
        return al.get("name", "") or ""
    if isinstance(al, str):
        return al
    return ""


def song_text(track: dict) -> str:
    return track.get("name", "") or ""


def track_fields_text(track: dict, fields) -> list[str]:
    """按指定字段取出待匹配文本（已归一化）"""
    texts = []
    for field in fields:
        if field == FIELD_ARTIST:
            texts.append(normalize(artist_text(track)))
        elif field == FIELD_ALBUM:
            texts.append(normalize(album_text(track)))
        elif field == FIELD_SONG:
            texts.append(normalize(song_text(track)))
    return [t for t in texts if t]


def match_texts(texts: list[str], include: list[str], exclude: list[str]) -> bool:
    """归一化文本列表 vs 关键词清单"""
    if not include:
        return False
    if not any(k in t for k in include for t in texts):
        return False
    if exclude and any(x in t for x in exclude for t in texts):
        return False
    return True


def track_matches(track: dict, include: list[str], exclude: list[str], fields) -> bool:
    """判断一首歌是否命中关键词"""
    if not include:
        return False
    texts = track_fields_text(track, fields)
    return match_texts(texts, include, exclude)


def filter_tracks(tracks: list[dict], include: list[str], exclude: list[str], fields) -> list[dict]:
    """过滤出命中的歌曲（保持原顺序）"""
    return [t for t in tracks if track_matches(t, include, exclude, fields)]


def group_by_album(tracks: list[dict]) -> list[dict]:
    """按专辑分组，返回 [{name, artists, album_id, tracks}]

    分组顺序按首次出现顺序，组内保持原顺序（便于按歌单顺序收歌）。
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for tr in tracks:
        al = tr.get("album") or tr.get("al") or {}
        album_name = (al.get("name") if isinstance(al, dict) else "") or "（未知专辑）"
        album_id = (al.get("id") or al.get("originalId")) if isinstance(al, dict) else ""
        key = str(album_id) if album_id else f"name:{album_name}"
        if key not in groups:
            groups[key] = {
                "key": key,
                "name": album_name,
                "album_id": album_id,
                "artists": artist_text(tr),
                "tracks": [],
            }
            order.append(key)
        groups[key]["tracks"].append(tr)
    return [groups[k] for k in order]

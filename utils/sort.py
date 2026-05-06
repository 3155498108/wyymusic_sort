"""排序算法模块"""
import re
from collections import defaultdict


def sort_by_custom_order(tracks: list[dict], custom_order: list[str]) -> tuple[list[dict], list[str]]:
    """按自定义歌曲名单顺序排列tracks，返回 (ordered, unmatched)"""
    if not custom_order:
        return tracks, []

    name_to_tr = {}
    for tr in tracks:
        name = tr.get("name", "").strip()
        if name:
            name_to_tr[name] = tr

    ordered = []
    unmatched = []
    for name in custom_order:
        matched = None
        if name in name_to_tr:
            matched = name_to_tr.pop(name)
        else:
            clean = re.sub(r"[（(].*?[）)]", "", name).strip()
            for k, v in list(name_to_tr.items()):
                k_clean = re.sub(r"[（(].*?[）)]", "", k).strip()
                if k_clean == clean:
                    matched = name_to_tr.pop(k)
                    break
        if matched:
            ordered.append(matched)
        else:
            unmatched.append(name)

    for tr in tracks:
        if tr not in ordered:
            ordered.append(tr)

    return ordered, unmatched


def sort_multi_level(tracks: list[dict], levels: list[tuple[str, bool]],
                    custom_order: list[str] | None = None) -> list[dict]:
    """
    多级排序主函数。

    Args:
        tracks: 当前歌单的tracks列表
        levels: 排序层级列表，每项为 (字段名, 是否降序)
                字段名可选: "艺人", "专辑", "歌曲名", "入库时间", "专辑发行时间", "自定义顺序"
        custom_order: 自定义顺序歌曲名列表（当 levels 包含"自定义顺序"时传入）

    Returns:
        排序后的tracks列表
    """
    # 特殊处理：艺人 primary + 入库时间 secondary
    is_artist_primary = len(levels) >= 1 and levels[0][0] == "艺人"
    is_addtime_secondary = len(levels) >= 2 and levels[1][0] == "入库时间"

    if len(levels) == 2 and is_artist_primary and is_addtime_secondary:
        group_dir = levels[1][1]
        within_dir = levels[0][1]

        groups = defaultdict(list)
        for tr in tracks:
            ar = tr.get("fullArtists") or tr.get("artists") or tr.get("ar") or []
            primary = ar[0].get("name", "") if ar else ""
            groups[primary].append(tr)

        groups_list = [(p, list(s)) for p, s in groups.items()]

        for p, s in groups_list:
            s.sort(key=lambda tr: tr.get("_addTime", 0), reverse=within_dir)

        if group_dir:
            groups_list.sort(key=lambda g: max(tr.get("_addTime", 0) for tr in g[1]), reverse=True)
        else:
            groups_list.sort(key=lambda g: min(tr.get("_addTime", 0) for tr in g[1]), reverse=False)

        ordered = []
        for p, s in groups_list:
            ordered.extend(s)
        return ordered

    # 标准多级稳定排序
    ordered = list(tracks)
    for field, reverse in levels:
        if field == "自定义顺序":
            if custom_order:
                ordered, _ = sort_by_custom_order(ordered, custom_order)
        elif field == "艺人":
            def _key(tr): return "/".join(
                a.get("name", "") for a in (tr.get("ar") or []) if a.get("name")
            )
            ordered.sort(key=_key, reverse=reverse)
        elif field == "专辑":
            def _key(tr): return (tr.get("al") or {}).get("name", "") if isinstance(tr.get("al"), dict) else ""
            ordered.sort(key=_key, reverse=reverse)
        elif field == "歌曲名":
            def _key(tr): return tr.get("name", "")
            ordered.sort(key=_key, reverse=reverse)
        elif field == "入库时间":
            def _key(tr): return tr.get("_addTime", 0)
            ordered.sort(key=_key, reverse=reverse)
        elif field == "专辑发行时间":
            def _key(tr): return tr.get("publishTime", 0)
            ordered.sort(key=_key, reverse=reverse)

    return ordered

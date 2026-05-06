"""Excel 导入导出模块"""
import openpyxl


def export_table_to_excel(table, playlist_name: str, path: str) -> int:
    """
    将 QTableWidget 的内容导出到 Excel 文件。

    Args:
        table: QTableWidget 实例
        playlist_name: 歌单名称（用于默认文件名）
        path: 保存路径

    Returns:
        导出的行数

    Raises:
        Exception: 写入失败时
    """
    rows = table.rowCount()
    if rows == 0:
        return 0

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "歌曲排序"
    ws.append(["序号", "歌曲名", "艺人", "专辑", "加密ID", "入库时间"])
    for r in range(rows):
        row_data = []
        for c in range(6):
            item = table.item(r, c)
            row_data.append(item.text() if item else "")
        ws.append(row_data)
    wb.save(path)
    return rows


def import_tracks_from_excel(
    path: str,
    current_tracks: list[dict],
) -> tuple[list[dict], int]:
    """
    从 Excel 文件导入歌曲顺序。

    Args:
        path: Excel 文件路径
        current_tracks: 当前歌单的 tracks 列表

    Returns:
        (ordered_tracks, missing_count)

    Raises:
        Exception: 读取失败时
    """
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    rows_data = list(ws.iter_rows(min_row=2, values_only=True))  # skip header
    if not rows_data:
        return [], 0

    encid_to_tr = {tr.get("encId"): tr for tr in current_tracks if tr.get("encId")}
    ordered = []
    missing = 0
    for row in rows_data:
        seq, name, artist, album, enc_id, add_time = (row[i] if i < len(row) else None for i in range(6))
        if not enc_id:
            continue
        tr = encid_to_tr.get(enc_id)
        if tr:
            ordered.append(tr)
        else:
            missing += 1
    return ordered, missing

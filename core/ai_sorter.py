"""AI 排序核心模块"""
import json
import os
from typing import Optional

from logger import _log

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from constants import CONFIG_FILE


def _load_ai_config() -> dict:
    """从 config.json 加载 AI 配置"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _build_track_list_text(tracks: list[dict]) -> str:
    """将 tracks 列表转为文本，方便发给 AI"""
    lines = []
    for i, tr in enumerate(tracks, 1):
        name = tr.get("name", "?")
        artists = "/".join(a.get("name", "") for a in tr.get("ar", []) if a.get("name"))
        album = (tr.get("al") or {}).get("name", "?") if isinstance(tr.get("al"), dict) else "?"
        enc_id = tr.get("encId", tr.get("id", ""))
        add_time = tr.get("_addTime", 0) or tr.get("addTime", 0)
        if add_time:
            import datetime
            dt = datetime.datetime.fromtimestamp(add_time / 1000)
            add_time_str = dt.strftime("%Y-%m-%d")
        else:
            add_time_str = "-"
        lines.append(f"{i}. [{enc_id}] {name} - {artists} | 专辑: {album} | 入库: {add_time_str}")
    return "\n".join(lines)


def ask_ai_sort(tracks: list[dict], user_prompt: str, progress_callback=None) -> Optional[list[str]]:
    """
    调用 AI 对歌单进行排序

    Args:
        tracks: 当前歌单的 tracks 列表
        user_prompt: 用户的排序要求
        progress_callback: 进度回调 (可选)

    Returns:
        排序后的 enc_id 列表，失败返回 None
    """
    config = _load_ai_config()
    provider = config.get("ai_provider", "openai")
    api_key = config.get("ai_api_key", "")

    if not api_key:
        _log("[ask_ai_sort] No API key configured")
        return None

    # 构建歌曲列表文本
    track_text = _build_track_list_text(tracks)
    total = len(tracks)

    if progress_callback:
        progress_callback(0, total, "正在准备数据...")

    # 构建 prompt
    system_prompt = """你是一个歌单排序助手。用户会给你一个歌单（包含歌曲ID、名称、艺人、专辑、入库时间），以及排序要求。
你需要根据要求对歌单进行排序，返回排序后的歌曲 ID 列表。

要求：
1. 严格按用户要求的排序规则执行
2. 如果有特殊要求（如某歌手的歌放前面），优先处理
3. 只返回 JSON 格式的 ID 列表，不要其他内容
4. ID 必须来自原始歌单，不要凭空创造

返回格式：
{"order": ["id1", "id2", "id3", ...]}"""

    user_msg = f"""歌单共 {total} 首歌曲：

{track_text}

排序要求：{user_prompt}

请返回排序后的歌曲 ID 列表（JSON 格式）。"""

    if progress_callback:
        progress_callback(0, total, "正在调用 AI...")

    try:
        if provider == "openai":
            result = _call_openai(api_key, config.get("ai_model", ""), system_prompt, user_msg)
        elif provider == "anthropic":
            result = _call_anthropic(api_key, config.get("ai_model", ""), system_prompt, user_msg)
        elif provider == "local":
            result = _call_local(api_key, system_prompt, user_msg)
        else:
            _log(f"[ask_ai_sort] Unknown provider: {provider}")
            return None

        if result is None:
            return None

        # 解析 JSON 结果
        try:
            data = json.loads(result)
            order = data.get("order", [])
            if isinstance(order, list) and order:
                _log(f"[ask_ai_sort] Success, got {len(order)} ordered ids")
                if progress_callback:
                    progress_callback(total, total, "排序完成")
                return order
        except json.JSONDecodeError:
            _log(f"[ask_ai_sort] Failed to parse JSON: {result[:200]}")

    except Exception as e:
        _log(f"[ask_ai_sort] Exception: {e}")

    return None


def _call_openai(api_key: str, model: str, system_prompt: str, user_msg: str) -> Optional[str]:
    """调用 OpenAI API"""
    if OpenAI is None:
        _log("[_call_openai] openai package not installed")
        return None

    client = OpenAI(api_key=api_key)
    actual_model = model.strip() if model else "gpt-4o-mini"

    _log(f"[_call_openai] calling {actual_model}")

    response = client.chat.completions.create(
        model=actual_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content


def _call_anthropic(api_key: str, model: str, system_prompt: str, user_msg: str) -> Optional[str]:
    """调用 Anthropic Claude API"""
    if Anthropic is None:
        _log("[_call_anthropic] anthropic package not installed")
        return None

    client = Anthropic(api_key=api_key)
    actual_model = model.strip() if model else "claude-sonnet-4-20250514"

    _log(f"[_call_anthropic] calling {actual_model}")

    response = client.messages.create(
        model=actual_model,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_msg},
        ],
    )

    return response.content[0].text


def _call_local(api_key: str, system_prompt: str, user_msg: str) -> Optional[str]:
    """调用本地 Ollama（OpenAI-compatible API）"""
    import requests

    # api_key 可能是 Ollama 的地址（如 http://localhost:11434）
    base_url = api_key.rstrip("/")

    _log(f"[_call_local] calling {base_url}")

    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": "llama3",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.3,
            },
            timeout=120,
        )
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            _log(f"[_call_local] HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        _log(f"[_call_local] Exception: {e}")

    return None
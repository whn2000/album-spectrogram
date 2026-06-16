"""
metadata.py — FLAC 元数据读取与 Tracklist 提取

功能：
  - 读取单个 FLAC 文件的 Vorbis Comment 标签
  - 批量扫描文件夹，提取完整的专辑 tracklist
  - 格式化输出（纯文本 / BBCode / Markdown）
"""

import os
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

from mutagen.flac import FLAC

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 单文件元数据读取
# ---------------------------------------------------------------------------

def read_flac_metadata(filepath: str) -> dict:
    """
    读取单个 FLAC 文件的元数据标签及音频信息。

    返回:
        {
            "title": str,
            "artist": str,
            "album": str,
            "albumartist": str,
            "tracknumber": str,
            "discnumber": str,
            "genre": str,
            "date": str,
            "duration": float,        # 秒
            "duration_fmt": str,       # "MM:SS"
            "sample_rate": int,        # Hz
            "channels": int,
            "bits_per_sample": int,
            "bitrate": int,            # bps
        }
    """
    try:
        audio = FLAC(filepath)
    except Exception as e:
        logger.error("无法读取 FLAC 文件 [%s]: %s", filepath, e)
        return _empty_metadata(filepath)

    def _tag(key: str, default: str = "Unknown") -> str:
        """安全获取标签值（Vorbis Comment 值为列表）。"""
        values = audio.get(key)
        if values and len(values) > 0:
            return str(values[0]).strip()
        return default

    # 时长
    duration = audio.info.length if audio.info else 0.0

    return {
        "title": _tag("title", os.path.splitext(os.path.basename(filepath))[0]),
        "artist": _tag("artist", "Unknown Artist"),
        "album": _tag("album", "Unknown Album"),
        "albumartist": _tag("albumartist", _tag("artist", "Unknown Artist")),
        "tracknumber": _normalize_track_number(_tag("tracknumber", "0")),
        "discnumber": _tag("discnumber", "1"),
        "genre": _tag("genre", ""),
        "date": _tag("date", ""),
        "duration": round(duration, 2),
        "duration_fmt": _format_duration(duration),
        "sample_rate": audio.info.sample_rate if audio.info else 0,
        "channels": audio.info.channels if audio.info else 0,
        "bits_per_sample": audio.info.bits_per_sample if audio.info else 0,
        "bitrate": audio.info.bitrate if audio.info else 0,
    }


def _empty_metadata(filepath: str) -> dict:
    """返回空的元数据字典（用于读取失败的情况）。"""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    return {
        "title": basename,
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "albumartist": "Unknown Artist",
        "tracknumber": "0",
        "discnumber": "1",
        "genre": "",
        "date": "",
        "duration": 0.0,
        "duration_fmt": "0:00",
        "sample_rate": 0,
        "channels": 0,
        "bits_per_sample": 0,
        "bitrate": 0,
    }


def _normalize_track_number(raw: str) -> str:
    """
    标准化曲号，处理 "1/12" 格式，返回纯数字字符串。
    """
    if "/" in raw:
        raw = raw.split("/")[0]
    try:
        return str(int(raw))
    except (ValueError, TypeError):
        return "0"


def _format_duration(seconds: float) -> str:
    """将秒数格式化为 MM:SS 字符串。"""
    if seconds <= 0:
        return "0:00"
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


# ---------------------------------------------------------------------------
# 2. 文件夹级 Tracklist 提取
# ---------------------------------------------------------------------------

def extract_tracklist(folder_path: str) -> list[dict]:
    """
    扫描文件夹中的所有 FLAC 文件，按文件夹分组提取 tracklist。

    返回:
        [
            {
                "folder": str,
                "album_name": str,
                "artist": str,
                "albumartist": str,
                "date": str,
                "genre": str,
                "audio_info": { "sample_rate", "bits_per_sample", "channels" },
                "tracks": [
                    { "number": str, "title": str, "artist": str, "duration": float, "duration_fmt": str },
                    ...
                ],
                "total_duration": float,
                "total_duration_fmt": str,
            },
            ...
        ]
    """
    root = Path(folder_path)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"路径不存在或不是目录: {folder_path}")

    # 按文件夹分组收集 FLAC 文件
    folder_files: dict[str, list[str]] = defaultdict(list)
    for flac_file in sorted(root.rglob("*.flac")):
        parent = str(flac_file.parent)
        folder_files[parent].append(str(flac_file))

    if not folder_files:
        return []

    albums = []
    for folder, files in sorted(folder_files.items()):
        tracks_meta = []
        for f in sorted(files):
            meta = read_flac_metadata(f)
            tracks_meta.append(meta)

        # 按曲号排序
        tracks_meta.sort(key=lambda m: (m["discnumber"], int(m["tracknumber"] or "0")))

        # 从第一首歌获取专辑级别信息
        first = tracks_meta[0] if tracks_meta else {}
        total_duration = sum(t["duration"] for t in tracks_meta)

        # 生成相对路径作为显示名称
        rel_path = os.path.relpath(folder, folder_path)
        display_name = rel_path if rel_path != "." else os.path.basename(
            os.path.abspath(folder_path)
        )

        albums.append({
            "folder": folder,
            "album_name": first.get("album", display_name),
            "artist": first.get("albumartist", first.get("artist", "Unknown Artist")),
            "albumartist": first.get("albumartist", ""),
            "date": first.get("date", ""),
            "genre": first.get("genre", ""),
            "audio_info": {
                "sample_rate": first.get("sample_rate", 0),
                "bits_per_sample": first.get("bits_per_sample", 0),
                "channels": first.get("channels", 0),
            },
            "tracks": [
                {
                    "number": t["tracknumber"],
                    "title": t["title"],
                    "artist": t["artist"],
                    "duration": t["duration"],
                    "duration_fmt": t["duration_fmt"],
                }
                for t in tracks_meta
            ],
            "total_duration": round(total_duration, 2),
            "total_duration_fmt": _format_duration(total_duration),
        })

    return albums


# ---------------------------------------------------------------------------
# 3. Tracklist 文本格式化
# ---------------------------------------------------------------------------

def format_tracklist(
    album_data: dict,
    fmt: str = "plain",
) -> str:
    """
    将 tracklist 数据格式化为可复制的文本。

    参数:
        album_data:  extract_tracklist() 返回的单个专辑字典
        fmt:         'plain' | 'bbcode' | 'markdown'

    返回:
        格式化后的字符串
    """
    tracks = album_data.get("tracks", [])
    album_name = album_data.get("album_name", "Unknown Album")
    artist = album_data.get("artist", "Unknown Artist")
    date = album_data.get("date", "")
    total_fmt = album_data.get("total_duration_fmt", "0:00")

    if fmt == "bbcode":
        return _format_bbcode(album_name, artist, date, tracks, total_fmt)
    elif fmt == "markdown":
        return _format_markdown(album_name, artist, date, tracks, total_fmt)
    else:
        return _format_plain(album_name, artist, date, tracks, total_fmt)


def _format_plain(
    album: str, artist: str, date: str,
    tracks: list[dict], total: str,
) -> str:
    """纯文本格式。"""
    lines = []
    header = f"{artist} - {album}"
    if date:
        header += f" ({date})"
    lines.append(header)
    lines.append("-" * len(header))
    for t in tracks:
        num = t["number"].zfill(2)
        lines.append(f"{num}. {t['title']}  [{t['duration_fmt']}]")
    lines.append("")
    lines.append(f"Total: {total}")
    return "\n".join(lines)


def _format_bbcode(
    album: str, artist: str, date: str,
    tracks: list[dict], total: str,
) -> str:
    """BBCode 格式（适用于论坛发帖）。"""
    lines = []
    header = f"{artist} - {album}"
    if date:
        header += f" ({date})"
    lines.append(f"[b]{header}[/b]")
    lines.append("")
    for t in tracks:
        num = t["number"].zfill(2)
        lines.append(f"{num}. {t['title']}  [color=#888][{t['duration_fmt']}][/color]")
    lines.append("")
    lines.append(f"[b]Total: {total}[/b]")
    return "\n".join(lines)


def _format_markdown(
    album: str, artist: str, date: str,
    tracks: list[dict], total: str,
) -> str:
    """Markdown 格式。"""
    lines = []
    header = f"{artist} - {album}"
    if date:
        header += f" ({date})"
    lines.append(f"### {header}")
    lines.append("")
    lines.append("| # | Title | Duration |")
    lines.append("|---|-------|----------|")
    for t in tracks:
        num = t["number"].zfill(2)
        lines.append(f"| {num} | {t['title']} | {t['duration_fmt']} |")
    lines.append("")
    lines.append(f"**Total: {total}**")
    return "\n".join(lines)

"""
spectrogram.py — 核心逻辑：SoX 频谱图生成 + Pillow 图片拼接

功能：
  - 递归扫描文件夹中的 .flac 文件
  - 使用 SoX 为每个音频生成频谱图
  - 按文件夹分组拼接频谱图
"""

import os
import subprocess
import uuid
import logging
import tempfile
from pathlib import Path
from collections import defaultdict
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 文件夹递归扫描
# ---------------------------------------------------------------------------

def scan_for_flac(root_path: str) -> dict[str, list[str]]:
    """
    递归扫描目录，查找所有 .flac 文件。
    按直接父文件夹分组返回：{ folder_path: [sorted .flac paths] }
    支持任意深度的嵌套文件夹。
    """
    albums = defaultdict(list)
    root = Path(root_path)

    if not root.exists():
        raise FileNotFoundError(f"路径不存在: {root_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"不是有效目录: {root_path}")

    for flac_file in sorted(root.rglob("*.flac")):
        parent = str(flac_file.parent)
        albums[parent].append(str(flac_file))

    # 每个文件夹内按文件名排序
    for folder in albums:
        albums[folder].sort()

    return dict(albums)


# ---------------------------------------------------------------------------
# 2. SoX 频谱图生成
# ---------------------------------------------------------------------------

def generate_spectrogram(
    audio_path: str,
    output_path: str,
    width: int = 1920,
    height: int = 400,
    dynamic_range: int = 90,
) -> str:
    """
    使用 SoX 生成单个 FLAC 文件的频谱图 PNG。

    命令: sox input.flac -n spectrogram -x <w> -y <h> -z <dB> -o output.png
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "sox",
        audio_path,
        "-n",
        "spectrogram",
        "-x", str(width),
        "-y", str(height),
        "-z", str(dynamic_range),
        "-o", output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "未找到 sox 命令，请先安装: sudo apt install sox libsox-fmt-all"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"SoX 处理失败 [{os.path.basename(audio_path)}]: {result.stderr.strip()}"
        )

    return output_path


# ---------------------------------------------------------------------------
# 3. 频谱图拼接
# ---------------------------------------------------------------------------

def _load_font(size: int = 14):
    """尝试加载系统字体，失败则使用默认字体。"""
    font_paths = [
        # Docker (Debian) — fonts-noto-cjk
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        # Linux — DejaVu / Liberation
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def stitch_spectrograms(
    image_paths: list[str],
    output_path: str,
    direction: str = "vertical",
    gap: int = 2,
    labels: Optional[list[str]] = None,
) -> str:
    """
    将多张频谱图拼接为一张大图。

    参数:
        image_paths: 频谱图文件路径列表
        output_path: 输出文件路径
        direction:   'vertical'（纵向）或 'horizontal'（横向）
        gap:         图片间距（像素）
        labels:      可选，每张图的标签文字
    """
    images = [Image.open(p) for p in image_paths]

    if not images:
        raise ValueError("没有可拼接的图片")

    font = _load_font(14) if labels else None
    label_height = 20 if labels else 0

    if direction == "vertical":
        total_width = max(img.width for img in images)
        total_height = (
            sum(img.height + label_height for img in images)
            + gap * (len(images) - 1)
        )

        result = Image.new("RGB", (total_width, total_height), (10, 10, 18))
        draw = ImageDraw.Draw(result)
        y_offset = 0

        for i, img in enumerate(images):
            # 绘制标签
            if labels and i < len(labels):
                draw.text(
                    (8, y_offset + 2),
                    labels[i],
                    fill=(200, 200, 220),
                    font=font,
                )
                y_offset += label_height

            # 居中粘贴频谱图
            x_offset = (total_width - img.width) // 2
            result.paste(img, (x_offset, y_offset))
            y_offset += img.height + gap

    else:  # horizontal
        total_width = (
            sum(img.width for img in images)
            + gap * (len(images) - 1)
        )
        total_height = max(img.height for img in images) + label_height

        result = Image.new("RGB", (total_width, total_height), (10, 10, 18))
        draw = ImageDraw.Draw(result)
        x_offset = 0

        for i, img in enumerate(images):
            # 绘制标签
            if labels and i < len(labels):
                draw.text(
                    (x_offset + 8, 2),
                    labels[i],
                    fill=(200, 200, 220),
                    font=font,
                )

            y_off = label_height + (total_height - label_height - img.height) // 2
            result.paste(img, (x_offset, y_off))
            x_offset += img.width + gap

    # 清理
    for img in images:
        img.close()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    result.save(output_path, "PNG", optimize=True)
    result.close()

    return output_path


# ---------------------------------------------------------------------------
# 4. 专辑处理编排
# ---------------------------------------------------------------------------

def process_album(
    folder_path: str,
    output_dir: str,
    config: dict,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    处理整个文件夹：递归扫描 → 生成频谱 → 拼接输出。

    参数:
        folder_path:       输入文件夹路径
        output_dir:        输出目录
        config:            配置字典 (width, height, dynamic_range, direction, gap, show_labels)
        progress_callback: 进度回调函数

    返回:
        {
            "albums": [{"name": ..., "output": ..., "filename": ..., "tracks": N}, ...],
            "total_tracks": N,
            "total_albums": N,
        }
    """
    width = int(config.get("width", 1920))
    height = int(config.get("height", 400))
    dynamic_range = int(config.get("dynamic_range", 90))
    direction = config.get("direction", "vertical")
    gap = int(config.get("gap", 2))
    show_labels = config.get("show_labels", True)

    # 扫描 FLAC 文件
    albums = scan_for_flac(folder_path)
    if not albums:
        raise FileNotFoundError(f"在 {folder_path} 中未找到 .flac 文件")

    total_tracks = sum(len(tracks) for tracks in albums.values())
    processed = 0
    results = []

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="spectrogram_") as tmp_dir:
        for folder, tracks in sorted(albums.items()):
            # 生成可读的专辑名称（保留嵌套路径信息）
            rel_path = os.path.relpath(folder, folder_path)
            safe_name = rel_path.replace(os.sep, " - ").replace("/", " - ")
            if safe_name == ".":
                safe_name = os.path.basename(os.path.abspath(folder_path))

            if progress_callback:
                progress_callback({
                    "type": "album_start",
                    "album": safe_name,
                    "tracks_in_album": len(tracks),
                    "processed": processed,
                    "total": total_tracks,
                })

            spec_paths = []
            labels = []

            for track_path in tracks:
                track_name = os.path.splitext(os.path.basename(track_path))[0]
                spec_out = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.png")

                try:
                    generate_spectrogram(
                        track_path,
                        spec_out,
                        width=width,
                        height=height,
                        dynamic_range=dynamic_range,
                    )
                    spec_paths.append(spec_out)
                    labels.append(track_name)
                except Exception as e:
                    logger.error("频谱图生成失败 [%s]: %s", track_path, e)

                processed += 1
                if progress_callback:
                    progress_callback({
                        "type": "track_done",
                        "track": track_name,
                        "album": safe_name,
                        "processed": processed,
                        "total": total_tracks,
                    })

            # 拼接当前专辑
            if spec_paths:
                # 清理文件名中的非法字符
                clean_name = "".join(
                    c if c.isalnum() or c in (" ", "-", "_", ".") else "_"
                    for c in safe_name
                )
                output_filename = f"{clean_name}.png"
                output_path = os.path.join(output_dir, output_filename)

                try:
                    stitch_spectrograms(
                        spec_paths,
                        output_path,
                        direction=direction,
                        gap=gap,
                        labels=labels if show_labels else None,
                    )

                    results.append({
                        "name": safe_name,
                        "output": output_path,
                        "filename": output_filename,
                        "tracks": len(spec_paths),
                    })

                    if progress_callback:
                        progress_callback({
                            "type": "album_done",
                            "album": safe_name,
                            "output": output_filename,
                            "processed": processed,
                            "total": total_tracks,
                        })
                except Exception as e:
                    logger.error("拼接失败 [%s]: %s", safe_name, e)

    return {
        "albums": results,
        "total_tracks": total_tracks,
        "total_albums": len(results),
    }

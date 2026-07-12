"""
uploader.py — 图床上传模块（imgbb）

功能：
  - 单张图片上传到 imgbb
  - 批量上传（带重试 + 进度回调）
  - 返回直链、缩略图链接、删除链接
"""

import os
import base64
import time
import logging
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

IMGBB_API_URL = "https://api.imgbb.com/1/upload"
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒（基础延迟，指数退避）


# ---------------------------------------------------------------------------
# 1. 单张上传
# ---------------------------------------------------------------------------

def upload_to_imgbb(
    image_path: str,
    api_key: str,
    name: Optional[str] = None,
    expiration: Optional[int] = None,
) -> dict:
    """
    上传单张图片到 imgbb。

    参数:
        image_path:  本地图片文件路径
        api_key:     imgbb API Key
        name:        可选，自定义文件名
        expiration:  可选，自动删除时间（秒，60 ~ 15,552,000）

    返回:
        {
            "success": True,
            "url": "https://i.ibb.co/xxxxx/image.png",         # 直链
            "display_url": "https://i.ibb.co/xxxxx/image.png",
            "viewer_url": "https://ibb.co/xxxxx",               # 查看页
            "thumb_url": "https://i.ibb.co/xxxxx/image.png",    # 缩略图
            "delete_url": "https://ibb.co/delete/xxxxx",        # 删除链接
            "filename": "image.png",
            "size": 123456,
        }

    异常:
        RuntimeError: API 调用失败
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    if not api_key or not api_key.strip():
        raise ValueError("imgbb API Key 不能为空")

    # 读取并 Base64 编码
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # 构建请求参数
    payload = {
        "key": api_key.strip(),
        "image": image_data,
    }
    if name:
        payload["name"] = name
    if expiration and 60 <= expiration <= 15_552_000:
        payload["expiration"] = str(expiration)

    # 发送请求（带重试）
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                IMGBB_API_URL,
                data=payload,
                timeout=120,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    data = result["data"]
                    return {
                        "success": True,
                        "url": data.get("url", ""),
                        "display_url": data.get("display_url", ""),
                        "viewer_url": data.get("url_viewer", ""),
                        "thumb_url": data.get("thumb", {}).get("url", ""),
                        "delete_url": data.get("delete_url", ""),
                        "filename": data.get("image", {}).get("filename", ""),
                        "size": data.get("size", 0),
                    }
                else:
                    last_error = f"API 返回失败: {result}"

            elif response.status_code == 429:
                # 触发速率限制
                delay = RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "imgbb 速率限制，等待 %ds 后重试 (%d/%d)",
                    delay, attempt, MAX_RETRIES,
                )
                time.sleep(delay)
                continue

            else:
                last_error = (
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )

        except requests.Timeout:
            last_error = f"请求超时 (尝试 {attempt}/{MAX_RETRIES})"
            logger.warning(last_error)
        except requests.ConnectionError as e:
            last_error = f"连接错误: {e}"
            logger.warning(last_error)
        except Exception as e:
            last_error = f"未知错误: {e}"
            logger.error(last_error)

        # 非 429 的重试也加延迟
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    # 所有重试均失败
    return {
        "success": False,
        "error": last_error or "上传失败（未知原因）",
        "filename": os.path.basename(image_path),
    }

def upload_to_pixhost(image_path: str, name: Optional[str] = None) -> dict:
    """
    上传单张图片到 pixhost (无需 API Key)。
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    # Pixhost API expects multipart form data with the image in 'img' field and 'content_type=0'
    img_file = open(image_path, 'rb')
    try:
        files = {
            'img': (name or os.path.basename(image_path), img_file, 'image/png')
        }
        data = {
            'content_type': '0',
            'max_th_size': '420'
        }

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    "https://api.pixhost.to/images",
                    files=files,
                    data=data,
                    timeout=120,
                )

                if response.status_code == 200:
                    result = response.json()
                    # Pixhost returns a list of uploaded images, or a list with a single dict
                    if isinstance(result, list) and len(result) > 0 and 'show_url' in result[0]:
                        img_data = result[0]
                        # We can construct the direct image URL from the thumbnail URL:
                        # thumb: https://t{server}.pixhost.to/thumbs/{dir}/{name}
                        # direct: https://img{server}.pixhost.to/images/{dir}/{name}
                        thumb_url = img_data.get('th_url', '')
                        direct_url = thumb_url.replace('/thumbs/', '/images/').replace('https://t', 'https://img')

                        return {
                            "success": True,
                            "url": direct_url,
                            "display_url": direct_url,
                            "viewer_url": img_data.get('show_url', ''),
                            "thumb_url": thumb_url,
                            "delete_url": "", # Pixhost doesn't return delete URLs in this simple API
                            "filename": img_data.get('name', ''),
                            "size": 0,
                        }
                    else:
                        last_error = f"API 返回不符合预期: {result}"
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"

            except requests.Timeout:
                last_error = f"请求超时 (尝试 {attempt}/{MAX_RETRIES})"
                logger.warning(last_error)
            except requests.ConnectionError as e:
                last_error = f"连接错误: {e}"
                logger.warning(last_error)
            except Exception as e:
                last_error = f"未知错误: {e}"
                logger.error(last_error)

            if attempt < MAX_RETRIES:
                img_file.seek(0)  # reset for next attempt
                time.sleep(RETRY_DELAY)

        return {
            "success": False,
            "error": last_error or "上传失败（未知原因）",
            "filename": os.path.basename(image_path),
        }
    finally:
        img_file.close()


# ---------------------------------------------------------------------------
# 2. 批量上传
# ---------------------------------------------------------------------------

def batch_upload(
    image_paths: list[str],
    api_key: str = "",
    expiration: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    host: str = "imgbb",
) -> list[dict]:
    """
    批量上传多张图片到图床。

    参数:
        image_paths:       图片路径列表
        api_key:           API Key (imgbb 需要)
        expiration:        可选，自动删除时间
        progress_callback: 进度回调 fn(info_dict)
        host:              'imgbb' 或 'pixhost'

    返回:
        上传结果列表
    """
    results = []
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        filename = os.path.basename(path)
        name = os.path.splitext(filename)[0]

        if progress_callback:
            progress_callback({
                "type": "upload_start",
                "filename": filename,
                "index": i + 1,
                "total": total,
            })

        if host == "pixhost":
            result = upload_to_pixhost(path, name=name)
        else:
            result = upload_to_imgbb(
                path,
                api_key,
                name=name,
                expiration=expiration,
            )
        result["original_filename"] = filename
        result["original_path"] = path

        if result.get("success"):
            logger.info(
                "上传成功 [%d/%d] %s → %s",
                i + 1, total, filename, result.get("url"),
            )
            if progress_callback:
                progress_callback({
                    "type": "upload_done",
                    "filename": filename,
                    "url": result.get("url", ""),
                    "direct_url": result.get("display_url", ""),
                    "thumb_url": result.get("thumb_url", ""),
                    "delete_url": result.get("delete_url", ""),
                    "index": i + 1,
                    "total": total,
                })
        else:
            logger.error(
                "上传失败 [%d/%d] %s: %s",
                i + 1, total, filename, result.get("error"),
            )
            if progress_callback:
                progress_callback({
                    "type": "upload_error",
                    "filename": filename,
                    "error": result.get("error", "未知错误"),
                    "index": i + 1,
                    "total": total,
                })

        results.append(result)

        # 上传间隔，避免触发速率限制
        if i < total - 1:
            time.sleep(0.5)

    return results

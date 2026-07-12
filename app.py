"""
app.py — Flask Web 应用

路由:
  GET  /                      主页
  POST /api/scan              扫描文件夹
  POST /api/generate          开始生成频谱图
  GET  /api/progress/<id>     SSE 实时进度
  GET  /api/output-files      列出输出目录文件
  GET  /api/image             提供图片访问
  POST /api/tracklist         提取 FLAC 元数据 Tracklist
  POST /api/tracklist/format  格式化 Tracklist 文本
  POST /api/upload            手动上传图片到图床
"""

import os
import json
import uuid
import threading
import queue
import logging

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    send_file,
    abort,
)

from dotenv import load_dotenv

from spectrogram import process_album, scan_for_audio
from metadata import extract_tracklist, format_tracklist
from uploader import batch_upload
from torrent_maker import create_torrent

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

load_dotenv()  # 从 .env 文件加载环境变量

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB (for API JSON)

DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "output"
)

# 路径浏览器的根目录，用于限制浏览范围（Docker 中通常为 /music）
BROWSE_ROOT = os.environ.get("BROWSE_ROOT", "").strip()
if BROWSE_ROOT and not os.path.isdir(BROWSE_ROOT):
    BROWSE_ROOT = ""  # 配置了但目录不存在，回退到无限制

# 存储每个任务的进度队列
_progress_queues: dict[str, queue.Queue] = {}


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """渲染主页。"""
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API 路由 — 扫描 & 生成
# ---------------------------------------------------------------------------

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    扫描文件夹，返回发现的专辑和曲目列表。
    请求体: { "folder_path": "/path/to/music" }
    """
    data = request.get_json(silent=True) or {}
    folder_path = data.get("folder_path", "").strip()

    if not folder_path:
        return jsonify({"error": "请输入文件夹路径"}), 400

    if not os.path.isdir(folder_path):
        return jsonify({"error": f"目录不存在: {folder_path}"}), 400

    try:
        albums = scan_for_audio(folder_path)
        result = []
        for folder, tracks in sorted(albums.items()):
            rel = os.path.relpath(folder, folder_path)
            display_name = rel if rel != "." else os.path.basename(
                os.path.abspath(folder_path)
            )
            result.append({
                "path": folder,
                "name": display_name,
                "tracks": [os.path.basename(t) for t in tracks],
                "count": len(tracks),
            })

        total = sum(a["count"] for a in result)
        return jsonify({"albums": result, "total_tracks": total})

    except Exception as e:
        logger.exception("扫描失败")
        return jsonify({"error": str(e)}), 500


@app.route("/api/path", methods=["GET"])
def api_path():
    """返回目录内容供前端路径浏览器使用（仅显示文件夹，限制在 BROWSE_ROOT 内）"""
    path = request.args.get("path", BROWSE_ROOT or "/")

    # 如果配置了 BROWSE_ROOT，确保不越界
    if BROWSE_ROOT:
        # 规范化路径
        browse_root = os.path.abspath(BROWSE_ROOT)
        if not path or not os.path.isdir(path):
            path = browse_root
        # 防止路径遍历攻击：不允许访问 BROWSE_ROOT 之外的目录
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(browse_root):
            path = browse_root
    else:
        if not path or not os.path.isdir(path):
            path = os.path.abspath(os.sep)

    entries = []
    try:
        # 上级目录（仅当不在 BROWSE_ROOT 时显示）
        parent_dir = os.path.dirname(path)
        can_go_up = parent_dir != path
        if BROWSE_ROOT:
            browse_root = os.path.abspath(BROWSE_ROOT)
            abs_parent = os.path.abspath(parent_dir)
            # 如果上级目录不在浏览根内，不允许返回
            if not abs_parent.startswith(browse_root):
                can_go_up = False

        if can_go_up:
            entries.append({
                "name": "..",
                "path": parent_dir,
                "is_dir": True,
                "size": 0,
            })

        for item in sorted(os.listdir(path)):
            full = os.path.join(path, item)
            # 跳过隐藏文件
            if item.startswith("."):
                continue
            # 仅显示文件夹
            if not os.path.isdir(full):
                continue
            entries.append({
                "name": item,
                "path": full,
                "is_dir": True,
                "size": 0,
            })
    except PermissionError:
        return jsonify({"error": "没有权限访问该目录"}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"path": path, "entries": entries, "browse_root": BROWSE_ROOT or None})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """
    启动频谱图生成任务（异步）。
    请求体: {
        "folder_path": "...",
        "output_dir": "...",
        "width": 1920, "height": 400,
        "dynamic_range": 90,
        "direction": "vertical",
        "gap": 2,
        "show_labels": true,
        "auto_upload": false,
        "imgbb_api_key": ""
    }
    """
    data = request.get_json(silent=True) or {}
    folder_path = data.get("folder_path", "").strip()
    output_dir = data.get("output_dir", "").strip() or DEFAULT_OUTPUT_DIR

    if not folder_path or not os.path.isdir(folder_path):
        return jsonify({"error": "无效的文件夹路径"}), 400

    config = {
        "width": int(data.get("width", 1920)),
        "height": int(data.get("height", 400)),
        "dynamic_range": int(data.get("dynamic_range", 90)),
        "direction": data.get("direction", "vertical"),
        "gap": int(data.get("gap", 2)),
        "show_labels": bool(data.get("show_labels", True)),
        "stitch": bool(data.get("stitch", True)),
    }

    auto_upload = bool(data.get("auto_upload", False))
    host = data.get("host", "imgbb").strip()
    imgbb_api_key = data.get("imgbb_api_key", "").strip()
    # 如果前端未提供 key，尝试从环境变量获取
    if auto_upload and host == "imgbb" and not imgbb_api_key:
        imgbb_api_key = os.environ.get("IMGBB_API_KEY", "")

    if auto_upload and host == "imgbb" and not imgbb_api_key:
        return jsonify({"error": "自动上传到 imgbb 需要提供 API Key"}), 400

    task_id = uuid.uuid4().hex
    _progress_queues[task_id] = queue.Queue()

    def _run():
        q = _progress_queues[task_id]
        try:
            result = process_album(
                folder_path,
                output_dir,
                config,
                progress_callback=lambda info: q.put(json.dumps(info)),
            )

            # 自动上传到图床
            if auto_upload and result.get("albums"):
                image_paths = []
                # If stitched, there is one output per album. If not stitched, there is one output per track.
                for a in result["albums"]:
                    if "output" in a and os.path.isfile(a.get("output", "")):
                        image_paths.append(a["output"])
                    elif "tracks" in a and isinstance(a["tracks"], list) and len(a["tracks"]) > 0 and isinstance(a["tracks"][0], dict) and "output" in a["tracks"][0]:
                        for t in a["tracks"]:
                            if os.path.isfile(t.get("output", "")):
                                image_paths.append(t["output"])

                if image_paths:
                    upload_results = batch_upload(
                        image_paths,
                        api_key=imgbb_api_key,
                        host=host,
                        progress_callback=lambda info: q.put(json.dumps(info)),
                    )
                    # 将上传结果附加到返回数据
                    result["upload_results"] = []
                    for ur in upload_results:
                        if ur.get("success"):
                            result["upload_results"].append({
                                "filename": ur.get("original_filename", ""),
                                "url": ur.get("url", ""),
                                "direct_url": ur.get("display_url", ""),
                                "thumb_url": ur.get("thumb_url", ""),
                                "delete_url": ur.get("delete_url", ""),
                            })

            q.put(json.dumps({"type": "complete", "result": result}))
        except Exception as e:
            logger.exception("生成任务失败")
            q.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            q.put(None)  # 流结束信号

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"task_id": task_id, "output_dir": output_dir})


@app.route("/api/torrent", methods=["POST"])
def api_torrent():
    """
    启动制种任务（异步）。
    """
    data = request.get_json(silent=True) or {}
    folder_path = data.get("folder_path", "").strip()
    output_dir = data.get("output_dir", "").strip() or DEFAULT_OUTPUT_DIR

    if not folder_path or not os.path.exists(folder_path):
        return jsonify({"error": "无效的文件夹路径"}), 400

    trackers = data.get("trackers", [])
    if isinstance(trackers, str):
        trackers = [t.strip() for t in trackers.split("\n") if t.strip()]

    web_seeds = data.get("web_seeds", [])
    if isinstance(web_seeds, str):
        web_seeds = [w.strip() for w in web_seeds.split("\n") if w.strip()]

    private = bool(data.get("private", True))
    source = data.get("source", "").strip()
    comment = data.get("comment", "").strip()
    piece_size = data.get("piece_size")
    if piece_size:
        try:
            piece_size = int(piece_size) * 1024  # assuming frontend sends KB or we specify bytes. Let's assume bytes from frontend if raw, or let torf handle it. torf expects bytes. Let's assume frontend sends bytes.
        except:
            piece_size = None

    task_id = uuid.uuid4().hex
    _progress_queues[task_id] = queue.Queue()

    def _run():
        q = _progress_queues[task_id]
        try:
            output_path = create_torrent(
                folder_path,
                output_dir,
                trackers=trackers,
                web_seeds=web_seeds,
                private=private,
                source=source,
                comment=comment,
                piece_size=piece_size,
                progress_callback=lambda info: q.put(json.dumps(info))
            )
            q.put(json.dumps({"type": "complete", "result": {"torrent_file": os.path.basename(output_path)}}))
        except Exception as e:
            logger.exception("制种失败")
            q.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            q.put(None)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"task_id": task_id, "output_dir": output_dir})


@app.route("/api/progress/<task_id>")
def api_progress(task_id):
    """SSE 实时进度推送。"""
    if task_id not in _progress_queues:
        return jsonify({"error": "任务不存在"}), 404

    def _stream():
        q = _progress_queues[task_id]
        max_idle = 1800  # 30 分钟无实际消息才断开
        idle_elapsed = 0
        heartbeat_interval = 30  # 每 30 秒检查一次
        try:
            while True:
                try:
                    msg = q.get(timeout=heartbeat_interval)
                    idle_elapsed = 0  # 收到消息，重置空闲计时
                    if msg is None:
                        yield f"data: {json.dumps({'type': 'end'})}\n\n"
                        break
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    idle_elapsed += heartbeat_interval
                    if idle_elapsed >= max_idle:
                        yield f"data: {json.dumps({'type': 'error', 'message': '超时：30 分钟无进度更新'})}\n\n"
                        break
                    # 发送 SSE 心跳注释，保持连接活跃
                    yield ": heartbeat\n\n"
        finally:
            _progress_queues.pop(task_id, None)

    return Response(
        _stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/output-files")
def api_output_files():
    """列出指定输出目录中的图片文件。"""
    output_dir = request.args.get("dir", DEFAULT_OUTPUT_DIR)

    if not os.path.isdir(output_dir):
        return jsonify({"files": []})

    files = []
    for f in sorted(os.listdir(output_dir)):
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            full = os.path.join(output_dir, f)
            files.append({
                "name": f,
                "size": os.path.getsize(full),
            })

    return jsonify({"files": files, "dir": output_dir})


@app.route("/api/image")
def api_image():
    """
    根据绝对路径提供图片文件访问。
    用于在 WebUI 中预览和下载频谱图。
    """
    filepath = request.args.get("path", "")

    if not filepath or not os.path.isfile(filepath):
        abort(404)

    if not filepath.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        abort(400)

    return send_file(filepath, mimetype="image/png")


# ---------------------------------------------------------------------------
# API 路由 — Tracklist 元数据
# ---------------------------------------------------------------------------

@app.route("/api/tracklist", methods=["POST"])
def api_tracklist():
    """
    从 FLAC 文件元数据中提取 Tracklist。
    请求体: { "folder_path": "/path/to/music" }
    """
    data = request.get_json(silent=True) or {}
    folder_path = data.get("folder_path", "").strip()

    if not folder_path:
        return jsonify({"error": "请输入文件夹路径"}), 400

    if not os.path.isdir(folder_path):
        return jsonify({"error": f"目录不存在: {folder_path}"}), 400

    try:
        albums = extract_tracklist(folder_path)
        return jsonify({"albums": albums, "total_albums": len(albums)})
    except Exception as e:
        logger.exception("Tracklist 提取失败")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tracklist/format", methods=["POST"])
def api_tracklist_format():
    """
    将 Tracklist 数据格式化为可复制的文本。
    请求体: { "albums": [...], "format": "plain|bbcode|markdown" }
    """
    data = request.get_json(silent=True) or {}
    albums = data.get("albums", [])
    fmt = data.get("format", "plain")

    if not albums:
        return jsonify({"error": "没有 Tracklist 数据"}), 400

    try:
        parts = []
        for album_data in albums:
            parts.append(format_tracklist(album_data, fmt=fmt))
        text = "\n\n".join(parts)
        return jsonify({"text": text, "format": fmt})
    except Exception as e:
        logger.exception("格式化失败")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API 路由 — 图床上传
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    手动上传图片到图床。
    """
    data = request.get_json(silent=True) or {}
    image_paths = data.get("image_paths", [])
    host = data.get("host", "imgbb").strip()
    api_key = data.get("api_key", "").strip()

    if host == "imgbb" and not api_key:
        api_key = os.environ.get("IMGBB_API_KEY", "")

    if host == "imgbb" and not api_key:
        return jsonify({"error": "请提供 imgbb API Key"}), 400

    if not image_paths:
        return jsonify({"error": "没有图片路径"}), 400

    # 验证文件存在
    valid_paths = [p for p in image_paths if os.path.isfile(p)]
    if not valid_paths:
        return jsonify({"error": "没有有效的图片文件"}), 400

    try:
        results = batch_upload(valid_paths, api_key=api_key, host=host)
        upload_data = []
        for r in results:
            if r.get("success"):
                upload_data.append({
                    "filename": r.get("original_filename", ""),
                    "url": r.get("url", ""),
                    "direct_url": r.get("display_url", ""),
                    "thumb_url": r.get("thumb_url", ""),
                    "delete_url": r.get("delete_url", ""),
                })
            else:
                upload_data.append({
                    "filename": r.get("original_filename", r.get("filename", "")),
                    "error": r.get("error", "上传失败"),
                })

        success_count = sum(1 for r in results if r.get("success"))
        return jsonify({
            "results": upload_data,
            "total": len(valid_paths),
            "success": success_count,
            "failed": len(valid_paths) - success_count,
        })

    except Exception as e:
        logger.exception("上传失败")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    print("\n  🎵 专辑频谱图生成器已启动")
    print(f"  📂 默认输出目录: {DEFAULT_OUTPUT_DIR}")
    print(f"  🌐 访问 http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

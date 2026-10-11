import ipaddress
import json
import os
import time
import uuid
import urllib.request

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.utils import secure_filename

from models import Comment, File, Post, Setting, db
from utils import (current_user, get_client_ip, get_setting, get_settings,
                   invalidate_settings, login_required,
                   random_guest_nickname, write_log)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _file_kind(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return current_app.config.get("EXT_KIND_MAP", {}).get(ext)


# ---------------- 评论 ----------------

@api_bp.route("/comment", methods=["POST"])
def add_comment():
    if get_setting("comment_allow", "1") != "1":
        return jsonify({"ok": False, "msg": "评论区已关闭"}), 400

    post_id = request.form.get("post_id", type=int)
    nickname = (request.form.get("nickname") or "").strip()
    email = (request.form.get("email") or "").strip()
    content = (request.form.get("content") or "").strip()

    # 游客评论：未填昵称时按 IP 稳定派生（同一 IP 多次评论同昵称）
    if not nickname:
        nickname = random_guest_nickname(get_client_ip())
    if not nickname or len(nickname) > 20:
        return jsonify({"ok": False, "msg": "请填写昵称（20 字以内）"}), 400
    if not content or len(content) > 1000:
        return jsonify({"ok": False, "msg": "评论内容需在 1-1000 字之间"}), 400
    if email and ("@" not in email or len(email) > 100):
        return jsonify({"ok": False, "msg": "邮箱格式不正确（选填）"}), 400

    if post_id is None:
        return jsonify({"ok": False, "msg": "缺少文章参数"}), 400

    post = Post.query.get(post_id)
    if post is None or post.status != "published":
        return jsonify({"ok": False, "msg": "文章不存在"}), 404
    if not post.allow_comment:
        return jsonify({"ok": False, "msg": "该文章已关闭评论"}), 403

    # 管理员评论直接通过；游客按审核设置
    is_admin = current_user() is not None
    need_audit = get_setting("comment_need_audit", "1") == "1"
    approved = is_admin or not need_audit

    c = Comment(
        post_id=post_id,
        user_id=None,
        nickname=nickname,
        email=email,
        content=content,
        ip=get_client_ip(),
        is_approved=approved,
    )
    db.session.add(c)
    db.session.commit()

    msg = "评论成功" if approved else "评论已提交，待管理员审核后展示"
    return jsonify({"ok": True, "msg": msg})


# ---------------- 点赞 ----------------

@api_bp.route("/post/<int:pid>/like", methods=["POST"])
def like_post(pid):
    post = Post.query.get_or_404(pid)
    liked = session.setdefault("liked_posts", [])
    if pid in liked:
        return jsonify({"ok": False, "msg": "你已经点过赞了"}), 400
    post.likes += 1
    liked.append(pid)
    session["liked_posts"] = liked
    db.session.commit()
    return jsonify({"ok": True, "likes": post.likes})


# ---------------- 文件库（上传 / 列表 / 删除） ----------------

@api_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "msg": "未选择文件"}), 400

    raw_name = secure_filename(file.filename) or "file"
    kind = _file_kind(raw_name)
    if not kind:
        allow = ", ".join(
            sorted({e for exts in current_app.config["FILE_KINDS"].values() for e in exts})
        )
        return jsonify({"ok": False, "msg": f"不支持的文件类型。支持：{allow}"}), 400

    ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    stored = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], kind)
    os.makedirs(folder, exist_ok=True)
    file.save(os.path.join(folder, stored))

    size = os.path.getsize(os.path.join(folder, stored))
    url = f"/uploads/{kind}/{stored}"
    rec = File(
        name=raw_name,
        stored_name=stored,
        kind=kind,
        mime=file.mimetype or "",
        size=size,
        ext=ext,
        url=url,
    )
    db.session.add(rec)
    db.session.commit()
    write_log("file_upload", f"上传文件：{raw_name}", f"{kind} · {rec.size_label if hasattr(rec,'size_label') else size}B",
              username=(current_user().username if current_user() else ""))

    return jsonify({
        "ok": True, "url": url, "name": raw_name,
        "kind": kind, "size": size, "id": rec.id,
    })


@api_bp.route("/files", methods=["GET"])
@login_required
def files():
    """文件库列表（编辑器插入器 / 文件管理页共用）。"""
    kind = request.args.get("kind", "")
    q = (request.args.get("q") or "").strip()
    query = File.query
    if kind and kind != "all":
        query = query.filter_by(kind=kind)
    if q:
        query = query.filter(File.name.like(f"%{q}%"))
    items = query.order_by(File.created_at.desc()).limit(200).all()
    return jsonify({
        "ok": True,
        "files": [{
            "id": f.id, "name": f.name, "url": f.url, "kind": f.kind,
            "size": f.size, "size_label": f.size_label,
            "ext": f.ext, "created": f.created_at.strftime("%Y-%m-%d %H:%M"),
        } for f in items],
    })


@api_bp.route("/file/<int:fid>/delete", methods=["POST"])
@login_required
def file_delete(fid):
    f = File.query.get_or_404(fid)
    # 同时删除磁盘文件（尽力而为）
    try:
        path = os.path.join(
            current_app.config["UPLOAD_FOLDER"], f.kind, f.stored_name
        )
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    db.session.delete(f)
    db.session.commit()
    write_log("file_delete", f"删除文件：{f.name}", "", username=(current_user().username if current_user() else ""))
    return jsonify({"ok": True, "msg": "文件已删除"})


# ---------------- 免费天气（侧栏小部件，后端代理） ----------------

_WEATHER_CACHE = {}
_UA = {"User-Agent": "Mozilla/5.0 (compatible; BlogWidget/1.0)"}


def _http_json(url, timeout=6):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _public_client_ip():
    """取访客公网 IP；内网/本机/未知时返回空（跳过定位）。"""
    ip = (get_client_ip() or "").strip()
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local \
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            return ""
    except ValueError:
        return ""
    return ip


def _locate(ip):
    """IP → (城市, 纬度, 经度)。多免费源兜底。"""
    if ip:
        try:
            d = _http_json(f"https://api.ip.sb/geoip/{ip}")
            if d and d.get("city"):
                return d["city"], d.get("latitude"), d.get("longitude")
        except Exception:
            pass
        try:
            d = _http_json(
                f"http://ip-api.com/json/{ip}?lang=zh-CN"
                "&fields=status,country,regionName,city,lat,lon"
            )
            if d and d.get("status") == "success" and d.get("city"):
                return d["city"], d.get("lat"), d.get("lon")
        except Exception:
            pass
    return None, None, None


def _weather_query(loc_key):
    """wttr.in 经纬度查询当前天气，返回 (city, payload)。"""
    d = _http_json(f"https://wttr.in/{loc_key}?format=j1&lang=zh&m", timeout=7)
    cur = (d.get("current_condition") or [{}])[0]
    if not cur:
        return None
    return {
        "temp": cur.get("temp_C", ""),
        "feels": cur.get("FeelsLikeC", ""),
        "humidity": cur.get("humidity", ""),
        "wind": cur.get("windspeedKmph", ""),
        "text_en": (cur.get("weatherDesc") or [{}])[0].get("value", ""),
    }


@api_bp.route("/weather")
def weather():
    """GET /api/weather —— 免费天气：IP 定位(api.ip.sb/ip-api 兜底) + wttr.in。
    结果按城市缓存 20 分钟。定位失败时退回后台设置中的默认城市。
    """
    city, lat, lon = None, None, None
    ip = _public_client_ip()
    if ip:
        city, lat, lon = _locate(ip)
    key, display = None, city or ""

    if city and lat is not None and lon is not None:
        key = f"{float(lat):.4f},{float(lon):.4f}"
    else:
        default = (get_setting("weather_default_city") or "").strip()
        if default:
            key, display = default, default  # 支持英文城市名或 纬度,经度
    if not key:
        return jsonify({"ok": False, "msg": "无法定位，且未配置默认城市"})

    now = time.time()
    cached = _WEATHER_CACHE.get(key)
    if cached and now - cached[0] < 20 * 60:
        body = dict(cached[1])
        body["from_cache"] = True
        return jsonify(body)

    try:
        wx = _weather_query(key)
    except Exception:
        wx = None
    if not wx:
        return jsonify({"ok": False, "msg": "天气服务暂不可用"})

    body = {"ok": True, "city": display or key, **wx}
    _WEATHER_CACHE[key] = (now, body)
    return jsonify(body)


# ---------------- 站点偏好（配色 / 深浅色）：前后台实时同步 ----------------
# 访客可读：用来初始化前后台的 data-palette / theme_default 等"权威默认值"
# 写：必须登录管理员；且仅允许写视觉类偏好（color_palette / theme_default）
#   → 这样前台游客预览切换不会污染 DB，只在管理员操作时才落库

_SITE_PREFS_KEYS = {
    "color_palette",      # amber / sea / mint / grape / rose
    "theme_default",      # light / dark
    "theme_auto",         # off / schedule / system
    "theme_dark_start",   # 0-23
    "theme_dark_end",     # 0-23
    "theme_fix_content",  # 0/1
}

_PALETTE_OK = {"amber", "sea", "mint", "grape", "rose"}
_THEME_LIGHT_OK = {"light", "dark"}
_AUTO_OK = {"off", "schedule", "system"}


@api_bp.route("/site-prefs", methods=["GET"])
def site_prefs_get():
    """GET /api/site-prefs — 任何人可读；用于初始化前后台"默认值"以便实时同步。"""
    # 取 DB 当前生效值（而不是 DEFAULT_SETTINGS 默认值）
    current = get_settings()
    out = {k: current.get(k, "") for k in _SITE_PREFS_KEYS if k in current}
    return jsonify({"ok": True, "prefs": out})


@api_bp.route("/site-prefs", methods=["POST"])
@login_required
def site_prefs_post():
    """POST /api/site-prefs — 仅管理员可写；用于实时切换后立即落库，让所有标签页同步。"""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "msg": "请求体需为 JSON 对象"}), 400
    changed = []
    for k, v in payload.items():
        if k not in _SITE_PREFS_KEYS:
            continue
        s = str(v).strip()
        # 字段校验
        if k == "color_palette":
            if s not in _PALETTE_OK:
                return jsonify({"ok": False, "msg": f"非法配色：{s}"}), 400
        elif k == "theme_default":
            if s not in _THEME_LIGHT_OK:
                return jsonify({"ok": False, "msg": f"非法默认主题：{s}"}), 400
        elif k == "theme_auto":
            if s not in _AUTO_OK:
                return jsonify({"ok": False, "msg": f"非法自动模式：{s}"}), 400
        elif k in ("theme_dark_start", "theme_dark_end"):
            try:
                n = int(s)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "msg": f"{k} 必须是 0-23 的整数"}), 400
            if not (0 <= n <= 23):
                return jsonify({"ok": False, "msg": f"{k} 越界（0-23）"}), 400
            s = str(n)
        elif k == "theme_fix_content":
            s = "1" if s in ("1", "true", "True", "on", "yes") else ""
        Setting.set(k, s)
        changed.append(k)
    if changed:
        db.session.commit()
        invalidate_settings()
        write_log("site_prefs_save", "实时切换站点偏好", ",".join(changed))
    # 回读最新生效值（get_settings 走 get_settings 缓存，会自动 invalidate）
    latest = get_settings()
    out = {k: latest.get(k, "") for k in _SITE_PREFS_KEYS if k in latest}
    return jsonify({"ok": True, "prefs": out, "changed": changed})

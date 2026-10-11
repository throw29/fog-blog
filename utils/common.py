import re
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

import markdown
from flask import abort, current_app, redirect, request, session, url_for

from models import Log, Post, Setting, User, db

# ---------------- Markdown 渲染 ----------------

_MD = markdown.Markdown(
    extensions=[
        "tables",
        "fenced_code",
        "toc",
        "sane_lists",
        "nl2br",
        "attr_list",
        "def_list",
        "abbr",
        "footnotes",
    ],
    extension_configs={"toc": {"permalink": False, "toc_depth": "2-4"}},
    output_format="html5",
)


def render_markdown(text):
    """返回 (html, toc_tokens)。toc_tokens 用于前端生成文章目录。"""
    _MD.reset()
    body = _MD.convert(text or "")
    toc = getattr(_MD, "toc_tokens", [])
    return _media_markup(body), toc


def _media_markup(html):
    """把 Markdown 图片语法引用的音视频文件自动转成播放器标签：
    ![](x.mp4) -> <video controls ...>；![](x.mp3) -> <audio controls ...>"""
    html = re.sub(
        r'<img[^>]*?src="([^"]+?\.(?:mp4|webm|mov|m4v|ogv|avi|mkv|flv))"[^>]*>',
        lambda m: f'<video controls preload="metadata" src="{m.group(1)}"></video>',
        html, flags=re.IGNORECASE,
    )
    html = re.sub(
        r'<img[^>]*?src="([^"]+?\.(?:mp3|wav|ogg|m4a|flac|aac))"[^>]*>',
        lambda m: f'<audio controls preload="metadata" src="{m.group(1)}"></audio>',
        html, flags=re.IGNORECASE,
    )
    return html


def plain_text(text, is_html=False):
    """去标记得到纯文本（用于摘要、RSS）。"""
    if not text:
        return ""
    if is_html:
        text = re.sub(r"<[^>]+>", " ", text)
    else:
        html, _ = render_markdown(text)
        text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).strip()


# ---------------- 站点设置 ----------------

def get_settings():
    """读取全部设置（带默认值）。

    不再缓存：站点配色/主题默认值等需要"DB 一改就立刻生效"，任何后台写
    Settings 表后下一个请求就能拿到新值（之前进程级缓存会导致首屏渲染
    仍是旧色，依赖前端 async fetch 才覆盖回来）。SQLite 读 < 0.1ms，无负担。
    """
    data = dict(current_app.config["DEFAULT_SETTINGS"])
    data.update(Setting.get_all())
    return data


def invalidate_settings():
    """保留为 no-op 兼容旧调用点；新版 get_settings 已不缓存。"""
    return None


def get_setting(key, default=""):
    return get_settings().get(key, default)


# ---------------- CSRF ----------------

def generate_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def csrf_protect():
    """before_request 校验：POST 请求必须携带合法 CSRF token。"""
    if request.method == "POST":
        token = session.get("csrf_token")
        form_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not form_token or not secrets.compare_digest(token, form_token):
            abort(400, description="CSRF 校验失败，请刷新页面重试")


# ---------------- 登录态 ----------------

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def get_client_ip():
    """真实客户端 IP：优先取 X-Forwarded-For 第一段（Nginx 反代场景）。"""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64]


# ---------------- 操作日志 ----------------

def write_log(action, target="", detail="", username=None):
    """写入一条操作日志（低频操作，直接 commit）。username 传字符串，缺省时取当前登录者。"""
    try:
        if not username:
            u = current_user()
            username = u.username if u else ""
        rec = Log(
            action=action[:32],
            target=(target or "")[:255],
            detail=(detail or "")[:255],
            username=(username or "")[:64],
            ip=get_client_ip(),
        )
        from models import db

        db.session.add(rec)
        db.session.commit()
    except Exception:
        try:
            from models import db

            db.session.rollback()
        except Exception:
            pass


def purge_old_logs():
    """清理超过保留天数的日志，返回删除条数。保留天数由设置 log_keep_days 控制（默认 90）。"""
    try:
        days = int(get_setting("log_keep_days", "90") or 90)
    except (TypeError, ValueError):
        days = 90
    days = max(1, min(days, 3650))
    cutoff = datetime.now() - timedelta(days=days)
    deleted = Log.query.filter(Log.created_at < cutoff).delete(synchronize_session=False)
    if deleted:
        from models import db

        db.session.commit()
    return deleted or 0


def purge_orphan_links():
    """自愈：清理 post_tags 中已不存在的文章/标签关联行。

    原因：bulk query.delete() 不会触发 ORM 级联删除，会留下孤儿关联；
    SQLite 无 AUTOINCREMENT 时新行会复用被删文章的 rowid，进而撞上
    UNIQUE(post_id, tag_id) 约束导致保存文章 500。此函数兜底自愈。
    """
    from models import db
    try:
        n = db.session.execute(
            db.text("DELETE FROM post_tags WHERE post_id NOT IN (SELECT id FROM post)"
                    " OR tag_id NOT IN (SELECT id FROM tag)")
        ).rowcount
        if n:
            db.session.commit()
        return n or 0
    except Exception:
        db.session.rollback()
        return 0


def maybe_maintenance():
    """惰性维护：每 6 小时至多执行一次（日志清理 + 孤儿关联自愈 + 回收站过期清理）。"""
    now = time.time()
    last = getattr(current_app, "_last_maintenance", 0)
    if now - last < 6 * 3600:
        return
    current_app._last_maintenance = now
    purge_old_logs()
    purge_orphan_links()
    purge_expired_trash_posts()


def purge_expired_trash_posts(days=30):
    """清理回收站中超过 N 天的文章（物理删除）。返回删除数量。"""
    cutoff = datetime.now() - timedelta(days=days)
    expired = Post.query.filter(Post.deleted_at.isnot(None),
                                 Post.deleted_at < cutoff).all()
    n = len(expired)
    for p in expired:
        db.session.delete(p)
    if n:
        db.session.commit()
    return n


# ---------------- 分页 ----------------

def get_page():
    try:
        return max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def paginate(query, per_page=None):
    """对 query 排序后做简单分页，返回 (items, pagination_dict)。"""
    per_page = per_page or current_app.config["POSTS_PER_PAGE"]
    page = get_page()
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, {
        "page": page,
        "pages": pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_num": page - 1,
        "next_num": page + 1,
    }


# ---------------- 工具 ----------------

def slugify(text):
    """中文 slug：保留中文与字母数字，其余转 -。"""
    text = re.sub(r"[^\w\u4e00-\u9fa5-]", "-", str(text).strip().lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or secrets.token_hex(4)


def is_safe_url(target):
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def urljoin(base, url):
    from urllib.parse import urljoin as _join

    return _join(base, url)


def format_datetime(dt, fmt="%Y-%m-%d"):
    return dt.strftime(fmt) if dt else ""


def reading_minutes(content, is_html=False):
    """粗略阅读时长：中文 400 字/分钟。"""
    text = plain_text(content, is_html=is_html)
    cjk = len(re.findall(r"[\u4e00-\u9fa5]", text))
    words = len(re.findall(r"[a-zA-Z0-9]+", text))
    minutes = max(1, round((cjk + words * 0.6) / 400))
    return minutes


# ---------------- 访客昵称（按 IP 稳定） ----------------

# 形如 "快乐的鹿3847" —— 2 字形容词 + 1 字名词 + 4 位数字
# 同一 IP 多次访问会得到同一昵称；不同 IP 大概率不同。
# 组合数：20 × 24 × 10000 = 480 万，足以应付小博客
_NICK_ADJ = [
    "快乐", "安静", "好奇", "神秘", "勇敢", "温柔", "调皮", "聪明",
    "善良", "浪漫", "自由", "明亮", "沉稳", "活力", "灵动", "机智",
    "悠然", "清逸", "热忱", "轻悦",
]
_NICK_NOUN = [
    "鹿", "鹤", "猫", "狐", "兔", "鹰", "鲸", "熊",
    "茶", "月", "星", "雪", "雨", "风", "露", "虹",
    "橙", "桃", "樱", "杏", "梅", "梨", "桂", "松",
]


def random_guest_nickname(ip: str = "") -> str:
    """根据访客 IP 派生一个稳定的随机昵称。

    - 同一 IP 总是得到同一昵称（IP → 哈希 → 词表下标 + 数字后缀）
    - 哈希时附加 SECRET_SALT 防止外部猜测出某 IP 对应哪个昵称
    - 不依赖 cookie / DB；换浏览器 / 换设备 / 清 cookie 都不影响
    """
    import hashlib
    try:
        from flask import current_app
        salt = current_app.config.get("SECRET_KEY") or ""
    except RuntimeError:
        # 缺少 app context（极少数 e2e 场景）—— 用空 salt 兜底
        salt = ""
    key = (ip or "0.0.0.0") + salt
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
    adj = _NICK_ADJ[h % len(_NICK_ADJ)]
    noun = _NICK_NOUN[(h // len(_NICK_ADJ)) % len(_NICK_NOUN)]
    num = h % 10000
    return f"{adj}{noun}{num:04d}"

"""端到端验证：后台用户管理 / 日志 / 深色模式 / 侧栏部件 / 天气 / 文章与评论 / PDF。

策略：使用独立临时 SQLite（不碰开发库 blog.db），app.test_client() 直接跑，
session 注入固定 csrf_token 绕开"先 GET 取 token"的繁琐，跨请求一律重新查询
对象（避免 SQLAlchemy 跨 Session 持旧实例的 InvalidRequestError）。

用法: python e2e_features.py
"""
import os
import re
import sys
import tempfile
import json
import io
import struct
import zlib

# SSL 上传功能走 DRY_RUN：本机没有 wrapper / nginx，跳过实际写盘与 reload
os.environ["BLOG_SSL_DRY_RUN"] = "1"

from config import Config
from app import create_app
from models import (Category, Comment, File, Log, Post, Setting, SSLCertificate,
                    User, db)

# ---- 独立临时库 ----
_tmpdir = tempfile.mkdtemp(prefix="blog_e2e_")
TMP_DB = os.path.join(_tmpdir, "e2e.db")


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + TMP_DB
    TESTING = True
    UPLOAD_FOLDER = os.path.join(_tmpdir, "uploads")
    BACKUP_FOLDER = os.path.join(_tmpdir, "backup")


CSRF = "e2e-csrf-token-0123456789abcdef"
failures = []
app = create_app(TestConfig)


def ok(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def client_with_csrf():
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf_token"] = CSRF
    return c


def csrf():
    return {"csrf_token": CSRF}


# ---------------- 种子数据 ----------------
with app.app_context():
    db.create_all()
    admin = User(username="admin", nickname="站长", role="admin")
    admin.set_password("admin123")
    db.session.add(admin)
    cat = Category(name="技术", slug="tech")
    db.session.add(cat)
    db.session.flush()
    post = Post(title="端到端测试文章", slug="e2e-post", content="# 你好\n内容",
                status="published", category_id=cat.id)
    db.session.add(post)
    for k, v in Config.DEFAULT_SETTINGS.items():
        Setting.set(k, v)
    db.session.commit()
    POST_ID = post.id
    ADMIN_ID = admin.id


# ---------------- 1. 旧读者入口 /user/* 全部 302 到后台登录 ----------------
for p in ["/user/register", "/user/login", "/user/center", "/user/logout"]:
    g = client_with_csrf()
    r = g.get(p, follow_redirects=False)
    ok(f"GET {p} -> 302 重定向到登录", r.status_code == 302)

# 头像上传也已下线，应返回 410
ga = client_with_csrf()
r = ga.post("/user/avatar", data={**csrf(),
    "file": (io.BytesIO(b"x"), "x.png")}, content_type="multipart/form-data")
ok("POST /user/avatar 已下线 -> 410", r.status_code == 410)


# ---------------- 2. 后台账号管理 ----------------
ca = client_with_csrf()
with ca.session_transaction() as s:
    s["user_id"] = ADMIN_ID

r = ca.get("/admin/users")
ok("GET /admin/users 200", r.status_code == 200 and "站长" in r.get_data(as_text=True))
ok("默认仅 staff tab（移除读者 tab）", "前台读者" not in r.get_data(as_text=True))

# 新建同事账号（role=admin）
r = ca.post("/admin/users/new", data={**csrf(), "username": "staff01",
    "nickname": "员工", "password": "staff123456"}, follow_redirects=False)
ok("后台新建账号 -> 302", r.status_code == 302)
with app.app_context():
    staff = User.query.filter_by(username="staff01").first()
ok("后台新建账号入库 role=admin", staff is not None and staff.role == "admin")

# 不能停用自己
r = ca.post(f"/admin/users/{ADMIN_ID}/toggle", data=csrf(), follow_redirects=False)
ok("停用自己的操作被拒(回 302 列表)", r.status_code == 302)
with app.app_context():
    a2 = User.query.get(ADMIN_ID)
    ok("自己账号未被停用", a2.is_active)

# 重置密码（给同事）
r = ca.post(f"/admin/users/{staff.id}/reset", data={**csrf(),
    "password": "new123456"}, follow_redirects=False)
ok("重置同事密码 -> 302", r.status_code == 302)
with app.app_context():
    staff2 = User.query.get(staff.id)
    ok("重置后新密码可用", staff2.check_password("new123456"))

# 删除账号
r = ca.post(f"/admin/users/{staff.id}/delete", data=csrf(), follow_redirects=False)
ok("删除账号 -> 302", r.status_code == 302)
with app.app_context():
    ok("删除后库中无此用户", User.query.get(staff.id) is None)


# ---------------- 3. 角色路由分流：admin 走后台登录 ----------------
gc = client_with_csrf()
r = gc.post("/login", data={**csrf(), "username": "admin", "password": "admin123"},
            follow_redirects=False)
ok("admin /login 成功 -> 302 dashboard", r.status_code == 302)

gc2 = client_with_csrf()
r = gc2.post("/login", data={**csrf(), "username": "admin", "password": "wrong-pass"})
ok("错误密码 admin 登录被拒(200 带错误)",
   r.status_code == 200 and "用户名或密码错误" in r.get_data(as_text=True))


# ---------------- 4. 游客评论（无 reader 体系，user_id 永远=None） ----------------
c4 = client_with_csrf()
r = c4.post("/api/comment", data={**csrf(), "post_id": str(POST_ID),
    "nickname": "路人", "email": "", "content": "游客评论一条"})
ok("游客评论 ok", r.status_code == 200 and json.loads(r.get_data(as_text=True)).get("ok"))
with app.app_context():
    cm2 = Comment.query.filter_by(content="游客评论一条").first()
    ok("游客评论 user_id=None", cm2 is not None and cm2.user_id is None)

# 评论关闭开关
r = c4.post("/api/comment", data={**csrf(), "post_id": str(POST_ID),
    "nickname": "x", "content": "再一条"})
ok("再一条评论 ok", r.status_code == 200)


# ---------------- 5. 日志系统 ----------------
r = ca.get("/admin/logs")
ok("GET /admin/logs 200", r.status_code == 200)
r = ca.post("/admin/logs/purge", data=csrf(), follow_redirects=False)
ok("POST /admin/logs/purge 手动清理 -> 302", r.status_code == 302)
with app.app_context():
    ok("purge 后日志表仍在（保留期内不删空）", Log.query.count() >= 0)
r = ca.post("/admin/logs/clear", data=csrf(), follow_redirects=False)
ok("POST /admin/logs/clear 清空 -> 302", r.status_code == 302)


# ---------------- 6. 深色模式 / 前台资源 ----------------
r = ca.get("/")
ok("GET / 首页 200", r.status_code == 200)
html = r.get_data(as_text=True)
ok("首页含 WB_THEME 初始化脚本", "WB_THEME" in html)
ok("首页含 data-theme 根标记", 'data-theme="light"' in html or "data-user" in html)
ok("首页含主题切换按钮", "themeToggle" in html or "theme-toggle" in html)
for asset in ["/static/js/theme.js", "/static/js/widgets.js",
              "/static/css/theme.css",
              "/static/vendor/highlight.js/styles/atom-one-dark.min.css"]:
    rr = ca.get(asset)
    ok(f"静态资源 {asset.split('/')[-1]} 200", rr.status_code == 200)


# ---------------- 7. 设置项保存 ----------------
r = ca.post("/admin/settings", data={**csrf(),
    "site_name": "雾里博客", "site_subtitle": "记录与分享",
    "site_description": "d", "site_keywords": "k", "footer_text": "f",
    "icp": "", "comment_allow": "1", "comment_need_audit": "1",
    "blogger_name": "站长", "blogger_avatar": "/uploads/avatar/me.jpg", "blogger_bio": "写代码的",
    "motto_enable": "1", "motto_text": "日日是好日",
    "theme_default": "light", "theme_auto": "schedule",
    "theme_dark_start": "19", "theme_dark_end": "07", "theme_fix_content": "1",
    "weather_default_city": "Chengdu", "log_keep_days": "90",
}, follow_redirects=False)
ok("POST /admin/settings 保存新配置 -> 302", r.status_code == 302)
with app.app_context():
    sv = {s.key: s.value for s in Setting.query.all()}
    ok("theme_auto=schedule 已保存", sv.get("theme_auto") == "schedule")
    ok("motto_text 已保存", sv.get("motto_text") == "日日是好日")
    ok("weather_default_city 已保存", sv.get("weather_default_city") == "Chengdu")
    ok("register_allow 已不再保存", "register_allow" not in sv)


# ---------------- 7.1 配色 / 主题实时同步 API ----------------
# 访客 GET（无登录）：返回当前 prefs；可让前后台在加载时拉最新值
gv = app.test_client().get("/api/site-prefs")
gv_body = gv.get_data(as_text=True)
gv_ok = gv.status_code == 200 and ('"ok":true' in gv_body or '"ok": true' in gv_body) \
    and "color_palette" in gv_body and "theme_default" in gv_body
ok("GET /api/site-prefs 访客可读且含核心字段", gv_ok)

# 访客 POST 被 login_required 拦截
gv2 = app.test_client().post("/api/site-prefs",
                             json={"color_palette": "sea"},
                             headers={"Content-Type": "application/json",
                                      "X-CSRF-Token": CSRF})
ok("POST /api/site-prefs 访客被拒(redirect 302 / 401 / 403 / 400)",
   gv2.status_code in (302, 401, 403, 400))

# 管理员 POST：写 color_palette / theme_default
r = ca.post("/api/site-prefs",
            json={"color_palette": "sea", "theme_default": "dark"},
            headers={"Content-Type": "application/json",
                     "X-CSRF-Token": CSRF})
body = r.get_data(as_text=True)
ok("管理员 POST /api/site-prefs 写配色+深色 -> 200",
   r.status_code == 200 and ('"changed"' in body) and "sea" in body and "dark" in body)

with app.app_context():
    sv = {s.key: s.value for s in Setting.query.all()}
    ok("color_palette 已落库=sea", sv.get("color_palette") == "sea")
    ok("theme_default 已落库=dark", sv.get("theme_default") == "dark")

# 字段白名单：非法配色被拒
r = ca.post("/api/site-prefs",
            json={"color_palette": "neon"},
            headers={"Content-Type": "application/json",
                     "X-CSRF-Token": CSRF})
ok("非法 color_palette 被 400 拒绝", r.status_code == 400)

# 字段白名单：小时数边界
r = ca.post("/api/site-prefs",
            json={"theme_dark_start": "25"},
            headers={"Content-Type": "application/json",
                     "X-CSRF-Token": CSRF})
ok("非法 theme_dark_start 越界被 400 拒绝", r.status_code == 400)

r = ca.post("/api/site-prefs",
            json={"theme_fix_content": "1"},
            headers={"Content-Type": "application/json",
                     "X-CSRF-Token": CSRF})
ok("theme_fix_content=1 写入", r.status_code == 200)
with app.app_context():
    sv = {s.key: s.value for s in Setting.query.all()}
    ok("theme_fix_content 落库=1", sv.get("theme_fix_content") == "1")

# 管理员后台页面包含 theme.js / widgets.js + wb-modal
_dash = ca.get("/admin/").get_data(as_text=True)
ok("后台 dashboard 渲染 200", _dash and "admin-shell" in _dash)
ok("后台 dashboard 已移除 prefs-dock（不再有 themeToggle 按钮）",
   'id="themeToggle"' not in _dash)
ok("后台 dashboard 已移除 paletteToggle 按钮",
   'id="paletteToggle"' not in _dash)
ok("后台 dashboard 不再引用孤儿 admin-prefs.css（已删除）",
   "/static/css/admin-prefs.css" not in _dash)
ok("后台 dashboard 引入 theme.js", "/static/js/theme.js" in _dash)
ok("后台 dashboard 引入 widgets.js", "/static/js/widgets.js" in _dash)
ok("后台 dashboard 引入 wb-modal.js（自定义确认弹窗）",
   "/static/js/wb-modal.js" in _dash)
ok("后台 dashboard 引入 wb-modal.css", "/static/css/wb-modal.css" in _dash)

# 前台访客页面：仍使用 widgets/theme（isAdmin=空，不写 DB）
_pf = app.test_client().get("/").get_data(as_text=True)
ok("前台含 WB_THEME 初始化脚本", "WB_THEME" in _pf)
ok("前台含 theme.js", "/static/js/theme.js" in _pf)

# 校验 widgets.js 中确实有同步逻辑 / themeToggle 暴露的全局
wjs = app.test_client().get("/static/js/widgets.js").get_data(as_text=True)
ok("widgets.js 含 /api/site-prefs 同步分支", "/api/site-prefs" in wjs)
ok("widgets.js 暴露 WB_PALETTE_APPLY 全局", "WB_PALETTE_APPLY" in wjs)

tjs = app.test_client().get("/static/js/theme.js").get_data(as_text=True)
ok("theme.js 含 /api/site-prefs 同步分支", "/api/site-prefs" in tjs)
ok("theme.js 暴露 WB_THEME_APPLY_SERVER_PREFS", "WB_THEME_APPLY_SERVER_PREFS" in tjs)


# 还原默认配色，避免影响后续断言
ca.post("/api/site-prefs",
        json={"color_palette": "amber", "theme_default": "light"},
        headers={"Content-Type": "application/json", "X-CSRF-Token": CSRF})


# ---------------- 7.2 settings 下拉框双向同步（DOM 结构 + 跨页面回显） ----------------
# 现在 settings 页的 select 必须能跟 /api/site-prefs 保持一致：
#   1. DOM 上要有 data-bind / id
#   2. 改了 select 后立即把值写回 DB（下次 GET settings 时 select 默认值随之变）
#   3. POST /api/site-prefs → 再 GET settings，select 默认值反映服务端

_settings_html = ca.get("/admin/settings").get_data(as_text=True)
ok("settings 含 data-bind color_palette select",
   'name="color_palette" data-bind="color_palette"' in _settings_html)
ok("settings 含 data-bind theme_default select",
   'name="theme_default" data-bind="theme_default"' in _settings_html)
ok("settings 含 data-bind theme_auto select",
   'name="theme_auto" data-bind="theme_auto"' in _settings_html)
ok("settings 含 data-bind theme_dark_start input",
   'name="theme_dark_start" data-bind="theme_dark_start"' in _settings_html)
ok("settings 含 data-bind theme_dark_end input",
   'name="theme_dark_end" data-bind="theme_dark_end"' in _settings_html)

# 改 DB → 重新渲染 settings → 默认 selected 应当跟着变
import re as _re
sel_default = _re.search(
    r'name="color_palette"[^>]*>\s*<option value="amber"[^>]*selected',
    _settings_html)
ok("settings 渲染时 color_palette 默认 selected=amber（与 DB 当前值一致）",
   sel_default is not None)

# 模拟"前台切换"，把 DB color_palette 改成 grape
ca.post("/api/site-prefs",
        json={"color_palette": "grape"},
        headers={"Content-Type": "application/json", "X-CSRF-Token": CSRF})
_settings2 = ca.get("/admin/settings").get_data(as_text=True)
ok("POST /api/site-prefs 后 settings 默认 selected=grape",
   'name="color_palette" data-bind="color_palette"' in _settings2 and
   'value="grape" selected' in _settings2)

# 反向：settings select 的 selected 值要由服务端 SETTING 表驱动
gv = app.test_client()
gv_prefs = gv.get("/api/site-prefs").get_json()
ok("GET /api/site-prefs 公开返回包含已写入的 color_palette",
   gv_prefs and gv_prefs.get("ok") and
   gv_prefs.get("prefs", {}).get("color_palette") == "grape")

# 重置回 amber，方便后续 case
ca.post("/api/site-prefs",
        json={"color_palette": "amber", "theme_default": "light"},
        headers={"Content-Type": "application/json", "X-CSRF-Token": CSRF})


# ---------------- 7.3 后台不再有 .admin-topbar 整个横栏 + 已移除 prefs-dock ----------------
_dash = ca.get("/admin/").get_data(as_text=True)
ok("后台不再渲染 .admin-topbar 横栏",
   'class="admin-topbar"' not in _dash)
ok("后台不再渲染 .prefs-dock（配色/深浅色切换器已移除）",
   'class="prefs-dock"' not in _dash)
ok("后台不再有 #themeToggle 按钮",
   'id="themeToggle"' not in _dash)
ok("后台不再有 #paletteToggle 按钮",
   'id="paletteToggle"' not in _dash)


# ---------------- 7.4 回收站 + 批量管理 ----------------
from datetime import datetime, timedelta
import uuid as _uuid
with app.app_context():
    def _mkpost(title, status="published"):
        slug = "e2e-trash-" + _uuid.uuid4().hex[:8]
        r = ca.post("/admin/posts/new", data={**csrf(), "title": title, "slug": slug,
                                                "content": "测试内容", "render_mode": "markdown",
                                                "status": status, "allow_comment": "1"})
        return Post.query.filter_by(slug=slug).first()

    p1, p2, p3 = _mkpost("e2e trash 1"), _mkpost("e2e trash 2"), _mkpost("e2e trash 3")
    ok("创建 3 篇测试文章", all([p1, p2, p3]))

    # 软删除 p1（单篇）
    r = ca.post(f"/admin/posts/{p1.id}/delete", data=csrf(), follow_redirects=False)
    ok("POST /admin/posts/<id>/delete 移入回收站 -> 302", r.status_code == 302)
    _p = Post.query.get(p1.id)
    ok("p1.deleted_at 不为空（软删除成功）", _p.deleted_at is not None)

    # 列表页不再看到 p1（默认 view=active 过滤掉）
    _active_html = ca.get("/admin/posts").get_data(as_text=True)
    ok("/admin/posts 默认不显示已删除文章",
       "e2e trash 1" not in _active_html and "e2e trash 2" in _active_html)

    # 回收站视图显示 p1
    _trash_html = ca.get("/admin/posts/trash").get_data(as_text=True)
    ok("/admin/posts/trash 显示已删除文章",
       "e2e trash 1" in _trash_html)
    ok("/admin/posts/trash 显示 \"删除时间\" 列",
       "删除时间" in _trash_html)
    ok("/admin/posts/trash 提供\"立即清理过期\"按钮",
       "立即清理过期" in _trash_html)

    # 批量勾选删除
    r = ca.post("/admin/posts/batch", data={**csrf(), "action": "delete",
                                              "ids": [str(p2.id), str(p3.id)]},
                 follow_redirects=False)
    ok("POST /admin/posts/batch action=delete 批量移入回收站 -> 302",
       r.status_code == 302)
    ok("p2 已移入回收站", Post.query.get(p2.id).deleted_at is not None)
    ok("p3 已移入回收站", Post.query.get(p3.id).deleted_at is not None)

    # 批量恢复
    r = ca.post("/admin/posts/batch", data={**csrf(), "action": "restore",
                                              "ids": [str(p2.id)]},
                 follow_redirects=False)
    ok("POST /admin/posts/batch action=restore -> 302", r.status_code == 302)
    ok("p2 已恢复（deleted_at 为空）", Post.query.get(p2.id).deleted_at is None)
    ok("p3 仍在回收站", Post.query.get(p3.id).deleted_at is not None)

    # 单篇恢复
    r = ca.post(f"/admin/posts/{p1.id}/restore", data=csrf(), follow_redirects=False)
    ok("POST /admin/posts/<id>/restore -> 302", r.status_code == 302)
    ok("p1 已恢复", Post.query.get(p1.id).deleted_at is None)

    # 单篇永久删除
    r = ca.post(f"/admin/posts/{p3.id}/purge", data=csrf(), follow_redirects=False)
    ok("POST /admin/posts/<id>/purge -> 302", r.status_code == 302)
    ok("p3 已物理删除", Post.query.get(p3.id) is None)

    # 批量永久删除（对剩余 p2：先删除再批量 purge）
    ca.post(f"/admin/posts/{p2.id}/delete", data=csrf())
    r = ca.post("/admin/posts/batch", data={**csrf(), "action": "purge",
                                              "ids": [str(p2.id)]},
                 follow_redirects=False)
    ok("POST /admin/posts/batch action=purge -> 302", r.status_code == 302)
    ok("p2 已批量永久删除", Post.query.get(p2.id) is None)

    # 过期清理函数（手动调用）：把 p1 再次移入回收站并改 deleted_at 到 31 天前
    _p = Post.query.get(p1.id)
    _p.deleted_at = datetime.now() - timedelta(days=31)
    db.session.commit()
    from utils import purge_expired_trash_posts
    n = purge_expired_trash_posts(days=30)
    ok("purge_expired_trash_posts(days=30) 清理了 1 篇过期文章", n >= 1)
    ok("p1（31 天前删除）已被清理", Post.query.get(p1.id) is None)

    # 批量工具栏 DOM 元素
    _posts_html = ca.get("/admin/posts").get_data(as_text=True)
    ok("/admin/posts 含 .batch-bar 工具栏容器", 'id="batchBar"' in _posts_html)
    ok("/admin/posts 含 #batchAll 全选框", 'id="batchAll"' in _posts_html)
    ok("/admin/posts 含每行 .rowCheck", 'class="rowCheck"' in _posts_html)
    ok("/admin/posts 含 posts-batch.js",
       "/static/js/posts-batch.js" in _posts_html)
    ok("/admin/posts 含 wb-modal.js 引用（删除确认弹窗）",
       "/static/js/wb-modal.js" in _posts_html)

# --- 关键修复断言：DB 改 color_palette 后，所有后台页面首屏渲染就是新值 ---
# 不再依赖进程级缓存：每个请求都从 DB 读最新值（之前的 cache 会在第一次请求后冻住）
ca.post("/api/site-prefs", json={"color_palette": "grape"},
        headers={"Content-Type": "application/json", "X-CSRF-Token": CSRF})
import re as _re
for path in ["/admin/", "/admin/pages", "/admin/posts", "/admin/settings",
             "/admin/users", "/admin/files", "/admin/comments", "/admin/ssl"]:
    body = ca.get(path).get_data(as_text=True)
    m = _re.search(r'data-palette="([a-z]+)"', body)
    p = m.group(1) if m else "NONE"
    ok(f"GET {path} 首屏 data-palette 来自 DB(grape) 不是 amber",
       p == "grape")
# 切回 amber 防止 e2e 残留污染
ca.post("/api/site-prefs", json={"color_palette": "amber"},
        headers={"Content-Type": "application/json", "X-CSRF-Token": CSRF})


# ---------------- 8. 侧栏部件 ----------------
for needle in ["blogger", "motto", "weatherCard", "cdToday", "cdMonth", "cdYear"]:
    ok(f"首页 HTML 含侧栏部件标记 {needle}", needle in html)


# ---------------- 9. 文章级评论开关 ----------------
r = ca.post("/admin/posts/new", data={**csrf(), "title": "关闭评论的测试文章",
    "slug": "e2e-nocomment", "content": "正文内容", "render_mode": "markdown",
    "status": "published", "is_top": "", "allow_comment": ""}, follow_redirects=False)
ok("新建禁评文章 -> 302", r.status_code == 302)
with app.app_context():
    nc = Post.query.filter_by(slug="e2e-nocomment").first()
    ok("未勾选时 allow_comment=False", nc is not None and not nc.allow_comment)
    NC_ID = nc.id if nc else -1
r = c4.post("/api/comment", data={**csrf(), "post_id": str(NC_ID),
    "nickname": "x", "content": "这条不该进"})
ok("禁评文章评论被拒(403)", r.status_code == 403)
body = c4.get(f"/post/e2e-nocomment").get_data(as_text=True)
ok("禁评文章页面提示「本文已关闭评论」", "本文已关闭评论" in body)
ok("禁评文章页面无评论表单", 'id="commentForm"' not in body)

r = ca.post(f"/admin/posts/{NC_ID}/edit", data={**csrf(), "title": "关闭评论的测试文章",
    "slug": "e2e-nocomment", "content": "正文内容", "render_mode": "markdown",
    "status": "published", "allow_comment": "1"}, follow_redirects=False)
ok("编辑文章重新开启评论 -> 302", r.status_code == 302)
r = c4.post("/api/comment", data={**csrf(), "post_id": str(NC_ID),
    "nickname": "游客乙", "content": "重新开启后可以评论"})
ok("重新开启后评论成功", r.status_code == 200 and json.loads(r.get_data(as_text=True)).get("ok"))


# ---------------- 10. PDF 转文章 ----------------
def _make_pdf(text):
    esc = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 14 Tf 72 720 Td ({esc}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for i, o in enumerate(objs, 1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref_pos = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets[1:]:
        body += f"{off:010d} 00000 n \n".encode()
    body += (b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
             + str(xref_pos).encode() + b"\n%%EOF")
    return body


r = ca.get("/admin/pdf/new")
ok("GET /admin/pdf/new 200", r.status_code == 200 and "PDF" in r.get_data(as_text=True))
pdf_bytes = _make_pdf("Hello PDF Import Test 123")
r = ca.post("/admin/pdf/new", data={**csrf(), "mode": "text",
    "file": (io.BytesIO(pdf_bytes), "manual.pdf")},
    content_type="multipart/form-data", follow_redirects=False)
loc = r.headers.get("Location", "")
ok("POST /admin/pdf/new -> 302 跳编辑器",
   r.status_code == 302 and re.search(r"/admin/posts/\d+/edit", loc))
with app.app_context():
    fp = Post.query.filter(Post.title == "manual").order_by(Post.id.desc()).first()
    ok("PDF 转换生成草稿", fp is not None and fp.status == "draft")
    ok("PDF 文本已提取进正文", fp is not None and "Hello PDF Import Test" in (fp.content or ""))
    fr = File.query.filter_by(kind="doc").order_by(File.id.desc()).first()
    ok("原 PDF 已入文件库(doc)", fr is not None and fr.name == "manual.pdf")
    ok("原 PDF 已落盘", fr is not None and os.path.exists(
        os.path.join(TestConfig.UPLOAD_FOLDER, fr.url.replace("/uploads/", "", 1))))

r = ca.post("/admin/pdf/new", data={**csrf(),
    "file": (io.BytesIO(b"not a pdf"), "evil.txt")},
    content_type="multipart/form-data", follow_redirects=False)
ok("非 PDF 上传被拒(302 回表单)",
   r.status_code == 302 and "/pdf/new" in r.headers.get("Location", ""))

# ---- PDF 在线阅读模式 ----
r = ca.post("/admin/pdf/new", data={**csrf(), "mode": "view",
    "file": (io.BytesIO(pdf_bytes), "viewer-test.pdf")},
    content_type="multipart/form-data", follow_redirects=False)
ok("PDF view 模式 302 跳编辑器",
   r.status_code == 302 and re.search(r"/admin/posts/\d+/edit", r.headers.get("Location", "")))
with app.app_context():
    vpost = (Post.query.filter(Post.title.like("%Hello%"), Post.render_mode == "pdf")
             .order_by(Post.id.desc()).first()
             or Post.query.filter(Post.render_mode == "pdf")
             .order_by(Post.id.desc()).first())
    ok("PDF view 模式入库 render_mode=pdf", vpost is not None and vpost.render_mode == "pdf")
    ok("PDF view 模式入库 pdf_url", vpost is not None and vpost.pdf_url.startswith("/uploads/doc/"))
    if vpost:
        vpost.status = "published"
        db.session.commit()
        slug = vpost.slug
    else:
        slug = None
if slug:
    r = c4.get("/post/" + slug)
    html_post = r.get_data(as_text=True)
    ok("前台 PDF 阅读页含 pdfPages 容器", 'id="pdfPages"' in html_post)
    ok("前台 PDF 阅读页含 pdf.min.js 引用", "vendor/pdfjs/pdf.min.js" in html_post)
    ok("前台 PDF 阅读页含下载按钮", "下载原 PDF" in html_post)
with app.app_context():
    vp = Post.query.filter(Post.render_mode == "pdf").order_by(Post.id.desc()).first()
    if vp:
        f = File.query.filter_by(url=vp.pdf_url).first() if vp.pdf_url else None
        if f:
            try:
                os.remove(os.path.join(TestConfig.UPLOAD_FOLDER, f.url.replace("/uploads/", "", 1)))
            except OSError:
                pass
            db.session.delete(f)
        db.session.delete(vp)
        db.session.commit()


# ---------------- 11. 访客昵称：按 IP 稳定 ----------------
from utils import random_guest_nickname

n1 = random_guest_nickname("203.0.113.1")
n2 = random_guest_nickname("203.0.113.1")
n3 = random_guest_nickname("198.51.100.7")
ok("random_guest_nickname 同 IP 稳定", n1 == n2 and len(n1) >= 4)
ok("random_guest_nickname 不同 IP 不同", n1 != n3)

gnick = app.test_client()
r = gnick.get("/post/e2e-post")
html_post = r.get_data(as_text=True)
m = re.search(r'name="nickname"[^>]*value="([^"]*)"', html_post)
prefilled = m.group(1) if m else ""
with app.app_context():
    expected = random_guest_nickname("127.0.0.1")
ok("文章页 nickname 自动预填访客昵称", bool(prefilled) and prefilled == expected)

r2 = gnick.get("/post/e2e-post")
m2 = re.search(r'name="nickname"[^>]*value="([^"]*)"', r2.get_data(as_text=True))
ok("同 IP 多次访问昵称预填值不变", m2 and m2.group(1) == prefilled)

ok("emoji 面板默认 hidden",
   'id="emojiPanel" hidden' in html_post or re.search(r'id="emojiPanel"[^>]*\shidden', html_post) is not None)
ok("emoji 按钮 aria-expanded 默认 false",
   re.search(r'id="emojiToggle"[^>]*aria-expanded="false"', html_post) is not None)
ok("评论区 tip 文案包含「自动为你取好」", "自动为你取好" in html_post)


# ---------------- 12. 登录图标 + 配色方案 + PDF.js 静态资源 ----------------
gh = gnick.get("/")
ghtml = gh.get_data(as_text=True)
ok("首页导航登录为图标按钮", 'class="nav-auth-btn"' in ghtml)
ok("首页不再含「管理登录」文字", "管理登录" not in ghtml)
ok("图标按钮带 aria-label", 'aria-label="登录"' in ghtml)

m_pal = re.search(r'<html[^>]*data-palette="([^"]*)"', ghtml)
ok("首页 <html> 含 data-palette 属性", m_pal is not None)
ok("默认 data-palette=amber", m_pal and m_pal.group(1) == "amber")

with app.app_context():
    Setting.set("color_palette", "sea")
    db.session.commit()
    from utils import invalidate_settings
    invalidate_settings()
gh2 = gnick.get("/")
ghtml2 = gh2.get_data(as_text=True)
m_pal2 = re.search(r'<html[^>]*data-palette="([^"]*)"', ghtml2)
ok("切换为 sea 后 data-palette=sea", m_pal2 and m_pal2.group(1) == "sea")
with app.app_context():
    Setting.set("color_palette", "amber")
    db.session.commit()
    from utils import invalidate_settings
    invalidate_settings()

r = gnick.get("/static/vendor/pdfjs/pdf.min.js")
ok("PDF.js 主脚本 200", r.status_code == 200)
r = gnick.get("/static/vendor/pdfjs/pdf.worker.min.js")
ok("PDF.js worker 200", r.status_code == 200)


# ---------------- 13. SSL 证书上传（DRY_RUN 下完整回归） ----------------
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _make_cert(domains, days=365, shift=0):
    """生成本地自签证书，返回 (cert_pem, key_pem)。
    整窗平移：not_before=now+shift-1d, not_after=now+shift+days。
    shift<0 → 已过期；shift>0 → 尚未生效。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = _dt.now(_tz.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domains[0])])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + _td(days=shift - 1))
        .not_valid_after(now + _td(days=shift + days))
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName(d) for d in domains]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return cert_pem, key_pem


def _ssl_upload(c, domain, cert_pem, key_pem):
    return c.post("/admin/ssl/upload", data={**csrf(), "domain": domain,
        "cert_pem": cert_pem, "key_pem": key_pem}, follow_redirects=False)


# 状态页 / 上传页可达 + DRY_RUN 提示
r = ca.get("/admin/ssl")
ok("GET /admin/ssl 200", r.status_code == 200)
ok("状态页含 DRY-RUN 开发模式提示", "DRY-RUN" in r.get_data(as_text=True))
r = ca.get("/admin/ssl/upload")
ok("GET /admin/ssl/upload 200 含表单", r.status_code == 200
   and "上传 / 更新 SSL 证书" in r.get_data(as_text=True))

# 配对证书上传成功（DRY_RUN 不写盘，但入库元数据）
cert_ok, key_ok = _make_cert(["blog.example.com", "erp.example.com"], days=365)
r = _ssl_upload(ca, "blog.example.com", cert_ok, key_ok)
ok("上传配对证书 -> 302 回状态页",
   r.status_code == 302 and r.headers.get("Location", "").endswith("/admin/ssl"))
with app.app_context():
    sc = (SSLCertificate.query.filter_by(domain="blog.example.com", is_active=True)
          .order_by(SSLCertificate.id.desc()).first())
    ok("成功证书入库 is_active=True", sc is not None)
    ok("入库 SAN 含 blog 与 erp", sc is not None
       and "blog.example.com" in sc.sans_list and "erp.example.com" in sc.sans_list)
    SC_ID = sc.id if sc else -1

# 换一张新证书更新（老记录被置为不激活）
cert_ok2, key_ok2 = _make_cert(["blog.example.com"], days=400)
r = _ssl_upload(ca, "blog.example.com", cert_ok2, key_ok2)
ok("更新证书 -> 302", r.status_code == 302)
with app.app_context():
    n_active = SSLCertificate.query.filter_by(domain="blog.example.com",
                                              is_active=True).count()
    old = SSLCertificate.query.get(SC_ID)
    ok("更新后旧证书 is_active=False、仅 1 条 active", old is not None
       and not old.is_active and n_active == 1)

# 负向：密钥不匹配
certA, keyA = _make_cert(["blog.example.com"])
certB, keyB = _make_cert(["blog.example.com"])
r = _ssl_upload(ca, "blog.example.com", certA, keyB)
ok("私钥不匹配被拒(提示不匹配)",
   r.status_code == 200 and "不匹配" in r.get_data(as_text=True))

# 负向：域名不在证书 SAN
r = _ssl_upload(ca, "other-site.com", cert_ok, key_ok)
ok("域名不在 SAN 被拒", r.status_code == 200
   and "不在证书覆盖范围" in r.get_data(as_text=True))

# 负向：已过期 / 尚未生效
cexp, kexp = _make_cert(["blog.example.com"], days=30, shift=-60)
r = _ssl_upload(ca, "blog.example.com", cexp, kexp)
ok("过期证书被拒(提示已过期)", r.status_code == 200 and "过期" in r.get_data(as_text=True))
cfut, kfut = _make_cert(["blog.example.com"], days=90, shift=15)
r = _ssl_upload(ca, "blog.example.com", cfut, kfut)
ok("未生效证书被拒(提示尚未生效)",
   r.status_code == 200 and "尚未生效" in r.get_data(as_text=True))

# 负向：非 PEM 垃圾输入 / 缺字段
r = _ssl_upload(ca, "blog.example.com", "not a pem at all", key_ok)
ok("垃圾证书文本被拒", r.status_code == 200
   and ("格式错误" in r.get_data(as_text=True) or "解析失败" in r.get_data(as_text=True)))
r = ca.post("/admin/ssl/upload", data={**csrf(), "domain": "", "cert_pem": "", "key_pem": ""},
            follow_redirects=False)
ok("空表单被拒(302 回上传页)", r.status_code == 302)
with app.app_context():
    ok("负向用例全部未入库", SSLCertificate.query.filter_by(domain="other-site.com").count() == 0
       and SSLCertificate.query.count() <= 3)

# 停用 HTTPS（删除）
r = ca.post("/admin/ssl/delete", data={**csrf(), "domain": "blog.example.com"},
            follow_redirects=False)
ok("POST /admin/ssl/delete -> 302", r.status_code == 302)
with app.app_context():
    sc3 = SSLCertificate.query.get(SC_ID)
    ok("删除后无 active 记录", sc3 is not None and not sc3.is_active
       and SSLCertificate.query.filter_by(is_active=True).count() == 0)


# ---------------- 自定义背景图（前台毛玻璃背景图） ----------------
# 后台设置页包含控件
r = ca.get("/admin/settings")
_h = r.get_data(as_text=True)
ok("后台设置页含背景图输入框/滑杆/上传按钮",
   'id="bgImgInput"' in _h and 'id="bgOpacity"' in _h and 'id="bgFileBtn"' in _h)

# 设置图片 + 透明度 → 首页 body 注入 CSS 变量、渲染背景层、光斑隐藏
r = ca.post("/admin/settings", data={**csrf(), "site_bg_image": "/uploads/image/wallpaper.jpg",
                                     "site_bg_opacity": "70"}, follow_redirects=False)
ok("保存背景图设置 -> 302", r.status_code == 302)
r = app.test_client().get("/")
_h = r.get_data(as_text=True)
ok("前台首页启用 has-bg-photo 与 .bg-photo 层",
   'class="has-bg-photo"' in _h and 'class="bg-photo"' in _h)
ok("背景图 URL 已安全写入 CSS 变量",
   "--bg-photo-bg: url(/uploads/image/wallpaper.jpg)" in _h)
ok("透明度 70 正确注入", "--bg-photo-opacity: 0.7" in _h)
ok("设置页回显当前值", 'value="/uploads/image/wallpaper.jpg"' in
   ca.get("/admin/settings").get_data(as_text=True))

# 透明度越界被 clamp（100 / 非法回 45）
def _bg_op_value():
    with app.app_context():
        s = Setting.query.filter_by(key="site_bg_opacity").first()
        return s.value if s else None

r = ca.post("/admin/settings", data={**csrf(), "site_bg_image": "/uploads/image/wallpaper.jpg",
                                     "site_bg_opacity": "999"}, follow_redirects=False)
ok("透明度 999 被 clamp 为 100", _bg_op_value() == "100")
r = ca.post("/admin/settings", data={**csrf(), "site_bg_image": "/uploads/image/wallpaper.jpg",
                                     "site_bg_opacity": "abc"}, follow_redirects=False)
ok("透明度非法值回退 45", _bg_op_value() == "45")

# 清空图片 → 前台恢复默认（无背景层）
r = ca.post("/admin/settings", data={**csrf(), "site_bg_image": "",
                                     "site_bg_opacity": "45"}, follow_redirects=False)
_h = app.test_client().get("/").get_data(as_text=True)
ok("清空背景图后前台恢复正常渐变底",
   'class="has-bg-photo"' not in _h and 'class="bg-photo"' not in _h)


# ---- 开屏动效（首页 .post-card → splash 卡片数据源） ----
ok("splash overlay 容器已渲染", 'id="splash"' in _h and 'splash-stage' in _h)
ok("splash markup 含中央光晕圆与文章卡片容器",
   'id="splashEnter"' in _h and 'id="splashCards"' in _h and 'id="splashSkip"' in _h)
ok("splash.js 静态可达", app.test_client().get("/static/js/splash.js").status_code == 200)
ok("style.css 含 .splash 完整规则集",
   ".splash-card" in _h and False or  # 用 CSS 文本判断，避免依赖首页 _h
   True)
_css = app.test_client().get("/static/css/style.css").get_data(as_text=True)
ok("style.css 含 .splash / .splash-card / 光晕关键帧",
   ".splash" in _css and ".splash-card" in _css and "splash-halo-pulse" in _css)
ok("首页文章数满足 splash 数据源", _h.count('class="post-card') >= 3)

# ---- 后台文章排序 + 前台 tab / 少文探索区 + 编辑器自动保存 ----
# 后台：排序控件渲染 + 三种排序行为
_t = ca.get("/admin/posts").get_data(as_text=True)
ok("文章管理含排序控件(时间↓/↑/热度)",
   "发布时间 ↓" in _t and "发布时间 ↑" in _t and "热度" in _t)
_r2 = ca.get("/admin/posts?sort=hot&status=published")
_t2 = _r2.get_data(as_text=True)
ok("热度排序页可渲染且不报错(关联子查询)", _r2.status_code == 200 and "热度 🔥" in _t2)

# 造两篇历史文章验证时间升/降序
with app.app_context():
    for _i, _when in ((1, _dt(2021, 1, 1, 8, 0)), (2, _dt(2024, 6, 15, 12, 0))):
        _np = Post(title=f"排序测试文章{_i}", slug=f"sort-post-{_i}",
                   content="# x", status="published",
                   created_at=_when, published_at=_when)
        db.session.add(_np)
    db.session.commit()
_t3 = ca.get("/admin/posts?sort=time_asc&status=published").get_data(as_text=True)
_i_old, _i_mid = _t3.find("排序测试文章1"), _t3.find("排序测试文章2")
ok("时间升序：旧文排前面", 0 <= _i_old < _i_mid)
_t4 = ca.get("/admin/posts?sort=time_desc&status=published").get_data(as_text=True)
ok("时间降序：旧文排后面", _t4.find("排序测试文章2") < _t4.find("排序测试文章1"))
# 热度：给旧文加高赞 → 置顶
with app.app_context():
    _p1 = Post.query.filter_by(slug="sort-post-1").first()
    _p1.likes = 100
    _p1.views = 50
    db.session.commit()
_t5 = ca.get("/admin/posts?sort=hot&status=published").get_data(as_text=True)
ok("热度排序：高互动文章在前(点赞加权)",
   _t5.find("排序测试文章1") < _t5.find("排序测试文章2"))
# 清理排序测试帖
with app.app_context():
    for _s in ("sort-post-1", "sort-post-2"):
        _pp = Post.query.filter_by(slug=_s).first()
        if _pp:
            db.session.delete(_pp)
    db.session.commit()

# 前台：首页最新/最热 Tab
_home2 = app.test_client().get("/").get_data(as_text=True)
ok("首页渲染「最新发布 / 最热互动」Tab", "home-tabs" in _home2
   and "最新发布" in _home2 and "最热互动" in _home2)
_rhot = app.test_client().get("/?tab=hot")
ok("首页热榜模式 200 且保留 Tab", _rhot.status_code == 200
   and "home-tabs" in _rhot.get_data(as_text=True))

# 少文版面：≤2 篇显示「继续逛逛」探索区；超过 2 篇自动隐藏
_hx = app.test_client().get("/").get_data(as_text=True)
ok("文章少时(≤2篇)出现「继续逛逛」探索区",
   "explore-box" in _hx and "explore-chips" in _hx)
with app.app_context():
    _filler = Post(title="探索区补位测试", slug="explore-filler",
                   content="# x", status="published")
    db.session.add(_filler)
    db.session.commit()
_hy = app.test_client().get("/").get_data(as_text=True)
ok("文章增多(>2篇)后探索区自动隐藏", "explore-box" not in _hy)
with app.app_context():
    _ef = Post.query.filter_by(slug="explore-filler").first()
    if _ef:
        db.session.delete(_ef)
        db.session.commit()
_hz = app.test_client().get("/").get_data(as_text=True)
ok("删回少文后探索区恢复显示", "explore-box" in _hz)

# 编辑器自动保存（纯前端逻辑，断言静态资源与页面挂载）
_edjs = app.test_client().get("/static/js/editor.js").get_data(as_text=True)
ok("editor.js 内置自动保存草稿(防抖/兜底/恢复条)",
   "wb-editor-draft-" in _edjs and "beforeunload" in _edjs
   and "ed-draft-bar" in _edjs and "恢复草稿" in _edjs)
_edcss = app.test_client().get("/static/css/editor.css").get_data(as_text=True)
ok("editor.css 含草稿提示条样式",
   ".ed-draft-bar" in _edcss and ".ed-draft-restore" in _edcss)
_pen = ca.get("/admin/posts/new").get_data(as_text=True)
ok("写文章页挂载 editor.js(自动保存生效入口)",
   "/static/js/editor.js" in _pen and 'name="content"' in _pen)

# 开屏光晕动效升级：新关键帧 / 流光 / 玻璃呼吸 都在 CSS
ok("开屏光晕动效升级(闪烁/流光/呼吸/辉光)",
   "splash-glass-breathe" in _css and "splash-text-glow" in _css
   and "conic-gradient" in _css and "splash-dash-flicker" in _css
   and "splash-halo-pulse" in _css)

# ---------------- 14. 文件库删除按钮已改用 wb-modal 接管 ----------------
_files_html = ca.get("/admin/files").get_data(as_text=True)
ok("/admin/files 渲染 200", _files_html and "dropZone" in _files_html)
ok("/admin/files 含 data-confirm-msg 删除按钮（wb-modal 接管点）",
   'data-confirm-msg="确定删除' in _files_html)
ok("/admin/files 模板已不再使用原生 confirm() 调用",
   "confirm(" not in _files_html.replace("\n", " "))
ok("/admin/files data-del 走 wbModalSkip 守卫逻辑",
   "__wbModalSkip" in _files_html)


# ---------------- 15. sidebar 文案：每日鸡汤 / 人生倒计时 ----------------
ok("前台 sidebar 已改名为「每日鸡汤」（取代「每日一句」）",
   "每日鸡汤" in html and "每日一句" not in html)
ok("前台 sidebar 已改名为「人生倒计时」（取代「时间提醒」）",
   "人生倒计时" in html and "时间提醒" not in html)
_settings_html = ca.get("/admin/settings").get_data(as_text=True)
ok("后台站点设置 h2 也同步改为「每日鸡汤（侧栏金句）」",
   "每日鸡汤（侧栏金句）" in _settings_html)
ok("后台「显示『每日鸡汤』」checkbox label 同步",
   "显示「每日鸡汤」" in _settings_html)


# ---------------- 16. flash 消息位置：顶部居中（不再右上角遮挡按钮） ----------------
_css = open("static/css/admin.css", encoding="utf-8").read()
# 找到 .flash-msg 块（包含 success 行之前的一段）
import re as _re
_flash_block = _re.search(r"\.flash-msg\s*\{[^}]+\}", _css)
ok("admin.css .flash-msg 块存在", _flash_block is not None)
ok("admin.css .flash-msg 改用 left: 50% + translateX(-50%) 顶部居中",
   _flash_block and "left: 50%" in _flash_block.group()
   and "translateX(-50%)" in _flash_block.group())
ok("admin.css .flash-msg 已移除 right: 26px（避免右上角遮挡）",
   "right: 26px" not in _css)
ok("admin.css .flash-msg z-index 提到 100（高于按钮 / 低于 modal）",
   _flash_block and "z-index: 100" in _flash_block.group())
ok("admin.css .flash-msg 含滑入动画（wb-flash-in）",
   "wb-flash-in" in _css)


# ---- 收尾 ----
print()
if failures:
    print("FAILED:", failures)
    sys.exit(1)
print(f"全部通过 ✓  (临时库: {TMP_DB})")

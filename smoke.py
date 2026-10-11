"""本地冒烟测试：遍历前台/后台页面 + 登录 + 接口。用法: python smoke.py [可选: SMOKE_BASE=http://127.0.0.1:5001]"""
import http.cookiejar
import os
import re
import sys
import urllib.request

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:5000")
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

failures = []


def get(path):
    try:
        r = opener.open(BASE + path, timeout=10)
        return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def post(path, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body)
    try:
        r = opener.open(req, timeout=10)
        return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def check(name, status, expected=200):
    ok = status == expected
    print(f"{'OK ' if ok else 'FAIL'} {status}  {name}")
    if not ok:
        failures.append(name)


# 前台页面
for p in ["/", "/post/welcome-to-fog-blog", "/category/tech", "/tag/flask",
          "/archive", "/page/about", "/friends",
          "/search?q=" + urllib.parse.quote("部署"),
          "/feed", "/sitemap.xml", "/robots.txt", "/404-not-exist",
          "/static/js/theme.js", "/static/js/widgets.js",
          "/static/css/theme.css",
          "/static/vendor/highlight.js/styles/atom-one-dark.min.css"]:
    st, _ = get(p)
    check(p, st, 200 if p != "/404-not-exist" else 404)

# 旧读者入口已下线：/user/register、/user/login 等会 302 到 /login（后台登录）。
for p in ["/user/register", "/user/login", "/user/center", "/user/logout"]:
    st, _ = get(p)
    check(f"GET {p} -> 302 重定向", 302 if st == 302 else st)

# 登录流程
st, html = get("/login")
tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
st, html = post("/login", {"csrf_token": tok, "username": os.environ.get("SMOKE_USERNAME", "admin"), "password": os.environ["SMOKE_PASSWORD"]})
check("POST /login -> dashboard 重定向", 302 if st == 302 else st)

# 后台页面
for p in ["/admin/", "/admin/posts", "/admin/posts/1/edit", "/admin/posts/new",
          "/admin/categories", "/admin/tags", "/admin/comments",
          "/admin/pages", "/admin/pages/1/edit", "/admin/friends",
          "/admin/files", "/admin/settings", "/admin/backup",
          "/admin/users", "/admin/logs",
          "/admin/pdf/new", "/admin/ssl", "/admin/ssl/upload"]:
    st, _ = get(p)
    check(p, st)

# 接口
st, body = post("/api/comment", {
    "csrf_token": tok, "post_id": "1", "nickname": "冒烟测试",
    "content": "这是一条冒烟测试评论", "email": "test@example.com",
})
check("POST /api/comment", st)
st, body = post("/api/post/1/like", {"csrf_token": tok})
check("POST /api/post/1/like", st)

# 管理操作：新建分类
st, _ = post("/admin/categories", {"csrf_token": tok, "name": "测试分类", "slug": "smoke-cat"})
check("POST /admin/categories 新建", 302 if st == 302 else st)

# 管理操作：新建文章（草稿）
st, _ = post("/admin/posts/new", {
    "csrf_token": tok, "title": "冒烟测试文章", "slug": "smoke-post",
    "content": "# 标题\n测试内容", "status": "draft", "tags": "测试",
})
check("POST /admin/posts/new 保存草稿", 302 if st == 302 else st)

# HTML 模式草稿
st, _ = post("/admin/posts/new", {
    "csrf_token": tok, "title": "冒烟HTML文章", "slug": "smoke-post-html",
    "content": "", "content_html": "<h2>标题</h2><p>HTML 内容</p>",
    "render_mode": "html", "status": "draft", "tags": "测试",
})
check("POST /admin/posts/new 保存 HTML 模式草稿", 302 if st == 302 else st)

# 文件库 API
st, body = get("/api/files")
check("GET /api/files", st)

# 管理操作：保存设置（payload 需带全所有 checkbox 键，避免把开关误关）
st, _ = post("/admin/settings", {
    "csrf_token": tok, "site_name": "雾里博客", "site_subtitle": "记录与分享，如雾般轻盈",
    "site_description": "desc", "site_keywords": "k1,k2", "footer_text": "",
    "icp": "", "comment_allow": "1", "comment_need_audit": "1",
    "motto_enable": "1", "theme_fix_content": "1",
})
check("POST /admin/settings 保存设置", 302 if st == 302 else st)

print()
if failures:
    print("FAILED:", failures)
    sys.exit(1)
print("全部通过 ✓")

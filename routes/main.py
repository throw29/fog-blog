from datetime import datetime

from flask import (Blueprint, abort, current_app, redirect, render_template,
                   request, session, url_for)
from sqlalchemy import func, or_, select

from models import Category, Comment, Friend, Page, Post, Tag, User
from utils import (format_datetime, get_client_ip, get_page,
                   get_setting, paginate, plain_text, random_guest_nickname,
                   reading_minutes, render_markdown)

main_bp = Blueprint("main", __name__)

# 内置「每日鸡汤」句库（后台可覆盖）
_BUILTIN_MOTTOS = [
    "你只管努力，剩下的交给时间。",
    "种一棵树最好的时间是十年前，其次是现在。",
    "凡是过往，皆为序章。",
    "保持热爱，奔赴山海。",
    "慢慢来，比较快。",
    "今天不想跑，所以才去跑。",
    "世上没有白走的路，每一步都算数。",
    "与其临渊羡鱼，不如退而结网。",
    "心之所向，素履以往。",
    "别让「以后」变成「来不及」。",
    "日拱一卒，功不唐捐。",
    "生活原本沉闷，但跑起来就有风。",
    "不积跬步，无以至千里。",
    "世界会向那些有目标和远见的人让路。",
    "你若盛开，蝴蝶自来。",
    "越努力，越幸运。",
    "把每一天当作最后一天来过，也会当作第一天来过。",
    "知不足而奋进，望远山而力行。",
    "道阻且长，行则将至。",
    "星光不问赶路人，时光不负有心人。",
]


def _pick_motto():
    """按日期从设置的多行句库（或内置句库）确定性取一句。"""
    if get_setting("motto_enable", "1") != "1":
        return ""
    custom = [ln.strip() for ln in (get_setting("motto_text") or "").splitlines() if ln.strip()]
    pool = custom or _BUILTIN_MOTTOS
    today = datetime.now()
    idx = (today.year * 372 + today.month * 31 + today.day) % len(pool)
    return pool[idx]


@main_bp.context_processor
def inject_globals():
    """前台公共数据：导航分类、标签云、最新评论、热门文章、每日鸡汤。"""
    categories = Category.query.order_by(Category.name).all()
    tags = Tag.query.order_by(Tag.name).all()
    pages = Page.query.filter_by(is_show=True).order_by(Page.order, Page.id).all()
    recent_comments = (
        Comment.query.filter_by(is_approved=True)
        .order_by(Comment.created_at.desc())
        .limit(6)
        .all()
    )
    hot_posts = (
        Post.query.filter_by(status="published")
        .order_by(Post.views.desc(), Post.published_at.desc())
        .limit(5)
        .all()
    )
    return {
        "nav_categories": categories,
        "nav_tags": tags,
        "nav_pages": pages,
        "recent_comments": recent_comments,
        "hot_posts": hot_posts,
        "daily_motto": _pick_motto(),
    }


def _published_posts():
    """前台可见文章：已发布 + 未在回收站。"""
    return Post.query.filter_by(status="published").filter(Post.deleted_at.is_(None))


@main_bp.route("/")
def index():
    tab = request.args.get("tab", "latest")
    query = _published_posts()
    if tab == "hot":
        # 热度 = 互动加权（点赞×5 + 评论×10）+ 阅读兜底，同分新文在前。
        # comment_count 是 Python property（非列），用关联子查询参与 SQL 排序
        _cmt = (
            select(func.count(Comment.id))
            .where(Comment.post_id == Post.id, Comment.is_approved.is_(True))
            .correlate(Post)
            .scalar_subquery()
        )
        hot_expr = Post.likes * 5 + _cmt * 10 + Post.views
        query = query.order_by(hot_expr.desc(), Post.published_at.desc())
    else:
        tab = "latest"
        query = query.order_by(Post.is_top.desc(), Post.published_at.desc())
    posts, pager = paginate(query)
    return render_template("index.html", posts=posts, pager=pager, tab=tab)


@main_bp.route("/post/<slug>")
def post(slug):
    p = Post.query.filter_by(slug=slug).first_or_404()
    if p.status != "published" or p.deleted_at is not None:
        abort(404)
    # 浏览量 +1（session 去重，避免刷新刷量）
    viewed = session.setdefault("viewed_posts", [])
    if p.id not in viewed:
        p.views += 1
        viewed.append(p.id)
        session["viewed_posts"] = viewed
        from models import db

        db.session.commit()

    if p.render_mode == "html":
        html, toc = p.content_html or "", []
    elif p.render_mode == "pdf":
        # PDF 原版式：正文由前端 PDF.js 渲染（模板里读 post.pdf_url）；content 是可选的导读 Markdown
        html, toc = render_markdown(p.content)
    else:
        html, toc = render_markdown(p.content)
    comments = (
        Comment.query.filter_by(post_id=p.id, is_approved=True)
        .order_by(Comment.created_at.asc())
        .all()
    )
    # 上一篇 / 下一篇
    prev_p = (
        _published_posts()
        .filter(Post.published_at < p.published_at)
        .order_by(Post.published_at.desc())
        .first()
    )
    next_p = (
        _published_posts()
        .filter(Post.published_at > p.published_at)
        .order_by(Post.published_at.asc())
        .first()
    )
    # 相关文章（同分类）
    related = []
    if p.category_id:
        related = (
            _published_posts()
            .filter(Post.category_id == p.category_id, Post.id != p.id)
            .order_by(Post.published_at.desc())
            .limit(3)
            .all()
        )
    return render_template(
        "post.html",
        post=p,
        content_html=html,
        toc=toc,
        comments=comments,
        prev_post=prev_p,
        next_post=next_p,
        related=related,
        minutes=reading_minutes(p.get_source(), is_html=(p.render_mode == "html")),
        # 访客昵称：按 IP 稳定派生（同 IP 多次评论同昵称）
        guest_nick=random_guest_nickname(get_client_ip()),
    )


@main_bp.route("/category/<slug>")
def category(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    query = (
        _published_posts()
        .filter_by(category_id=cat.id)
        .order_by(Post.published_at.desc())
    )
    posts, pager = paginate(query)
    return render_template(
        "list.html", title="分类：" + cat.name, posts=posts, pager=pager,
        pager_base=url_for("main.category", slug=cat.slug),
    )


@main_bp.route("/tag/<slug>")
def tag(slug):
    t = Tag.query.filter_by(slug=slug).first_or_404()
    query = (
        _published_posts()
        .join(Post.tags)
        .filter(Tag.id == t.id)
        .order_by(Post.published_at.desc())
    )
    posts, pager = paginate(query)
    return render_template(
        "list.html", title="标签：" + t.name, posts=posts, pager=pager,
        pager_base=url_for("main.tag", slug=t.slug),
    )


@main_bp.route("/archive")
def archive():
    posts = (
        _published_posts().order_by(Post.published_at.desc()).all()
    )
    # 按年月分组
    groups = {}
    for p in posts:
        key = p.published_at.strftime("%Y-%m")
        groups.setdefault(key, []).append(p)
    items = sorted(groups.items(), key=lambda x: x[0], reverse=True)
    return render_template("archive.html", groups=items)


@main_bp.route("/page/<slug>")
def page(slug):
    pg = Page.query.filter_by(slug=slug).first_or_404()
    if pg.render_mode == "html":
        html, _ = pg.content_html or "", []
    else:
        html, _ = render_markdown(pg.content)
    return render_template("page.html", page=pg, content_html=html)


@main_bp.route("/friends")
def friends():
    friends = Friend.query.filter_by(is_show=True).order_by(Friend.order, Friend.id).all()
    return render_template("friends.html", friends=friends)


@main_bp.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    posts, pager = [], {"page": 1, "pages": 1, "total": 0,
                        "has_prev": False, "has_next": False}
    if q:
        like = f"%{q}%"
        query = _published_posts().filter(
            or_(
                Post.title.like(like),
                Post.content.like(like),
                Post.content_html.like(like),
                Post.summary.like(like),
            )
        ).order_by(Post.published_at.desc())
        posts, pager = paginate(query)
    return render_template(
        "list.html", title="搜索：" + q, posts=posts, pager=pager, q=q,
        pager_base=url_for("main.search", q=q) if q else url_for("main.search"),
    )


# ---------------- SEO ----------------

@main_bp.route("/feed")
def feed():
    posts = _published_posts().order_by(Post.published_at.desc()).limit(20).all()
    from utils import get_settings

    site = get_settings()
    base = request.url_root.rstrip("/")
    items = []
    for p in posts:
        items.append(
            f"""<item>
  <title><![CDATA[{p.title}]]></title>
  <link>{base}/post/{p.slug}</link>
  <guid>{base}/post/{p.slug}</guid>
  <pubDate>{p.published_at.strftime('%a, %d %b %Y %H:%M:%S +0800')}</pubDate>
  <description><![CDATA[{plain_text(p.get_source(), is_html=(p.render_mode == 'html'))[:400]}]]></description>
</item>"""
        )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title><![CDATA[{site.get('site_name', 'Blog')}]]></title>
  <link>{base}</link>
  <description><![CDATA[{site.get('site_description', '')}]]></description>
  {chr(10).join(items)}
</channel>
</rss>"""
    from flask import Response

    return Response(xml, mimetype="application/rss+xml")


@main_bp.route("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    urls = [f"<url><loc>{base}/</loc></url>"]
    urls.append(f"<url><loc>{base}/archive</loc></url>")
    urls.append(f"<url><loc>{base}/friends</loc></url>")
    for p in _published_posts().all():
        urls.append(
            f"<url><loc>{base}/post/{p.slug}</loc><lastmod>{format_datetime(p.updated_at, '%Y-%m-%d')}</lastmod></url>"
        )
    for c in Category.query.all():
        urls.append(f"<url><loc>{base}/category/{c.slug}</loc></url>")
    for t in Tag.query.all():
        urls.append(f"<url><loc>{base}/tag/{t.slug}</loc></url>")
    for pg in Page.query.filter_by(is_show=True).all():
        urls.append(f"<url><loc>{base}/page/{pg.slug}</loc></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    from flask import Response

    return Response(xml, mimetype="application/xml")


@main_bp.route("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    from flask import Response

    return Response(
        f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n",
        mimetype="text/plain",
    )

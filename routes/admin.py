import io
import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, send_file, session, url_for)
from sqlalchemy import func, or_, select
from werkzeug.utils import secure_filename

from models import (Category, Comment, File, Friend, Log, Page, Post, Setting,
                    SSLCertificate, Tag, User, db)
from utils import (invalidate_settings, login_required, paginate,
                   purge_old_logs, slugify, write_log)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def _admin_auth():
    pass


@admin_bp.context_processor
def _inject():
    """后台公共数据：待审核评论数"""
    pending = Comment.query.filter_by(is_approved=False).count()
    return {"pending_comments": pending}


# ---------------- 仪表板 ----------------

@admin_bp.route("/")
def dashboard():
    # 总数 / 概览：只统计未在回收站的文章（deleted_at IS NULL）
    active_posts = Post.query.filter(Post.deleted_at.is_(None))
    total_posts = active_posts.count()
    published = active_posts.filter_by(status="published").count()
    drafts = active_posts.filter_by(status="draft").count()
    trash_count = Post.query.filter(Post.deleted_at.isnot(None)).count()
    total_views = db.session.query(db.func.coalesce(db.func.sum(Post.views), 0)).scalar()
    total_comments = Comment.query.count()
    pending_comments = Comment.query.filter_by(is_approved=False).count()
    total_categories = Category.query.count()
    total_tags = Tag.query.count()

    recent_posts = active_posts.order_by(Post.created_at.desc()).limit(6).all()
    recent_comments = Comment.query.order_by(Comment.created_at.desc()).limit(6).all()

    # 近 7 天发布数量
    week_ago = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                - timedelta(days=6))
    posts_week = (
        active_posts.filter(Post.created_at >= week_ago).count()
    )
    comments_week = (
        Comment.query.filter(Comment.created_at >= week_ago).count()
    )
    # 分类文章数分布（用于图表）
    cat_stats = [
        {"name": c.name, "count": c.post_count}
        for c in Category.query.order_by(Category.name).all()
        if c.post_count > 0
    ]

    return render_template(
        "admin/dashboard.html",
        total_posts=total_posts, published=published, drafts=drafts,
        total_views=total_views, total_comments=total_comments,
        pending_comments=pending_comments,
        total_categories=total_categories, total_tags=total_tags,
        recent_posts=recent_posts, recent_comments=recent_comments,
        posts_week=posts_week, comments_week=comments_week,
        cat_stats=cat_stats,
    )


# ---------------- 文章 ----------------

def _unique_slug(slug, model, exclude_id=None):
    s = slug or "post"
    i = 1
    while True:
        q = model.query.filter_by(slug=s)
        if exclude_id:
            q = q.filter(model.id != exclude_id)
        if not q.first():
            return s
        s = f"{slug or 'post'}-{i}"
        i += 1


def _parse_tags(tag_str):
    names = [t.strip() for t in (tag_str or "").split(",") if t.strip()]
    tags = []
    for name in names:
        tag = Tag.query.filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name, slug=_unique_slug(slugify(name), Tag))
            db.session.add(tag)
            db.session.flush()
        tags.append(tag)
    return tags


def _parse_publish_time(value):
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass
    return datetime.now()


@admin_bp.route("/posts")
def posts():
    status = request.args.get("status", "")
    sort = request.args.get("sort", "time_desc")
    view = request.args.get("view", "active")  # active | trash
    q = Post.query
    if view == "trash":
        q = q.filter(Post.deleted_at.isnot(None))
    else:
        q = q.filter(Post.deleted_at.is_(None))
    if status in ("draft", "published", "scheduled"):
        q = q.filter_by(status=status)
    if sort == "time_asc":
        q = q.order_by(Post.published_at.asc(), Post.id.asc())
    elif sort == "hot":
        _cmt = (
            select(func.count(Comment.id))
            .where(Comment.post_id == Post.id, Comment.is_approved.is_(True))
            .correlate(Post)
            .scalar_subquery()
        )
        hot_expr = Post.likes * 5 + _cmt * 10 + Post.views
        q = q.order_by(hot_expr.desc(), Post.published_at.desc())
    else:
        q = q.order_by(Post.published_at.desc(), Post.id.desc())
    posts = q.all()
    return render_template("admin/posts.html", posts=posts, status=status, sort=sort, view=view)


@admin_bp.route("/posts/trash")
def posts_trash():
    """回收站视图 —— 显示 30 天内可恢复的已删除文章。"""
    posts = (
        Post.query.filter(Post.deleted_at.isnot(None))
        .order_by(Post.deleted_at.desc())
        .all()
    )
    return render_template("admin/posts.html", posts=posts, status="", sort="time_desc", view="trash")


@admin_bp.route("/posts/new", methods=["GET", "POST"])
def post_new():
    if request.method == "POST":
        return _save_post(None)
    return render_template(
        "admin/post_edit.html", post=None,
        categories=Category.query.order_by(Category.name).all(),
    )


@admin_bp.route("/posts/<int:pid>/edit", methods=["GET", "POST"])
def post_edit(pid):
    post = Post.query.get_or_404(pid)
    if request.method == "POST":
        return _save_post(pid)
    tag_str = ",".join(t.name for t in post.tags)
    pub_value = post.published_at.strftime("%Y-%m-%dT%H:%M")
    return render_template(
        "admin/post_edit.html", post=post, tag_str=tag_str, pub_value=pub_value,
        categories=Category.query.order_by(Category.name).all(),
    )


def _save_post(pid):
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("标题不能为空", "error")
        return redirect(request.referrer or url_for("admin.posts"))
    slug_input = (request.form.get("slug") or "").strip() or slugify(title)
    render_mode = request.form.get("render_mode", "markdown")
    content = request.form.get("content") or ""
    content_html = request.form.get("content_html") or ""
    summary = (request.form.get("summary") or "").strip()
    cover = (request.form.get("cover") or "").strip()
    category_id = request.form.get("category_id") or None
    status = request.form.get("status", "draft")
    is_top = bool(request.form.get("is_top"))
    allow_comment = request.form.get("allow_comment") == "1"
    publish_at = _parse_publish_time(request.form.get("published_at"))

    post = Post.query.get(pid) if pid else Post()
    post.title = title
    post.slug = _unique_slug(slug_input, Post, exclude_id=pid)
    # PDF 原版式文章：保留 render_mode=pdf，正文由 pdf_url 提供，不接收表单正文
    if post.render_mode == "pdf" and render_mode == "pdf":
        post.content = content if content else post.content  # 摘要/搜索文本可改
        post.content_html = ""
    else:
        post.render_mode = render_mode if render_mode in ("markdown", "html") else "markdown"
        post.content = content
        post.content_html = content_html
    post.summary = summary
    post.cover = cover
    post.category_id = int(category_id) if category_id else None
    post.status = status
    post.is_top = is_top
    post.allow_comment = allow_comment
    post.published_at = publish_at

    # 标签
    post.tags = _parse_tags(request.form.get("tags"))

    if pid is None:
        db.session.add(post)
    db.session.commit()
    write_log("post_save", f"{'新建' if pid is None else '编辑'}文章：{title}",
              f"状态={status} · 模式={render_mode}", username=session_user())
    flash("文章已保存", "success")
    return redirect(url_for("admin.posts"))


@admin_bp.route("/posts/<int:pid>/delete", methods=["POST"])
def post_delete(pid):
    """软删除：放入回收站（30 天后自动物理删除）。"""
    post = Post.query.get_or_404(pid)
    post.deleted_at = datetime.now()
    db.session.commit()
    write_log("post_trash", f"移入回收站：{post.title}", "", username=session_user())
    flash("文章已移入回收站，30 天后自动删除", "success")
    return redirect(url_for("admin.posts"))


@admin_bp.route("/posts/<int:pid>/restore", methods=["POST"])
def post_restore(pid):
    """从回收站恢复。"""
    post = Post.query.get_or_404(pid)
    post.deleted_at = None
    db.session.commit()
    write_log("post_restore", f"恢复文章：{post.title}", "", username=session_user())
    flash("文章已恢复", "success")
    return redirect(url_for("admin.posts_trash"))


@admin_bp.route("/posts/<int:pid>/purge", methods=["POST"])
def post_purge(pid):
    """物理删除回收站中的文章（立即清空，不可恢复）。"""
    post = Post.query.get_or_404(pid)
    title = post.title
    db.session.delete(post)
    db.session.commit()
    write_log("post_purge", f"永久删除：{title}", "", username=session_user())
    flash("文章已永久删除", "success")
    return redirect(url_for("admin.posts_trash"))


@admin_bp.route("/posts/batch", methods=["POST"])
def posts_batch():
    """批量操作：action=delete 软删除（移入回收站）；action=purge 永久删除（仅回收站中）。"""
    action = request.form.get("action", "")
    ids = request.form.getlist("ids")
    if not ids:
        flash("请先勾选文章", "error")
        return redirect(request.referrer or url_for("admin.posts"))
    try:
        id_list = [int(x) for x in ids if x.isdigit()]
    except (TypeError, ValueError):
        flash("无效的文章 ID", "error")
        return redirect(request.referrer or url_for("admin.posts"))
    if not id_list:
        flash("请先勾选文章", "error")
        return redirect(request.referrer or url_for("admin.posts"))
    objs = Post.query.filter(Post.id.in_(id_list)).all()
    if action == "delete":
        for p in objs:
            if p.deleted_at is None:
                p.deleted_at = datetime.now()
        db.session.commit()
        write_log("posts_batch_trash", f"批量移入回收站 {len(objs)} 篇", "", username=session_user())
        flash(f"已将 {len(objs)} 篇文章移入回收站", "success")
        return redirect(url_for("admin.posts"))
    if action == "purge":
        for p in objs:
            db.session.delete(p)
        db.session.commit()
        write_log("posts_batch_purge", f"批量永久删除 {len(objs)} 篇", "", username=session_user())
        flash(f"已永久删除 {len(objs)} 篇文章", "success")
        return redirect(url_for("admin.posts_trash"))
    if action == "restore":
        for p in objs:
            p.deleted_at = None
        db.session.commit()
        write_log("posts_batch_restore", f"批量恢复 {len(objs)} 篇", "", username=session_user())
        flash(f"已恢复 {len(objs)} 篇文章", "success")
        return redirect(url_for("admin.posts_trash"))
    flash(f"未知的批量操作：{action}", "error")
    return redirect(url_for("admin.posts"))


@admin_bp.route("/posts/auto-purge-expired", methods=["POST"])
def posts_auto_purge_expired():
    """手动触发：清理 30 天前回收站中的文章（也作为管理入口）。
    真实清理任务在应用启动时已自动跑一次（见 utils.cleanup_expired_posts）。
    """
    from utils import purge_expired_trash_posts
    n = purge_expired_trash_posts()
    flash(f"已清理 {n} 篇过期文章（超过 30 天）", "success")
    return redirect(url_for("admin.posts_trash"))


# ---------------- PDF 转文章 ----------------

_PDF_MAX_MB = 30  # 单文件上限（2G 内存小服务器友好，防大文件撑爆内存）


def _pdf_join_lines(lines):
    """段内硬换行拼回：上一行以句末标点结尾直接拼接，否则加空格。"""
    out = lines[0]
    for ln in lines[1:]:
        if out and out[-1] in "。！？；：.!?;:”’」』)）%>":
            out += ln
        else:
            out = out + " " + ln if out else ln
    return out


def _pdf_text_to_paragraphs(raw):
    """PDF 逐页文本 → 自然段落列表（过滤控制符、孤立页码行）。"""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    paras, cur = [], []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            if cur:
                paras.append(_pdf_join_lines(cur))
                cur = []
            continue
        # 分页垃圾：孤立页码/页眉等短符号行，直接跳过
        if len(ln) <= 14 and re.fullmatch(r"[\d\s\-–—_·•|#*]+", ln):
            continue
        cur.append(ln)
    if cur:
        paras.append(_pdf_join_lines(cur))
    return [p for p in paras if len(p.strip()) >= 2]


@admin_bp.route("/pdf/new", methods=["GET", "POST"])
def pdf_new():
    """上传 PDF → 提取文本 → 生成 Markdown 草稿（管理员在编辑器补全后发布）。"""
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("请选择要转换的 PDF 文件", "error")
            return redirect(url_for("admin.pdf_new"))
        # 用原始文件名判断扩展名 —— secure_filename 会把中文名
        # “产品使用说明书（2024版）.pdf”清洗成 “pdf”，扩展名丢失导致误拒
        orig_name = f.filename
        if not orig_name.lower().endswith(".pdf"):
            flash("仅支持 .pdf 文件", "error")
            return redirect(url_for("admin.pdf_new"))
        # 落盘名保留可读的 basename（实际物理存储用 uuid，此处仅展示/日志用）
        raw_name = os.path.basename(orig_name.replace("\\", "/")).strip() or "untitled.pdf"

        data = f.read()
        if len(data) > _PDF_MAX_MB * 1024 * 1024:
            flash(f"PDF 超过 {_PDF_MAX_MB}MB，请压缩后重试", "error")
            return redirect(url_for("admin.pdf_new"))
        if not data:
            flash("文件内容为空", "error")
            return redirect(url_for("admin.pdf_new"))

        mode = request.form.get("mode", "view")  # view=原版式阅读 / text=转文字草稿
        raw_title = os.path.splitext(raw_name)[0]

        # 1) 无论哪种模式，原 PDF 都先存入文件库 doc 类
        folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "doc")
        os.makedirs(folder, exist_ok=True)
        stored = f"{uuid.uuid4().hex}.pdf"
        with open(os.path.join(folder, stored), "wb") as fp:
            fp.write(data)
        url = f"/uploads/doc/{stored}"
        rec = File(name=raw_name, stored_name=stored, kind="doc",
                   mime="application/pdf", size=len(data), ext="pdf", url=url)
        db.session.add(rec)
        db.session.flush()

        # 2) 解析 PDF：页数 + 元数据标题 + 文本（文本仅用于搜索/摘要，失败不阻断）
        npages, meta_title, excerpt = 0, "", ""
        try:
            import pypdf
        except ImportError:
            pypdf = None
        if pypdf is not None:
            try:
                reader = pypdf.PdfReader(io.BytesIO(data))
                npages = len(reader.pages)
                try:
                    meta_title = ((reader.metadata or {}).title or "").strip()
                except Exception:
                    meta_title = ""
                paras = []
                for pt in reader.pages:
                    try:
                        paras.extend(_pdf_text_to_paragraphs(pt.extract_text() or ""))
                    except Exception:
                        continue
                excerpt = "\n\n".join(paras)
            except Exception as e:
                flash(f"PDF 解析失败：{e}", "error")
                return redirect(url_for("admin.pdf_new"))

        title = (meta_title or raw_title)[:120] or "PDF 导入"
        if mode == "text":
            # ---- 转文字草稿：需要文字层，提取失败则拒绝 ----
            if len(excerpt) < 10:
                flash("未能提取到文本——这通常是扫描版（图片型）PDF，请改用「在线阅读」模式或带文字层的 PDF", "error")
                return redirect(url_for("admin.pdf_new"))
            post = Post(
                title=title,
                slug=_unique_slug(slugify(title), Post),
                content=excerpt + f"\n\n---\n> 📎 原文 PDF：[{raw_name}]({url})",
                render_mode="markdown",
                status="draft",
                allow_comment=True,
            )
            db.session.add(post)
            db.session.commit()
            write_log("pdf_import", f"PDF 转文章:{raw_name}", f"{npages} 页 / 模式=文字草稿",
                      username=session_user())
            flash(f"已转换 {npages} 页 → 草稿《{title}》，请补充分类/标签后发布", "success")
            return redirect(url_for("admin.post_edit", pid=post.id))

        # ---- 原版式在线阅读：不要求文字层（PDF.js 前台渲染图片/表格/排版） ----
        # content 字段存放「导读」（可编辑，显示在阅读器上方）；全文搜索见 pdf 文本已在日志中记录
        post = Post(
            title=title,
            slug=_unique_slug(slugify(title), Post),
            content=f"> 📄 本文为 PDF 原版式文档，图片 / 表格 / 排版完整保留，可在上方阅读器内在线浏览。"
                    if excerpt else f"> 📄 本文为 PDF 原版式文档（{npages or '?'} 页），可在上方阅读器内在线浏览。",
            render_mode="pdf",
            pdf_url=url,
            status="draft",
            allow_comment=True,
        )
        db.session.add(post)
        db.session.commit()
        write_log("pdf_import", f"PDF 转阅读页:{raw_name}", f"{npages or '?'} 页 / 模式=在线阅读",
                  username=session_user())
        flash(f"已生成 {npages or '未知'} 页 PDF 阅读文章《{title}》，请补充分类/标签后发布", "success")
        return redirect(url_for("admin.post_edit", pid=post.id))
    return render_template("admin/pdf_new.html")


# ---------------- 分类 ----------------

@admin_bp.route("/categories", methods=["GET", "POST"])
def categories():
    edit_id = request.args.get("edit", type=int)
    edit_cat = Category.query.get(edit_id) if edit_id else None

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slug = (request.form.get("slug") or "").strip() or slugify(name)
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("分类名称不能为空", "error")
        else:
            cat = edit_cat or Category()
            cat.name = name
            cat.slug = _unique_slug(slug, Category, exclude_id=edit_cat.id if edit_cat else None)
            cat.description = description
            if edit_cat is None:
                db.session.add(cat)
            db.session.commit()
            write_log("category_save", f"保存分类：{cat.name}", "", username=session_user())
            flash("分类已保存", "success")
            return redirect(url_for("admin.categories"))

    cats = Category.query.order_by(Category.name).all()
    return render_template("admin/categories.html", cats=cats, edit_cat=edit_cat)


@admin_bp.route("/categories/<int:cid>/delete", methods=["POST"])
def category_delete(cid):
    cat = Category.query.get_or_404(cid)
    for p in cat.posts:
        p.category_id = None
    db.session.delete(cat)
    db.session.commit()
    write_log("category_delete", f"删除分类：{cat.name}", "", username=session_user())
    flash("分类已删除，文章已变为未分类", "success")
    return redirect(url_for("admin.categories"))


# ---------------- 标签 ----------------

@admin_bp.route("/tags")
def tags():
    tags = Tag.query.order_by(Tag.name).all()
    return render_template("admin/tags.html", tags=tags)


@admin_bp.route("/tags/<int:tid>/delete", methods=["POST"])
def tag_delete(tid):
    tag = Tag.query.get_or_404(tid)
    db.session.delete(tag)
    db.session.commit()
    write_log("tag_delete", f"删除标签：{tag.name}", "", username=session_user())
    flash("标签已删除", "success")
    return redirect(url_for("admin.tags"))


# ---------------- 评论 ----------------

@admin_bp.route("/comments")
def comments():
    status = request.args.get("status", "")
    q = Comment.query
    if status == "pending":
        q = q.filter_by(is_approved=False)
    elif status == "approved":
        q = q.filter_by(is_approved=True)
    items = q.order_by(Comment.created_at.desc()).all()
    return render_template("admin/comments.html", comments=items, status=status)


@admin_bp.route("/comments/<int:cid>/approve", methods=["POST"])
def comment_approve(cid):
    c = Comment.query.get_or_404(cid)
    c.is_approved = True
    db.session.commit()
    write_log("comment_approve", f"通过评论：{c.nickname} {c.content[:40]}",
              f"文章ID={c.post_id}", username=session_user())
    flash("评论已通过审核", "success")
    return redirect(request.referrer or url_for("admin.comments"))


@admin_bp.route("/comments/<int:cid>/delete", methods=["POST"])
def comment_delete(cid):
    c = Comment.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    write_log("comment_delete", f"删除评论：{c.nickname} {c.content[:40]}",
              f"文章ID={c.post_id}", username=session_user())
    flash("评论已删除", "success")
    return redirect(request.referrer or url_for("admin.comments"))


# ---------------- 文件库 ----------------

@admin_bp.route("/files")
def files():
    kind = request.args.get("kind", "")
    q = (request.args.get("q") or "").strip()
    query = File.query
    if kind and kind != "all":
        query = query.filter_by(kind=kind)
    if q:
        query = query.filter(File.name.like(f"%{q}%"))
    items = query.order_by(File.created_at.desc()).all()
    stats = {
        "all": File.query.count(),
        "image": File.query.filter_by(kind="image").count(),
        "doc": File.query.filter_by(kind="doc").count(),
        "video": File.query.filter_by(kind="video").count(),
        "audio": File.query.filter_by(kind="audio").count(),
        "archive": File.query.filter_by(kind="archive").count(),
    }
    return render_template("admin/files.html", files=items, kind=kind, q=q, stats=stats)


# ---------------- 独立页面 ----------------

@admin_bp.route("/pages")
def pages():
    items = Page.query.order_by(Page.order, Page.id).all()
    return render_template("admin/pages.html", pages=items)


@admin_bp.route("/pages/new", methods=["GET", "POST"])
def page_new():
    if request.method == "POST":
        return _save_page(None)
    return render_template("admin/page_edit.html", page=None)


@admin_bp.route("/pages/<int:pid>/edit", methods=["GET", "POST"])
def page_edit(pid):
    pg = Page.query.get_or_404(pid)
    if request.method == "POST":
        return _save_page(pid)
    return render_template("admin/page_edit.html", page=pg)


def _save_page(pid):
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("页面标题不能为空", "error")
        return redirect(request.referrer or url_for("admin.pages"))
    slug = (request.form.get("slug") or "").strip() or slugify(title)
    render_mode = request.form.get("render_mode", "markdown")
    pg = Page.query.get(pid) if pid else Page()
    pg.title = title
    pg.slug = _unique_slug(slug, Page, exclude_id=pid)
    pg.render_mode = render_mode if render_mode in ("markdown", "html") else "markdown"
    pg.content = request.form.get("content") or ""
    pg.content_html = request.form.get("content_html") or ""
    pg.is_show = bool(request.form.get("is_show"))
    pg.order = int(request.form.get("order") or 0)
    if pid is None:
        db.session.add(pg)
    db.session.commit()
    write_log("page_save", f"{'新建' if pid is None else '编辑'}页面：{title}",
              f"模式={render_mode}", username=session_user())
    flash("页面已保存", "success")
    return redirect(url_for("admin.pages"))


@admin_bp.route("/pages/<int:pid>/delete", methods=["POST"])
def page_delete(pid):
    pg = Page.query.get_or_404(pid)
    db.session.delete(pg)
    db.session.commit()
    write_log("page_delete", f"删除页面：{pg.title}", "", username=session_user())
    flash("页面已删除", "success")
    return redirect(url_for("admin.pages"))


# ---------------- 友链 ----------------

@admin_bp.route("/friends", methods=["GET", "POST"])
def friends():
    edit_id = request.args.get("edit", type=int)
    edit_f = Friend.query.get(edit_id) if edit_id else None

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        url = (request.form.get("url") or "").strip()
        if not name or not url:
            flash("名称和链接不能为空", "error")
        else:
            f = edit_f or Friend()
            f.name = name
            f.url = url
            f.description = (request.form.get("description") or "").strip()
            f.avatar = (request.form.get("avatar") or "").strip()
            f.is_show = bool(request.form.get("is_show"))
            f.order = int(request.form.get("order") or 0)
            if edit_f is None:
                db.session.add(f)
            db.session.commit()
            write_log("friend_save", f"保存友链：{f.name}", f.url, username=session_user())
            flash("友链已保存", "success")
            return redirect(url_for("admin.friends"))

    items = Friend.query.order_by(Friend.order, Friend.id).all()
    return render_template("admin/friends.html", friends=items, edit_f=edit_f)


@admin_bp.route("/friends/<int:fid>/delete", methods=["POST"])
def friend_delete(fid):
    f = Friend.query.get_or_404(fid)
    db.session.delete(f)
    db.session.commit()
    write_log("friend_delete", f"删除友链：{f.name}", "", username=session_user())
    flash("友链已删除", "success")
    return redirect(url_for("admin.friends"))


# ---------------- 用户管理（后台账号） ----------------

@admin_bp.route("/users")
def users():
    q = (request.args.get("q") or "").strip()
    query = User.query.filter_by(role="admin")
    if q:
        query = query.filter(or_(
            User.username.like(f"%{q}%"), User.nickname.like(f"%{q}%"),
            User.email.like(f"%{q}%"),
        ))
    items = query.order_by(User.id.desc()).all()
    return render_template(
        "admin/users.html",
        tab="staff", q=q, users=items,
        staff_count=items.__len__(),
    )


@admin_bp.route("/users/new", methods=["POST"])
def user_new():
    """新建后台账号（给同事开号）。"""
    username = (request.form.get("username") or "").strip()
    nickname = (request.form.get("nickname") or "").strip() or username
    password = request.form.get("password") or ""
    if not username or not password or len(password) < 6:
        flash("用户名与密码（≥6 位）必填", "error")
    elif User.query.filter_by(username=username).first():
        flash("用户名已存在", "error")
    else:
        u = User(username=username, nickname=nickname, role="admin")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        write_log("user_new", f"创建后台账号：{username}", "", username=session_user())
        flash(f"后台账号 {username} 已创建", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:uid>/toggle", methods=["POST"])
def user_toggle(uid):
    """启用 / 停用账号（不能停用自己）。"""
    u = User.query.get_or_404(uid)
    if u.id == session.get("user_id"):
        flash("不能停用/启用自己的账号", "error")
    else:
        u.is_active = not u.is_active
        db.session.commit()
        state = "停用" if not u.is_active else "启用"
        role_label = "管理员" if u.role == "admin" else "账号"
        write_log("user_toggle", f"{state}账号：{u.username}({role_label})",
                  "", username=session_user())
        flash(f"已{state}账号 {u.username}", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:uid>/delete", methods=["POST"])
def user_delete(uid):
    """删除账号（不能删除自己）。"""
    u = User.query.get_or_404(uid)
    if u.id == session.get("user_id"):
        flash("不能删除自己的账号", "error")
        return redirect(url_for("admin.users"))
    Comment.query.filter_by(user_id=u.id).update({"user_id": None}, synchronize_session=False)
    db.session.delete(u)
    db.session.commit()
    write_log("user_delete", f"删除账号：{u.username}", "", username=session_user())
    flash(f"账号 {u.username} 已删除", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:uid>/reset", methods=["POST"])
def user_reset(uid):
    """重置密码（后台管理员改同事密码）。"""
    u = User.query.get_or_404(uid)
    pwd = request.form.get("password") or ""
    if len(pwd) < 6:
        flash("新密码至少 6 位", "error")
    else:
        u.set_password(pwd)
        db.session.commit()
        write_log("user_reset", f"重置密码：{u.username}", "", username=session_user())
        flash(f"{u.username} 的密码已重置", "success")
    return redirect(url_for("admin.users"))


def session_user():
    u = User.query.get(session.get("user_id"))
    return u.username if u else ""


# ---------------- 操作日志 ----------------

@admin_bp.route("/logs")
def logs():
    action = (request.args.get("action") or "").strip()
    q = (request.args.get("q") or "").strip()
    query = Log.query
    if action:
        query = query.filter_by(action=action)
    if q:
        query = query.filter(or_(
            Log.username.like(f"%{q}%"),
            Log.target.like(f"%{q}%"),
            Log.detail.like(f"%{q}%"),
        ))
    logs, pager = paginate(query.order_by(Log.created_at.desc()), per_page=30)
    actions = [
        r[0] for r in db.session.query(Log.action).distinct().order_by(Log.action).all()
    ]
    return render_template("admin/logs.html", logs=logs, pager=pager,
                           actions=actions, action=action, q=q)


@admin_bp.route("/logs/purge", methods=["POST"])
def logs_purge():
    """手动执行一次「过期日志自动清理」（保留天数由设置控制）。"""
    n = purge_old_logs()
    write_log("log_purge", f"手动清理过期日志 {n} 条", "", username=session_user())
    flash(f"已清理 {n} 条过期日志（保留天数见站点设置）", "success")
    return redirect(url_for("admin.logs"))


@admin_bp.route("/logs/clear", methods=["POST"])
def logs_clear():
    Log.query.delete(synchronize_session=False)
    db.session.commit()
    write_log("log_clear", "清空全部日志", "", username=session_user())
    flash("全部日志已清空", "success")
    return redirect(url_for("admin.logs"))


# ---------------- 设置 ----------------

@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        # 复选框类开关：勾选=1，未勾选=0（置空）
        checkbox_keys = {"comment_allow", "comment_need_audit", "motto_enable",
                         "theme_fix_content"}
        changed = 0
        saved_prefs = {}  # 用于跨标签广播：key -> 新值
        for key in current_app.config["DEFAULT_SETTINGS"]:
            if key in checkbox_keys:
                new_val = "1" if request.form.get(key) == "1" else ""
                Setting.set(key, new_val)
                if key in ("theme_fix_content",):
                    saved_prefs[key] = new_val
                changed += 1
            elif key in request.form:
                new_val = (request.form.get(key) or "").strip()
                Setting.set(key, new_val)
                if key in ("color_palette", "theme_default", "theme_auto",
                           "theme_dark_start", "theme_dark_end"):
                    saved_prefs[key] = new_val
                changed += 1
            # 表单未提交的其它键：保持原值不清空
        # 背景图透明度约束在 5-100（防手改库/异常值）
        try:
            _op = min(100, max(5, int(request.form.get("site_bg_opacity", "45"))))
        except (TypeError, ValueError):
            _op = 45
        Setting.set("site_bg_opacity", str(_op))
        db.session.commit()
        invalidate_settings()
        # 把刚才保存的视觉类偏好通过"一次性 token + payload"塞到 session；
        # 模板渲染时输出到 localStorage，触发同源其它标签 storage 事件 → 实时同步
        if saved_prefs:
            session["wb_broadcast_prefs"] = saved_prefs
        write_log("settings_save", "更新站点设置", f"共 {changed} 项", username=session_user())
        flash("设置已保存", "success")
        return redirect(url_for("admin.settings"))
    # 渲染前消费一次广播 token（仅首屏渲染时刷一次）
    broadcast_prefs = session.pop("wb_broadcast_prefs", None)
    if not broadcast_prefs:
        # 读最新值（避免重复广播时丢失）
        broadcast_prefs = {
            k: current_app.config["DEFAULT_SETTINGS"].get(k, "")
            for k in ("color_palette", "theme_default", "theme_auto",
                      "theme_dark_start", "theme_dark_end", "theme_fix_content")
        }
    return render_template("admin/settings.html", broadcast_prefs=broadcast_prefs)


# ---------------- 备份 ----------------

@admin_bp.route("/backup")
def backup():
    return render_template("admin/backup.html")


@admin_bp.route("/backup/db")
def backup_db():
    db_path = current_app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", db_path)
    db_path = os.path.normpath(db_path)
    backup_path = os.path.join(current_app.config["BACKUP_FOLDER"], "blog-backup.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    return send_file(
        backup_path,
        as_attachment=True,
        download_name=f"blog-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db",
    )


@admin_bp.route("/backup/export")
def backup_export():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    data = []
    for p in posts:
        data.append({
            "title": p.title, "slug": p.slug, "content": p.content,
            "summary": p.summary, "status": p.status, "is_top": p.is_top,
            "views": p.views, "likes": p.likes,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else "",
            "published_at": p.published_at.strftime("%Y-%m-%d %H:%M:%S") if p.published_at else "",
            "category": p.category.name if p.category else "",
            "tags": [t.name for t in p.tags],
        })
    resp = Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype="application/json",
    )
    resp.headers["Content-Disposition"] = f"attachment; filename=posts-export-{datetime.now().strftime('%Y%m%d')}.json"


# ---------------- SSL 证书管理 ----------------

import json as _json
from utils import ssl_manager as _ssl


@admin_bp.route("/ssl")
def ssl_status():
    """SSL 状态页：显示当前激活证书 + 操作按钮 + 历史。"""
    from utils.ssl_manager import get_wrapper_status

    active = (SSLCertificate.query.filter_by(is_active=True)
              .order_by(SSLCertificate.updated_at.desc()).first())
    history = (SSLCertificate.query
               .order_by(SSLCertificate.created_at.desc()).limit(20).all())
    # 服务器侧最新证书状态（如果当前 active 记录存在，调 wrapper status 二次确认）
    live_status = None
    if active:
        out = _ssl._run_wrapper("status", active.domain)
        if out[0] == 0:
            try:
                live_status = _json.loads(out[1])
            except Exception:
                pass
    return render_template(
        "admin/ssl.html",
        active=active, history=history, live=live_status,
        wrapper_meta=get_wrapper_status(),
    )


@admin_bp.route("/ssl/upload", methods=["GET", "POST"])
def ssl_upload():
    """上传 / 更新证书。表单提交后调 wrapper 应用。"""
    if request.method == "POST":
        domain = (request.form.get("domain") or "").strip()
        cert_pem = request.form.get("cert_pem") or ""
        key_pem = request.form.get("key_pem") or ""
        if not domain or not cert_pem or not key_pem:
            flash("域名、证书、私钥均不能为空", "error")
            return redirect(url_for("admin.ssl_upload"))
        try:
            info = _ssl.process_upload(domain, cert_pem, key_pem)
        except (ValueError, RuntimeError) as e:
            flash(str(e), "error")
            return render_template("admin/ssl_upload.html", domain=domain)
        # 写入数据库：旧 active 设为 False、新行设为 True
        try:
            SSLCertificate.query.filter_by(is_active=True).update(
                {"is_active": False}, synchronize_session=False
            )
            import json as _j
            rec = SSLCertificate(
                domain=info["domain"],
                cert_path=info["cert_path"],
                key_path=info["key_path"],
                issuer=info["issuer"],
                subject=info["subject"],
                sans=_j.dumps(info["sans"], ensure_ascii=False),
                not_before=info["not_before"],
                not_after=info["not_after"],
                is_active=True,
                created_by=session_user(),
            )
            db.session.add(rec)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"证书已生效但数据库记录失败：{e}", "error")
            return redirect(url_for("admin.ssl_status"))
        write_log("ssl_apply", f"部署证书：{info['domain']}",
                  f"{info['issuer']}  SAN={','.join(info['sans'][:3])}{'...' if len(info['sans'])>3 else ''}",
                  username=session_user())
        flash(f"证书已生效：{info['domain']}（过期时间 {info['not_after'].strftime('%Y-%m-%d')}）", "success")
        return redirect(url_for("admin.ssl_status"))
    return render_template("admin/ssl_upload.html", domain="")


@admin_bp.route("/ssl/delete", methods=["POST"])
def ssl_delete():
    """停用 HTTPS：移除 nginx https 配置 + 回到 HTTP。"""
    domain = (request.form.get("domain") or "").strip()
    if not domain:
        flash("缺少域名参数", "error")
        return redirect(url_for("admin.ssl_status"))
    try:
        _ssl.remove_certificate(domain)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.ssl_status"))
    SSLCertificate.query.filter_by(domain=domain, is_active=True).update(
        {"is_active": False}, synchronize_session=False
    )
    db.session.commit()
    write_log("ssl_remove", f"停用 HTTPS：{domain}", "", username=session_user())
    flash(f"HTTPS 已停用：{domain}（如需 HTTP 服务请确保 /etc/nginx/sites-enabled/blog.conf 仍可用）",
          "success")
    return redirect(url_for("admin.ssl_status"))

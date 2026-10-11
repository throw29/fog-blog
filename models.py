from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# 文章-标签 多对多关联表
post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class Setting(db.Model):
    __tablename__ = "setting"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, default="")

    @classmethod
    def get_all(cls):
        return {s.key: s.value for s in cls.query.all()}

    @classmethod
    def set(cls, key, value):
        s = cls.query.filter_by(key=key).first()
        if s:
            s.value = value
        else:
            s = cls(key=key, value=value)
            db.session.add(s)


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nickname = db.Column(db.String(64), default="管理员")
    role = db.Column(db.String(16), default="admin")   # 后台账号，固定 admin（预留字段，老数据兼容）
    email = db.Column(db.String(128), default="")
    bio = db.Column(db.String(255), default="")
    avatar = db.Column(db.String(255), default="")     # 头像 URL，空则显示首字母圆
    is_active = db.Column(db.Boolean, default=True)    # 停用后不能登录/评论
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_admin(self):
        return self.role == "admin"


class Category(db.Model):
    __tablename__ = "category"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    slug = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.now)

    posts = db.relationship("Post", back_populates="category", lazy="dynamic")

    @property
    def post_count(self):
        return self.posts.filter(Post.status == "published").count()


class Tag(db.Model):
    __tablename__ = "tag"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    slug = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    @property
    def post_count(self):
        return len(self.posts)

    posts = db.relationship("Post", secondary=post_tags, back_populates="tags")


class Post(db.Model):
    __tablename__ = "post"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    content = db.Column(db.Text, default="")            # Markdown 源文
    content_html = db.Column(db.Text, default="")       # HTML 源文（render_mode=html 时使用）
    render_mode = db.Column(db.String(16), default="markdown")  # markdown / html / pdf
    pdf_url = db.Column(db.String(255), default="")     # render_mode=pdf 时指向 /uploads/doc/*.pdf
    summary = db.Column(db.String(500), default="")     # 自定义摘要，留空自动截取
    cover = db.Column(db.String(255), default="")       # 封面图 URL
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)

    status = db.Column(db.String(16), default="draft")  # draft / published / scheduled
    is_top = db.Column(db.Boolean, default=False)
    allow_comment = db.Column(db.Boolean, default=True)  # 单篇是否允许评论
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    published_at = db.Column(db.DateTime, default=datetime.now)
    deleted_at = db.Column(db.DateTime, nullable=True)  # 回收站时间戳，NULL=正常，非 NULL=已删除

    category = db.relationship("Category", back_populates="posts")
    tags = db.relationship("Tag", secondary=post_tags, back_populates="posts")
    comments = db.relationship(
        "Comment", back_populates="post", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def get_source(self):
        """按渲染模式返回正文源文（用于统计/搜索/摘要）。"""
        if self.render_mode == "html":
            return self.content_html or ""
        return self.content or ""

    def get_summary(self):
        if self.summary and self.summary.strip():
            return self.summary
        import re

        if self.render_mode == "html":
            text = re.sub(r"<[^>]+>", " ", self.content_html or "")
        else:
            text = re.sub(r"\s+", " ", self.content or "")
            text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # 去掉图片
        return re.sub(r"\s+", " ", text)[:120]

    @property
    def comment_count(self):
        return self.comments.filter(Comment.is_approved == True).count()  # noqa: E712


class Page(db.Model):
    __tablename__ = "page"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(128), unique=True, nullable=False)
    content = db.Column(db.Text, default="")            # Markdown 源文
    content_html = db.Column(db.Text, default="")       # HTML 源文
    render_mode = db.Column(db.String(16), default="markdown")  # markdown / html
    is_show = db.Column(db.Boolean, default=True)      # 是否显示在导航
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class File(db.Model):
    """文件库：编辑器与文章可引用的全部上传文件。"""
    __tablename__ = "file"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)    # 原始文件名
    stored_name = db.Column(db.String(64), nullable=False)  # 存储文件名 uuid.ext
    kind = db.Column(db.String(16), nullable=False)     # image/doc/video/audio/archive/other
    mime = db.Column(db.String(128), default="")
    size = db.Column(db.Integer, default=0)
    ext = db.Column(db.String(16), default="")
    url = db.Column(db.String(512), default="")
    created_at = db.Column(db.DateTime, default=datetime.now)

    @property
    def size_label(self):
        s = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024:
                return f"{s:.0f} {unit}" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} TB"


class Comment(db.Model):
    __tablename__ = "comment"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=True)  # 空=留言板
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # 登录读者（游客为空）
    nickname = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(128), default="")      # 仅管理员可见
    content = db.Column(db.Text, nullable=False)
    ip = db.Column(db.String(64), default="")
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    post = db.relationship("Post", back_populates="comments")
    user = db.relationship("User")


class Log(db.Model):
    """操作日志：后台/前台关键操作留痕，超出保留天数自动清理。"""
    __tablename__ = "log"
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(32), nullable=False, index=True)  # login/post_edit/file_del ...
    target = db.Column(db.String(255), default="")   # 操作对象描述，如“文章: xxx”
    detail = db.Column(db.String(255), default="")
    username = db.Column(db.String(64), default="")  # 操作人
    ip = db.Column(db.String(64), default="")
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)


class Friend(db.Model):
    __tablename__ = "friend"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), default="")
    avatar = db.Column(db.String(255), default="")
    is_show = db.Column(db.Boolean, default=True)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)


class SSLCertificate(db.Model):
    """SSL 证书历史与当前状态（后台 SSL 上传功能的元数据记录）。

    实际证书文件落在服务器 /etc/nginx/ssl/<domain>/ 下，由 wrapper 脚本管理。
    本表只跟踪元数据：签发者、SAN、有效期、操作人等，供状态页与历史页展示。
    """
    __tablename__ = "ssl_certificate"
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), nullable=False, index=True)
    cert_path = db.Column(db.String(512), nullable=False)
    key_path = db.Column(db.String(512), nullable=False)
    issuer = db.Column(db.String(255), default="")
    subject = db.Column(db.String(255), default="")
    sans = db.Column(db.Text, default="")          # JSON 列表字符串，覆盖的所有域名
    not_before = db.Column(db.DateTime, nullable=True)
    not_after = db.Column(db.DateTime, nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True)  # 当前是否被 nginx 加载
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = db.Column(db.String(64), default="")

    @property
    def sans_list(self):
        try:
            import json
            return json.loads(self.sans or "[]")
        except Exception:
            return []

    @property
    def days_to_expire(self):
        if not self.not_after:
            return None
        from datetime import datetime
        delta = self.not_after - datetime.utcnow()
        return int(delta.total_seconds() // 86400)

    @property
    def status_label(self):
        """证书状态：未生效 / 正常 / 即将过期（30 天内）/ 已过期。"""
        if self.days_to_expire is None:
            return "未知"
        if self.days_to_expire < 0:
            return f"已过期 {-self.days_to_expire} 天"
        if self.days_to_expire < 30:
            return f"即将过期（{self.days_to_expire} 天）"
        return "正常"

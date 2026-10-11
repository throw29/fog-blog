import os
from datetime import datetime

import click
from flask import Flask, current_app, render_template, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from models import Setting, User, db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # nginx 终结 TLS 后反代到 127.0.0.1:8000 —— 让 Flask 感知 https 协议
    # 与真实客户端 IP（生产仅本机监听，不会被伪造头欺骗）
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["BACKUP_FOLDER"], exist_ok=True)

    db.init_app(app)

    from routes import register_blueprints

    register_blueprints(app)

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        """公开访问上传的文件（文章引用的图片/PDF/视频等）。"""
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    # 站点设置缓存失效：后台修改后调用 invalidate_settings()
    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from utils import current_user, generate_csrf_token, get_settings

        return {
            "SITE": get_settings(),
            "csrf_token": generate_csrf_token,
            "now": datetime.now,
            "datetime": datetime,
            "auth_user": current_user(),
            "is_logged_in": current_user() is not None,
        }

    @app.template_filter("css_url")
    def css_url(u):
        """把站点设置的图片 URL 安全转成 CSS url(裸token) 形式。

        URL 中除 URL 骨架字符外的特殊字符全部 percent 编码（引号/空格/括号等），
        因此输出不引号的 url(...) 也安全；同时避免模板自动转义把引号变实体。"""
        from urllib.parse import quote

        s = (u or "").strip()
        if not s:
            return "none"
        return "url(" + quote(s, safe="/:?&=._~%#+@-") + ")"

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """初始化数据库并写入默认设置"""
        with app.app_context():
            db.create_all()
            for key, value in Config.DEFAULT_SETTINGS.items():
                Setting.set(key, value)
            db.session.commit()
            click.echo("数据库初始化完成：blog.db")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.argument("password")
    @click.option("--nickname", default="管理员", help="显示昵称")
    def create_user(username, password, nickname):
        """创建管理员账号: flask --app app create-user admin <strong-password>"""
        with app.app_context():
            if User.query.filter_by(username=username).first():
                click.echo("用户已存在")
                return
            user = User(username=username, nickname=nickname)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo(f"用户 {username} 创建成功")

    @app.cli.command("migrate")
    def migrate():
        """升级数据库：建新表 + 给已有表补充新增字段。"""
        with app.app_context():
            db.create_all()
            # 老库中 post / page 没有 render_mode、content_html，手动补列
            import sqlite3

            db_path = Config.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            for table, cols in {
                "post": [
                    ("render_mode", "VARCHAR(16) DEFAULT 'markdown'"),
                    ("content_html", "TEXT"),
                    ("allow_comment", "BOOLEAN DEFAULT 1"),
                    ("pdf_url", "VARCHAR(255) DEFAULT ''"),
                    ("deleted_at", "DATETIME"),
                ],
                "page": [
                    ("render_mode", "VARCHAR(16) DEFAULT 'markdown'"),
                    ("content_html", "TEXT"),
                ],
                "user": [
                    ("role", "VARCHAR(16) DEFAULT 'admin'"),
                    ("email", "VARCHAR(128) DEFAULT ''"),
                    ("bio", "VARCHAR(255) DEFAULT ''"),
                    ("avatar", "VARCHAR(255) DEFAULT ''"),
                    ("is_active", "BOOLEAN DEFAULT 1"),
                    ("last_login_at", "DATETIME"),
                ],
                "comment": [
                    ("user_id", "INTEGER"),
                ],
            }.items():
                existing = {
                    r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for col, ddl in cols:
                    if col not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                        click.echo(f"  + {table}.{col} 已补充")
            conn.commit()
            conn.close()
            click.echo("数据库升级完成")


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

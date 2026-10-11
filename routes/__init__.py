from datetime import datetime

from flask import Flask

from models import Post, db


def register_blueprints(app: Flask):
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.member import member_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # 上传文件统一由 app.py 的 /uploads/<path:filename> 公开访问

    # 全局：CSRF 保护 + 定时文章自动发布 + 惰性维护（日志自动清理）
    from utils import csrf_protect, maybe_maintenance

    @app.before_request
    def global_hooks():
        csrf_protect()
        _auto_publish()
        maybe_maintenance()

    def _auto_publish():
        now = datetime.now()
        rows = (
            Post.query.filter(Post.status == "scheduled", Post.published_at <= now)
            .update({Post.status: "published"}, synchronize_session=False)
        )
        if rows:
            db.session.commit()

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import User, db
from utils import current_user, is_safe_url, write_log

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if user.role != "admin":
                flash("该账号已被停用，请联系管理员", "error")
            else:
                session["user_id"] = user.id
                user.last_login_at = datetime.now()
                db.session.commit()
                write_log("admin_login", f"后台登录：{username}", "", username=user.username)
                flash("登录成功，欢迎回来", "success")
                next_url = request.args.get("next")
                if next_url and is_safe_url(next_url):
                    return redirect(next_url)
                return redirect(url_for("admin.dashboard"))
        else:
            write_log("admin_login_fail", f"后台登录失败：{username}")
            flash("用户名或密码错误", "error")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("已退出登录", "success")
    return redirect(url_for("main.index"))

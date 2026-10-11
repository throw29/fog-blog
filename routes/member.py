"""前台账号入口（兼容旧链接）。

旧版本博客曾支持前台读者注册 / 登录 / 个人中心 / 头像上传。
现已合并为「仅后台账号」：前台访客无需账号即可评论（昵称按 IP 稳定派生）。

本模块保留旧 URL 的可达性：
- /user/register、/user/login → 重定向到 /login（后台登录）
- /user/center、/user/logout、/user/avatar → 重定向到 / (首页)
404 / 410 的选择：考虑到用户书签与搜索引擎可能仍指向这些路径，这里用 302 重定向到最近的等效入口，避免 404 体验割裂。
"""
from flask import Blueprint, redirect, session, url_for

member_bp = Blueprint("member_compat", __name__, url_prefix="/user")


@member_bp.route("/register")
def register_compat():
    """旧读者注册入口 → 后台登录。"""
    return redirect(url_for("auth.login"), code=302)


@member_bp.route("/login")
def login_compat():
    """旧读者登录入口 → 后台登录。"""
    return redirect(url_for("auth.login"), code=302)


@member_bp.route("/center")
def center_compat():
    """旧个人中心 → 首页（功能已合并到后台账号设置）。"""
    return redirect(url_for("main.index"), code=302)


@member_bp.route("/logout")
def logout_compat():
    """旧读者登出：清除 session['uid']（脏兜底），跳到首页。"""
    session.pop("uid", None)
    return redirect(url_for("main.index"), code=302)


@member_bp.route("/avatar", methods=["POST"])
def avatar_compat():
    """旧读者头像上传 → 不再支持。"""
    return {"ok": False, "msg": "读者账号已下线，请联系管理员"}, 410

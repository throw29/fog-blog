import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("BLOG_SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "blog.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 上传目录（存储于 uploads/<kind>/ 下，按类型分子目录）
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

    # 文件类型白名单 → 存储子目录
    FILE_KINDS = {
        "image": {"png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "svg", "avif"},
        "doc": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "epub"},
        "video": {"mp4", "webm", "mov", "avi", "mkv", "flv", "m4v", "ogv"},
        "audio": {"mp3", "wav", "ogg", "m4a", "aac", "flac"},
        "archive": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"},
    }
    EXT_KIND_MAP = {
        ext: kind
        for kind, exts in FILE_KINDS.items()
        for ext in exts
    }
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB（视频/大文档）

    # 备份目录
    BACKUP_FOLDER = os.path.join(BASE_DIR, "backup")

    # 分页
    POSTS_PER_PAGE = 8
    COMMENTS_PER_PAGE = 50

    # 站点默认设置（写入数据库，可在后台修改）
    DEFAULT_SETTINGS = {
        "site_name": "雾里博客",
        "site_subtitle": "记录与分享，如雾般轻盈",
        "site_description": "一个基于 Flask 的轻量毛玻璃风格博客",
        "site_keywords": "博客,技术,生活,随笔",
        "footer_text": "Powered by Flask · Glassmorphism Theme",
        "icp": "",
        "comment_need_audit": "1",
        "comment_allow": "1",
        # ---- 博主信息（前台侧栏卡片）----
        "blogger_name": "",
        "blogger_avatar": "",
        "blogger_bio": "",
        # ---- 每日鸡汤（多行，每行一句；留空使用内置默认句库）----
        "motto_enable": "1",
        "motto_text": "",
        # ---- 深色模式 ----
        "theme_default": "light",     # light / dark（默认外观）
        "theme_auto": "off",          # off / schedule(按时间段) / system(跟随系统)
        "theme_dark_start": "19",     # 按时间段自动切深色的开始小时
        "theme_dark_end": "07",       # 结束小时（跨天）
        "theme_fix_content": "1",     # 深色模式修复正文中硬编码的深色文字
        # ---- 配色方案（毛玻璃主色调）----
        # amber=焦糖琥珀(默认) / sea=海盐蓝 / mint=抹茶青 / grape=葡萄紫 / rose=蔷薇粉
        "color_palette": "amber",
        # ---- 自定义背景图（前台毛玻璃底图；留空=默认渐变底+光斑）----
        "site_bg_image": "",      # 图片 URL：/uploads/image/xxx.jpg 或 https://…
        "site_bg_opacity": "35",  # 图片不透明度 5-100（越小越淡，越大毛玻璃透出的图越清晰）
        # ---- 天气（免费接口，IP 定位，失败自动隐藏）----
        "weather_default_city": "",
        # ---- 日志自动清理（天）----
        "log_keep_days": "90",
    }

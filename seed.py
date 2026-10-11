"""插入演示数据（分类/标签/文章/页面/友链/评论），仅供本地体验。
用法: python seed.py
"""
import os
import secrets
import sys
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import app  # noqa: E402
from models import Category, Comment, Friend, Page, Post, Tag, User, db  # noqa: E402

SAMPLE_POST = """欢迎使用 **雾里博客** —— 一个基于 Flask 的半透明毛玻璃风格轻量博客。

## 功能亮点

- Markdown 写作，右侧实时预览
- 分类 / 标签 / 归档，内容组织清晰
- 自建评论系统，支持审核
- RSS 订阅与 SEO 优化
- 移动端完美适配

## 快速上手

1. 在后台「文章管理」中新建文章
2. 支持 `代码高亮`、表格、引用等语法

```python
def hello(name):
    print(f"Hello, {name}!")
```

> 提示：发布后在前台即可看到效果，访问 `/admin` 进入后台管理。

## 开始创作吧

在「站点设置」中修改站点名称，让它成为属于你的博客。
"""


def run():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            u = User(username="admin", nickname="站长")
            password = os.environ.get("BLOG_ADMIN_PASSWORD") or secrets.token_urlsafe(24)
            u.set_password(password)
            db.session.add(u)
            print(f"已创建管理员 admin，初始密码：{password}（请妥善保存并及时修改）")

        cat_tech = Category(name="技术", slug="tech", description="技术分享与折腾记录")
        cat_life = Category(name="生活", slug="life", description="生活随笔")
        db.session.add_all([cat_tech, cat_life])
        db.session.flush()

        t_flask = Tag(name="Flask", slug="flask")
        t_ui = Tag(name="UI设计", slug="ui-design")
        db.session.add_all([t_flask, t_ui])
        db.session.flush()

        if Post.query.count() == 0:
            now = datetime.now()
            p1 = Post(
                title="欢迎使用雾里博客：毛玻璃风格的轻量博客",
                slug="welcome-to-fog-blog",
                content=SAMPLE_POST,
                category_id=cat_tech.id,
                status="published",
                is_top=True,
                views=128,
                likes=16,
                published_at=now - timedelta(days=2),
            )
            p1.tags = [t_flask, t_ui]

            p2 = Post(
                title="部署到腾讯云 Ubuntu 服务器的完整指南",
                slug="deploy-to-tencent-cloud-ubuntu",
                content="""这篇指南介绍如何在腾讯云 Ubuntu 服务器上部署本博客，包括：

- Nginx 反向代理配置
- systemd 守护进程
- HTTPS 证书申请

完整步骤见项目根目录的 `README.md`。
""",
                category_id=cat_tech.id,
                status="published",
                views=66,
                likes=8,
                published_at=now - timedelta(days=1),
            )
            p2.tags = [t_flask]

            p3 = Post(
                title="周末随笔：关于专注与记录",
                slug="weekend-notes",
                content="""记录本身就是一种沉淀。

把想法写下来，过段时间再回看，往往会发现当时的思路有多稚嫩，而这正是成长。

祝大家都能找到属于自己的表达方式。
""",
                category_id=cat_life.id,
                status="published",
                views=42,
                likes=5,
                published_at=now - timedelta(hours=6),
            )
            db.session.add_all([p1, p2, p3])
            db.session.flush()

            db.session.add_all([
                Comment(post_id=p1.id, nickname="路人甲", content="沙发！博客很漂亮，毛玻璃效果绝了。", is_approved=True, created_at=now - timedelta(hours=20)),
                Comment(post_id=p1.id, nickname="老王", content="部署文档写得很清楚，已经跑起来了，感谢！", is_approved=True, created_at=now - timedelta(hours=10)),
                Comment(post_id=p2.id, nickname="待审核用户", content="这条评论需要管理员审核后才会显示哦～", is_approved=False, created_at=now - timedelta(hours=2)),
            ])

        if Page.query.count() == 0:
            db.session.add_all([
                Page(title="关于我", slug="about", content="""### 关于本站

这是一个基于 Flask 的轻量博客，使用半透明毛玻璃设计风格。

- 追求简洁、专注的写作体验
- 所有数据自主可控
- 支持移动端阅读

欢迎交流：**交换友链、技术讨论都可以**。
""", is_show=True, order=1),
            ])

        if Friend.query.count() == 0:
            db.session.add_all([
                Friend(name="Halo 官网", url="https://www.halo.run", description="强大易用的开源建站工具", is_show=True, order=1),
                Friend(name="Flask 官方", url="https://flask.palletsprojects.com", description="Python 微框架", is_show=True, order=2),
            ])

        db.session.commit()
        print("演示数据插入完成 ✓")
        print("前台: http://127.0.0.1:5000")
        print("后台: http://127.0.0.1:5000/admin （新建账号密码见上方；已有账号不会重置）")


if __name__ == "__main__":
    run()

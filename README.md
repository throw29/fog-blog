#  Fog Blog

基于 Flask + SQLite 的轻量博客，提供毛玻璃风格前台和管理后台。适合希望自行部署、管理文章与评论的个人博客作者。

## 主要功能

- Markdown / HTML 编辑、预览、浏览器本地草稿恢复、置顶和定时发布。
- 分类、标签、归档、独立页面、友情链接、搜索、RSS、sitemap 和 robots.txt。
- 评论审核、文章级评论开关、点赞、阅读统计；游客可评论，不开放前台注册。
- 后台文章批量管理、回收站、文件库、账号管理、操作日志及数据库/JSON 导出。
- 五套配色、浅色/深色模式、自定义背景图及首页开屏动画。
- PDF 原版式在线阅读，或提取文字生成 Markdown 草稿。
- 博主信息、每日鸡汤、倒计时、天气侧栏；天气功能依赖外部网络接口。
- Ubuntu 的 Gunicorn、systemd、Nginx 部署模板，以及后台 SSL 证书解析/校验和上传流程。

前端依赖已放在 `static/vendor/`，不需要从 CDN 加载。运行时数据与上传文件不随源码发布。

## 截图

附件提供的演示截图，供了解界面；不是本次测试生成的结果。截图中的背景插画未包含为应用默认资源。

![后台仪表板](screenshots/admin-dashboard.png)

含外部背景插画的其他截图保留在本地，不纳入公开提交。

## 安装与本地运行

需要 Python 3.9+。下载本仓库源码并进入项目根目录。

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell 改用：.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed.py
python app.py
```

打开前台 `http://127.0.0.1:5000/`，通过 `/login` 登录，后台为 `/admin/`。

`seed.py` 为本地体验创建演示文章与管理员 `admin`，初始密码随机生成并在首次创建时显示。已有用户不会被重置。也可通过 `BLOG_ADMIN_PASSWORD` 环境变量指定初始密码。不要把生产密码提交到仓库。

不需要演示内容时：

```bash
flask --app app init-db
flask --app app create-user admin <替换为你的强密码>
```

程序读取 `BLOG_SECRET_KEY`。未设置时使用进程内随机密钥，仅便于本地体验；重启会使既有会话失效。生产部署必须为所有 worker 设置同一个持久随机密钥，见 [部署说明](deploy/README.md)。

## 使用示例

1. 登录后台，在「文章管理」中新建文章。
2. 输入标题和正文，例如：

   ```markdown
   # 我的第一篇文章
   这是正文，支持 **加粗** 和代码块。
   ```

3. 选择分类、标签与发布状态，保存后在前台查看文章。
4. 游客提交评论后，是否立即展示取决于后台的审核设置。

PDF 转文章入口在后台；文件库上传后可在编辑器引用文件。站点名称、主题及背景图在「站点设置」调整。

## 项目结构

```text
app.py / config.py / models.py   应用入口、配置和数据模型
routes/                         前台、登录、管理和 API 路由
utils/                          通用工具与证书管理
templates/                      Jinja2 前台和后台模板
static/                         样式、脚本、本地第三方库及其许可证
deploy/                         Ubuntu 部署模板和脚本
screenshots/                    提供的演示截图
seed.py                         演示数据初始化
smoke.py / e2e_features.py       HTTP 冒烟和 Flask 客户端回归测试
```

## 测试与已知边界

```bash
python e2e_features.py
```

回归测试使用临时 SQLite、上传目录和备份目录；SSL 为 dry-run，只测试解析/校验，不修改 Nginx。HTTP 冒烟测试会登录并写入测试内容，仅对本地测试实例运行：

```bash
# 设置 SMOKE_PASSWORD 为测试实例的管理员密码；可选 SMOKE_USERNAME / SMOKE_BASE
python smoke.py
```

本次发布准备在 Windows、Python 3.13 下通过现有回归及本地 HTTP 冒烟测试。Ubuntu 安装、真实 Nginx reload 和真实证书生效尚未实机验证；Gunicorn 用于 Linux 部署，Windows 本地体验使用 Flask。测试通过不代表所有浏览器、性能和安全场景均已验证。

附件中的 PDF.js 3.11.174 仍为旧版，本项目按 [Mozilla 官方安全公告](https://github.com/mozilla/pdf.js/security/advisories/GHSA-wgrm-67xf-hhpq)禁用 `isEvalSupported`，缓解 CVE-2024-4367；后续仍需安排依赖升级。

定时发布由页面请求触发，不是独立定时任务。天气依赖第三方服务，可能不可用。截图中的外部背景插画版权不由项目 MIT 许可证授予。对外部署前应审查上传文件、HTML 内容和反向代理配置，避免把开发服务直接暴露到公网。

## 许可证

项目按 [MIT License](LICENSE) 发布，保留原作者 `yimeipiaopiao` 的版权声明。第三方库遵循各自许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

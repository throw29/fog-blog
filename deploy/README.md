# Ubuntu 部署说明

部署模板面向 Ubuntu：Gunicorn 监听 `127.0.0.1:8000`，Nginx 对外服务，systemd 管理进程。当前已进行脚本语法和应用测试，尚未在 Ubuntu 实机执行安装流程或验证真实 SSL 生效。

## 安装

下载源码到服务器，进入根目录，审查脚本后运行：

```bash
sudo bash deploy/install.sh
```

脚本会安装系统依赖、复制代码到 `/var/www/blog`、创建 Python 虚拟环境、生成 `/etc/blog/blog.env`、注册 systemd/Nginx 配置和 SSL sudo wrapper。它会修改服务器系统配置，复制到目标路径时使用 rsync；执行前备份已有部署。不要在 Windows 执行。

生产密钥变量必须是 `BLOG_SECRET_KEY`。脚本仅在环境文件不存在时生成随机值；已有文件需自行核对，不能保留示例占位值。环境文件权限为 600，所有 worker 使用同一密钥。

安装后：

```bash
# 修改站点域名
sudo nano /etc/nginx/sites-available/blog.conf
sudo ln -sf /etc/nginx/sites-available/blog.conf /etc/nginx/sites-enabled/blog.conf
sudo nginx -t
sudo systemctl reload nginx

# 初始化默认设置并创建管理员（替换密码占位符）
cd /var/www/blog
sudo -u www-data venv/bin/flask --app app init-db
sudo -u www-data venv/bin/flask --app app create-user admin <你的强密码>
sudo systemctl start blog
sudo systemctl status blog
```

不要使用 `seed.py` 向生产站点插入演示内容。将数据库、上传文件、备份、环境文件与 TLS 私钥留在服务器，不提交 Git。

## HTTPS 与维护

后台支持校验证书、私钥匹配、域名及有效期；真实应用依赖 `deploy/scripts/blog-ssl-apply.sh` 安装的特权 wrapper。审查 sudoers、Nginx 配置及目录权限后再启用。现有失败处理不保证所有配置与软链完整回滚；首次启用应备份并安排人工恢复方案。也可自行使用 certbot 配置 HTTPS。

```bash
sudo systemctl restart blog
sudo journalctl -u blog -f
bash deploy/logs.sh
```

`rollback.sh` 仅适用于有可用 Git Tag 的部署，执行前查看其行为。`nginx-subpath.conf` 是子路径部署参考模板，需另外调整 Flask 路由挂载，不能直接当作已支持的一键部署方式。

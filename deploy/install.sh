#!/usr/bin/env bash
# 一键部署脚本：Ubuntu 20.04+ / 22.04+ （CentOS 7 不支持，参见 README 注释）
# 用法：sudo bash deploy/install.sh

set -euo pipefail

# ---------- 颜色 + 日志 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()   { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[x]${NC} $*" >&2; }
die()   { err "$@"; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root 跑：sudo bash deploy/install.sh"

# ---------- 检查系统 ----------
. /etc/os-release
[[ "$ID" == "ubuntu" ]] || die "当前只支持 Ubuntu（你的系统是 $ID）。本项目没有提供 CentOS/Docker 部署流程。"
log "检测到 $PRETTY_NAME"

APP_DIR=/var/www/blog
SERVICE_NAME=blog
ENV_DIR=/etc/blog
ENV_FILE=$ENV_DIR/blog.env

# ---------- 安装系统依赖 ----------
log "apt update + 安装系统包"
apt update -y
apt install -y python3 python3-venv python3-pip nginx rsync sudo

# ---------- 创建部署用户（www-data 已存在，nginx 默认也是它） ----------
id www-data &>/dev/null || useradd -r -s /usr/sbin/nologin www-data
log "部署用户 www-data 就绪"

# ---------- 复制代码到 /var/www/blog（如果当前不在那里） ----------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
if [[ "$PROJECT_DIR" != "$APP_DIR" ]]; then
    log "复制代码到 $APP_DIR"
    mkdir -p "$APP_DIR"
    rsync -a --delete --exclude='.git' --exclude='venv' --exclude='__pycache__' \
              --exclude='blog.db' --exclude='uploads/' --exclude='backup/' --exclude='.venv/' --exclude='shots/' \
              "$PROJECT_DIR/" "$APP_DIR/"
else
    log "已在 $APP_DIR 直接部署"
fi

# ---------- 创建 venv + 装依赖 ----------
log "创建 Python venv"
mkdir -p "$APP_DIR/uploads" "$APP_DIR/backup"
chown -R www-data:www-data "$APP_DIR"
sudo -u www-data python3 -m venv "$APP_DIR/venv"
log "安装依赖（pip install -r requirements.txt）"
sudo -u www-data "$APP_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u www-data "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
log "依赖安装完成"

# ---------- 环境变量 ----------
if [[ ! -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE 不存在，创建模板（请填 BLOG_SECRET_KEY 后重启服务）"
    mkdir -p "$ENV_DIR"
    cp "$APP_DIR/deploy/blog.env.example" "$ENV_FILE"
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    sed -i "s|^BLOG_SECRET_KEY=.*|BLOG_SECRET_KEY=$SECRET|" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log "已生成随机 BLOG_SECRET_KEY 写入 $ENV_FILE（chmod 600）"
else
    log "$ENV_FILE 已存在，跳过生成"
fi

grep -q '^BLOG_SECRET_KEY=.' "$ENV_FILE" || die "环境文件必须设置 BLOG_SECRET_KEY，请迁移旧 SECRET_KEY 配置"
if grep -q '^BLOG_SECRET_KEY=change-me' "$ENV_FILE"; then
    die "生产密钥仍是占位值，请填写随机 BLOG_SECRET_KEY"
fi

# ---------- 设置目录权限 ----------
log "调整目录所有权（uploads / backup 可写，其余只读）"
chown -R www-data:www-data "$APP_DIR"
chmod -R 755 "$APP_DIR"
chmod -R 775 "$APP_DIR/uploads" "$APP_DIR/backup" 2>/dev/null || true
mkdir -p "$APP_DIR/backup"
chown www-data:www-data "$APP_DIR/backup"

# ---------- 注册 systemd 服务 ----------
log "注册 systemd 服务"
cp "$APP_DIR/deploy/blog.service" /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload
systemctl enable $SERVICE_NAME
log "systemd 服务已 enable（启动用: systemctl start $SERVICE_NAME）"

# ---------- 注册 nginx 配置 ----------
log "注册 nginx 配置"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/$SERVICE_NAME.conf
warn "需要编辑 /etc/nginx/sites-available/$SERVICE_NAME.conf 把 server_name 改成你的域名"
warn "改完后执行: ln -sf /etc/nginx/sites-available/$SERVICE_NAME.conf /etc/nginx/sites-enabled/"
warn "然后: nginx -t && systemctl reload nginx"

# ---------- SSL 部署（sudo wrapper + sudoers + nginx 通用参数片段）----------
log "部署 SSL 上传 wrapper（sudo 限定 www-data 无密码执行）"
cp "$APP_DIR/deploy/scripts/blog-ssl-apply.sh" /usr/local/bin/blog-ssl-apply
chmod 750 /usr/local/bin/blog-ssl-apply
chown root:www-data /usr/local/bin/blog-ssl-apply

# sudoers：仅允许 www-data 跑这一个 wrapper，不允许其他 root 命令
SUDOERS_FILE="/etc/sudoers.d/blog-ssl"
cat > "$SUDOERS_FILE" <<'SUDO_EOF'
Cmnd_Alias BLOG_SSL = /usr/local/bin/blog-ssl-apply
www-data ALL=(root) NOPASSWD: BLOG_SSL
SUDO_EOF
chmod 440 "$SUDOERS_FILE"
visudo -c -f "$SUDOERS_FILE" || die "sudoers 配置有语法错误，请检查 $SUDOERS_FILE"
log "sudoers 配置完成：$SUDOERS_FILE"

# nginx SSL 通用参数片段（写证书时由 wrapper include 进 server block）
mkdir -p /etc/blog
cp "$APP_DIR/deploy/nginx-ssl-params.conf" /etc/blog/nginx-ssl-params.conf
chmod 644 /etc/blog/nginx-ssl-params.conf

# 证书目录（www-data 没写权限，但 wrapper 走 root → 正常）
mkdir -p /etc/nginx/ssl
chmod 755 /etc/nginx/ssl
log "SSL 目录 /etc/nginx/ssl 已就绪"

# 初始化数据库时新建 SSLCertificate 表
log "初始化数据库（创建表，含 SSLCertificate）"
sudo -u www-data "$APP_DIR/venv/bin/python" -c "from app import app, db; app.app_context().push(); db.create_all()"
log "数据库表已创建"

# ---------- 提示 ----------
cat <<'EOF'

╔══════════════════════════════════════════════════════════╗
║             部署完成！接下来需要：                          ║
╠══════════════════════════════════════════════════════════╣
║  1. 改 /etc/nginx/sites-available/blog.conf               ║
║     里的 server_name 改成你的域名                          ║
║  2. 启用 nginx 站点：                                     ║
║       ln -sf /etc/nginx/sites-available/blog.conf \        ║
║               /etc/nginx/sites-enabled/                    ║
║       nginx -t && systemctl reload nginx                   ║
║  3. 启动博客：                                            ║
║       systemctl start blog                                ║
║  4. 配 HTTPS（两种方式）：                                  ║
║     A. 后台「SSL 证书」上传 PEM（已部署 wrapper）：         ║
║         在 https://example.com/admin/ssl 上传即可          ║
║     B. 手动 certbot 自动：                                 ║
║         certbot --nginx -d example.com                   ║
║  5. （可选）插入演示数据：                                 ║
║       sudo -u www-data venv/bin/python seed.py            ║
║                                                          ║
║  日志：                                                   ║
║    systemctl status blog    # 服务状态                     ║
║    journalctl -u blog -f    # 实时日志                     ║
║    tail -f /var/log/nginx/blog.access.log                 ║
║                                                          ║
║  数据备份：管理后台 → 备份 → 下载数据库（建议每日）        ║
╚══════════════════════════════════════════════════════════╝
EOF

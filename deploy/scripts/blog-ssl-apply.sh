#!/usr/bin/env bash
# blog-ssl-apply.sh — blog SSL 证书 wrapper（sudo 白名单入口）
#
# 部署：sudo bash deploy/install.sh 末尾会把本文件复制到 /usr/local/bin/blog-ssl-apply
#      并写入 sudoers 限定 www-data 无密码执行。
#
# 子命令：
#   write <domain>   从 stdin 读 PEM（cert + key）→ 写盘 → nginx -t → reload
#   remove <domain>  停用 https（移除 https server block + reload 回 http）
#   status <domain>  返回当前证书的状态 JSON
#
# stdin 传入证书与私钥（避免出现在 ps 输出），格式：
#   -----BEGIN CERTIFICATE-----... \n <<<CERT_END>>> \n
#   -----BEGIN PRIVATE KEY-----... \n  <<<KEY_END>>>
#
# 安全边界：
# - 域名仅允许 [a-z0-9-.]+
# - 写盘路径固定 /etc/nginx/ssl/<domain>/
# - 仅调用 nginx / openssl / cp / rm / ln / chmod / chown / mkdir
# - 全部失败会回滚备份

set -euo pipefail

SSL_BASE="/etc/nginx/ssl"
DOMAIN_RE='^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
NGINX_HTTP_LINK="/etc/nginx/sites-enabled/blog.conf"
NGINX_HTTPS_CONF="/etc/nginx/sites-available/blog-ssl.conf"
NGINX_HTTPS_LINK="/etc/nginx/sites-enabled/blog-ssl.conf"
NGINX_SSL_PARAMS="/etc/blog/nginx-ssl-params.conf"
# 与 deploy/nginx.conf / blog.service 保持一致；可用环境变量覆盖
BLOG_UPSTREAM="${BLOG_UPSTREAM:-http://127.0.0.1:8000}"
APP_DIR="${BLOG_APP_DIR:-/var/www/blog}"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[blog-ssl] $*" >&2; }

# ---------- 参数校验 ----------
[[ $# -ge 1 ]] || die "用法：blog-ssl-apply {write|remove|status} <domain>"
ACTION="$1"; shift
DOMAIN="${1:-}"

[[ -n "$DOMAIN" ]] || die "缺少域名参数"
[[ "$DOMAIN" =~ $DOMAIN_RE ]] || die "域名格式不合法：$DOMAIN"
[[ "$DOMAIN" != *..* && "$DOMAIN" != /* ]] || die "拒绝包含 .. 或绝对路径的域名"

CERT_DIR="$SSL_BASE/$DOMAIN"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"
BACKUP_DIR="$CERT_DIR/.backup"

# ---------- write ----------
write_action() {
    # 从 stdin 读 PEM
    INPUT="$(cat)"
    CERT_BODY="$(printf '%s' "$INPUT" | sed -n '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/p')"
    KEY_BODY="$(printf '%s' "$INPUT" | sed -n '/-----BEGIN .*PRIVATE KEY-----/,/-----END .*PRIVATE KEY-----/p')"
    [[ -n "$CERT_BODY" ]] || die "stdin 中未找到 CERTIFICATE 块"
    [[ -n "$KEY_BODY" ]]   || die "stdin 中未找到 PRIVATE KEY 块"

    mkdir -p "$CERT_DIR" "$BACKUP_DIR"
    chmod 755 "$SSL_BASE" 2>/dev/null || true

    # 备份现有证书
    if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
        cp -p "$CERT_FILE" "$BACKUP_DIR/fullchain.pem"
        cp -p "$KEY_FILE"  "$BACKUP_DIR/privkey.pem"
        chmod 600 "$BACKUP_DIR"/* 2>/dev/null || true
        log "已备份当前证书到 $BACKUP_DIR"
    fi

    # 写入新证书
    printf '%s\n' "$CERT_BODY" > "$CERT_FILE"
    printf '%s\n' "$KEY_BODY"   > "$KEY_FILE"
    chmod 644 "$CERT_FILE"
    chmod 640 "$KEY_FILE"
    chown root:www-data "$KEY_FILE" 2>/dev/null || true

    # 生成 / 更新 nginx https 配置（覆盖式）
    # server_name 只写用户提交的主域名（不自动加 www —— 证书是否覆盖 www
    # 由用户证书决定，避免凭空引入一个不受证书保护的域名）
    cat > "$NGINX_HTTPS_CONF" <<NGINX_EOF
# blog HTTPS 配置 —— 由 blog-ssl-apply 自动管理
# （手改后下次写证书会被覆盖，重新覆盖后请 nginx -t 验证）
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate     $CERT_FILE;
    ssl_certificate_key $KEY_FILE;
    include $NGINX_SSL_PARAMS;

    location = /healthz {
        access_log off;
        return 200 "ok\n";
    }

    location /static/ {
        alias $APP_DIR/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location /uploads/ {
        alias $APP_DIR/uploads/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass $BLOG_UPSTREAM;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection         "";
        proxy_connect_timeout 60s;
        proxy_send_timeout    60s;
        proxy_read_timeout    60s;
        client_max_body_size 50m;
    }
}
NGINX_EOF

    # 启用 https 软链，停用原 http 软链避免 listen 80 冲突
    ln -sf "$NGINX_HTTPS_CONF" "$NGINX_HTTPS_LINK"
    if [[ -e "$NGINX_HTTP_LINK" || -L "$NGINX_HTTP_LINK" ]]; then
        rm -f "$NGINX_HTTP_LINK"
        log "已停用 http 配置软链（listen 80 转 https）"
    fi

    # nginx -t 测试
    if ! nginx -t 2>&1; then
        log "nginx -t 失败，回滚备份证书"
        if [[ -f "$BACKUP_DIR/fullchain.pem" ]]; then
            cp "$BACKUP_DIR/fullchain.pem" "$CERT_FILE"
            cp "$BACKUP_DIR/privkey.pem"  "$KEY_FILE"
        fi
        exit 1
    fi

    # reload
    nginx -s reload
    log "证书已应用：$DOMAIN → $CERT_FILE"
}

# ---------- remove ----------
remove_action() {
    [[ -f "$CERT_FILE" ]] || die "未找到证书文件：$CERT_FILE"
    # 移除 https 配置软链
    rm -f "$NGINX_HTTPS_LINK"
    # 重新启用原 http 配置软链（deploy/install.sh 部署的）
    if [[ -f /etc/nginx/sites-available/blog.conf ]]; then
        ln -sf /etc/nginx/sites-available/blog.conf "$NGINX_HTTP_LINK"
    fi
    if nginx -t && nginx -s reload; then
        log "HTTPS 已停用，证书文件保留在 $CERT_DIR（无 nginx 配置引用，不会被加载）"
    else
        die "nginx reload 失败，请手动检查 /var/log/nginx/error.log"
    fi
}

# ---------- status ----------
status_action() {
    if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
        EXPIRES=$(openssl x509 -enddate -noout -in "$CERT_FILE" 2>/dev/null | cut -d= -f2 || echo "unknown")
        ISSUER=$(openssl x509 -issuer -noout -in "$CERT_FILE" 2>/dev/null | sed 's/issuer=//' || true)
        SUBJECT=$(openssl x509 -subject -noout -in "$CERT_FILE" 2>/dev/null | sed 's/subject=//' || true)
        SANS=$(openssl x509 -text -noout -in "$CERT_FILE" 2>/dev/null | \
            awk '/Subject Alternative Name/{getline; gsub(/^ +/, ""); print; exit}' | \
            tr ',' '\n' | grep DNS | sed 's/DNS://g' | sed 's/^ *//' | paste -sd ',' -)
        printf '{"active":true,"path":"%s","expires":"%s","issuer":"%s","subject":"%s","sans":"%s"}\n' \
            "$CERT_FILE" "$EXPIRES" "$ISSUER" "$SUBJECT" "$SANS"
    else
        printf '{"active":false}\n'
    fi
}

# ---------- 入口分发 ----------
case "$ACTION" in
    write)   write_action ;;
    remove)  remove_action ;;
    status)  status_action ;;
    *)       die "未知子命令：$ACTION（仅支持 write/remove/status）" ;;
esac

#!/usr/bin/env bash
# 一键回滚到上一个 git tag
# 用法：sudo bash deploy/rollback.sh
#
# 配合 deploy/install.sh 使用前先：
#   cd /var/www/blog
#   git tag -a v1.0.0 -m "初次部署"  # 每次部署成功后打 tag

set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

APP_DIR=/var/www/blog
SERVICE_NAME=blog

cd "$APP_DIR" || die "未找到 $APP_DIR"

CURRENT=$(git describe --tags --abbrev=0 2>/dev/null || echo "无 tag")
echo "当前版本: $CURRENT"

# 找上一个 tag
PREVIOUS=$(git tag --sort=-creatordate | sed -n '2p')
if [[ -z "$PREVIOUS" ]]; then
    die "没有可回滚的 tag（只有 $CURRENT 或无 tag）"
fi

echo "将回滚到: $PREVIOUS"
read -p "确认？[y/N] " -n 1 -r
echo
[[ $REPLY =~ ^[Yy]$ ]] || { echo "已取消"; exit 0; }

log() { echo -e "\033[0;32m[+]\033[0m $*"; }
log "git checkout $PREVIOUS"
git checkout "$PREVIOUS"
log "更新依赖（如有变化）"
sudo -u www-data "$APP_DIR/venv/bin/pip" install -r requirements.txt -q
log "重启服务"
systemctl restart $SERVICE_NAME
sleep 2
systemctl status $SERVICE_NAME --no-pager -l | head -10
log "回滚完成（注意：数据库没回滚，如有 schema 变化需要手动处理）"

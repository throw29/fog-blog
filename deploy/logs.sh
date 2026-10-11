#!/usr/bin/env bash
# 集中查看应用日志（systemd journal + nginx access/error）
# 用法： bash deploy/logs.sh [app|nginx|all]

MODE=${1:-all}

case "$MODE" in
    app|all)
        echo -e "\n\033[1;36m=== blog service journal (最近 50 行) ===\033[0m"
        journalctl -u blog -n 50 --no-pager
        if [[ "$MODE" == "app" ]]; then exit 0; fi
        ;;
esac

case "$MODE" in
    nginx|all)
        echo -e "\n\033[1;36m=== nginx access (最近 20 行) ===\033[0m"
        tail -n 20 /var/log/nginx/blog.access.log 2>/dev/null || echo "无 access 日志（可能还没流量）"
        echo -e "\n\033[1;36m=== nginx error (最近 20 行) ===\033[0m"
        tail -n 20 /var/log/nginx/blog.error.log 2>/dev/null || echo "无 error 日志"
        ;;
esac

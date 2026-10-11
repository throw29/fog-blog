"""SSL 证书管理：解析 / 校验 / 应用 / 删除。

安全模型：所有写盘 + nginx reload 操作通过 subprocess 调用 wrapper 脚本
sudo /usr/local/bin/blog-ssl-apply（参数白名单 + 写盘路径限定 /etc/nginx/ssl/&lt;domain&gt;/）。

部署时需先跑 deploy/install.sh 把 wrapper 装好 + sudoers 配置好。

开发环境（无 wrapper）下：可通过 BLOG_SSL_DRY_RUN=1 环境变量跳过实际写盘，
让 python 层只做证书解析与校验，便于本地回归测试。
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa
from cryptography.x509.oid import NameOID

DRY_RUN = os.environ.get("BLOG_SSL_DRY_RUN") == "1"
SSL_BASE_DIR = "/etc/nginx/ssl"
WRAPPER = "/usr/local/bin/blog-ssl-apply"


# ---------------- 解析 ----------------

def _ensure_pem(text, label):
    """轻量 PEM 头尾校验；详细解析由 cryptography 处理。"""
    if not text or not text.strip():
        raise ValueError(f"「{label}」内容为空")
    s = text.strip()
    if not s.startswith("-----BEGIN "):
        raise ValueError(f"「{label}」格式错误：缺少 BEGIN 标记（必须为 PEM 格式）")
    head = s.split("\n", 1)[0]
    if "PRIVATE KEY" not in head and "CERTIFICATE" not in head:
        raise ValueError(f"「{label}」首行类型应为 CERTIFICATE 或 PRIVATE KEY，当前：{head[:60]}")
    if "-----END" not in s:
        raise ValueError(f"「{label}」缺少 END 标记")
    return s


def _format_name(name):
    parts = []
    for oid, fmt in (
        (NameOID.COMMON_NAME, "CN"),
        (NameOID.ORGANIZATION_NAME, "O"),
        (NameOID.ORGANIZATIONAL_UNIT_NAME, "OU"),
    ):
        try:
            v = name.get_attributes_for_oid(oid)[0].value
            parts.append(f"{fmt}={v}")
        except (IndexError, AttributeError):
            pass
    return " / ".join(parts) or str(name)


def parse_cert_pem(cert_pem):
    """解析证书 PEM，返回 dict(issuer, subject, sans, not_before, not_after, serial)。
    解析失败抛 ValueError 并带可展示错误。
    """
    pem = _ensure_pem(cert_pem, "证书")
    try:
        cert = x509.load_pem_x509_certificate(pem.encode("utf-8"))
    except Exception as e:
        raise ValueError(f"证书解析失败：{e}")

    sans = []
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for name in ext.value:
            if isinstance(name, x509.DNSName):
                sans.append(name.value)
    except x509.ExtensionNotFound:
        pass

    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc
    if not_before.tzinfo:
        not_before = not_before.astimezone(timezone.utc).replace(tzinfo=None)
    if not_after.tzinfo:
        not_after = not_after.astimezone(timezone.utc).replace(tzinfo=None)

    return {
        "issuer": _format_name(cert.issuer),
        "subject": _format_name(cert.subject),
        "sans": sans,
        "not_before": not_before,
        "not_after": not_after,
        "serial": cert.serial_number,
    }


def parse_key_pem(key_pem):
    """解析私钥（PEM），支持 RSA / EC / DSA。当前不支持加密私钥（password=None）。"""
    pem = _ensure_pem(key_pem, "私钥")
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except Exception as e:
        msg = str(e)
        if "encrypted" in msg.lower() or "password" in msg.lower():
            raise ValueError("检测到加密私钥，本系统暂不支持加密私钥导入，请先在本地用 openssl 解密")
        raise ValueError(f"私钥解析失败：{e}")
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey, dsa.DSAPrivateKey)):
        raise ValueError("私钥算法不支持（仅 RSA / EC / DSA）")
    return key


# ---------------- 校验 ----------------

def validate_cert_key_match(cert_pem, key_pem):
    """证书公钥与私钥必须配对（HTTPS 握手才会成功）。"""
    pem = _ensure_pem(cert_pem, "证书")
    cert = x509.load_pem_x509_certificate(pem.encode("utf-8"))
    key = parse_key_pem(key_pem)
    cert_pub = cert.public_key()
    same = False
    try:
        if isinstance(key, rsa.RSAPrivateKey) and isinstance(cert_pub, rsa.RSAPublicKey):
            same = key.public_key().public_numbers() == cert_pub.public_numbers()
        elif isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(cert_pub, ec.EllipticCurvePublicKey):
            same = key.public_key().public_numbers() == cert_pub.public_numbers()
        elif isinstance(key, dsa.DSAPrivateKey) and isinstance(cert_pub, dsa.DSAPublicKey):
            same = key.public_key().public_numbers() == cert_pub.public_numbers()
    except Exception:
        same = False
    if not same:
        return False, "证书公钥与私钥不匹配（这一对必须配对，否则 HTTPS 握手必然失败）"
    return True, None


def validate_domain_in_cert(domain, cert_info):
    """校验 user 填的域名是否在证书覆盖范围内（SAN 优先，CN 兜底）。"""
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return False, "请填写域名"
    sans = [s.lower().rstrip(".") for s in (cert_info.get("sans") or [])]
    subject_cn = (cert_info.get("subject") or "").split(" / ")[0].split("=", 1)[-1].lower().rstrip(".")
    for s in sans:
        if s == domain:
            return True, None
        if s.startswith("*."):
            base = s[2:]
            # 通配符 *.example.com 匹配 blog.example.com，但不应匹配顶层 example.com
            if domain.endswith("." + base) and domain.count(".") >= base.count(".") + 1:
                return True, None
    if subject_cn == domain:
        return True, None
    sample = sans[:5]
    if subject_cn:
        sample.append(subject_cn)
    return False, f"域名 {domain} 不在证书覆盖范围内。证书包括：{', '.join(sample) or '(无)'}（请确认域名是否正确，或换一张覆盖该域名的证书）"


def validate_not_expired(cert_info):
    """证书有效期：未生效 或 已过期 都拒绝。"""
    now = datetime.utcnow()
    if cert_info["not_after"] < now:
        delta = now - cert_info["not_after"]
        return False, f"证书已于 {cert_info['not_after'].strftime('%Y-%m-%d')} 过期（已过 {delta.days} 天）"
    if cert_info["not_before"] > now:
        delta = cert_info["not_before"] - now
        return False, f"证书尚未生效，将在 {delta.days} 天后启用（生效时间：{cert_info['not_before'].strftime('%Y-%m-%d')}）"
    return True, None


# ---------------- Wrapper 进程调用 ----------------

def _run_wrapper(action, *args, stdin_text=None, timeout=30):
    """调用 sudo wrapper，DRY_RUN 时模拟成功。返回 (returncode, stdout, stderr)。"""
    if DRY_RUN:
        return 0, f"[DRY_RUN] {action} {' '.join(args)}", ""
    cmd = ["sudo", "-n", WRAPPER, action] + list(args)
    try:
        r = subprocess.run(
            cmd, input=stdin_text, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"wrapper 超时（{timeout}s）"
    except FileNotFoundError:
        return -1, "", f"wrapper 未找到：{WRAPPER}（请先跑 deploy/install.sh 部署 wrapper 与 sudoers）"


# ---------------- 业务入口 ----------------

def apply_certificate(domain, cert_pem, key_pem):
    """应用证书到 nginx：写盘 + nginx -t + reload，失败抛 RuntimeError。

    流程全部由 wrapper 完成：
    1. 备份 /etc/nginx/ssl/<domain>/*.bak（如有）
    2. 写入新 cert.pem + key.pem
    3. nginx -t 测试
    4. 测试通过 → reload；失败 → 回滚备份
    """
    # 私钥通过 stdin 传入 wrapper，避免命令行出现在 ps 输出里。
    payload = f"{cert_pem.strip()}\n<<<CERT_END>>>\n{key_pem.strip()}\n<<<KEY_END>>>\n"
    rc, out, err = _run_wrapper("write", domain, stdin_text=payload, timeout=45)
    if rc != 0:
        raise RuntimeError(f"应用失败：{(err or out).strip() or '未知错误'}")
    return out.strip()


def remove_certificate(domain):
    """删除证书 + nginx reload（站点 fallback 到 HTTP）。"""
    rc, out, err = _run_wrapper("remove", domain, timeout=30)
    if rc != 0:
        raise RuntimeError(f"删除失败：{(err or out).strip() or '未知错误'}")
    return out.strip()


def get_wrapper_status():
    """返回 wrapper 是否就绪 + dry_run 标记（供 UI 提示）。"""
    return {
        "dry_run": DRY_RUN,
        "wrapper_path": WRAPPER,
        "wrapper_exists": os.path.exists(WRAPPER) if not DRY_RUN else True,
    }


def process_upload(domain, cert_pem, key_pem):
    """证书上传的统一入口：解析 → 全部校验 → 应用 → 返回数据库可入库的 dict。
    任一步失败抛 ValueError / RuntimeError。
    """
    domain = (domain or "").strip().lower().rstrip(".")
    # 域名格式基础校验
    if not re.fullmatch(r"(\*\.)?([a-z0-9-]+\.)+[a-z]{2,}", domain):
        raise ValueError("域名格式不正确（形如 example.com 或 blog.example.com）")

    # 解析
    cert_info = parse_cert_pem(cert_pem)
    key = parse_key_pem(key_pem)  # noqa: F841 — 同时完成格式校验

    # 配对
    ok, msg = validate_cert_key_match(cert_pem, key_pem)
    if not ok:
        raise ValueError(msg)

    # 域名覆盖
    ok, msg = validate_domain_in_cert(domain, cert_info)
    if not ok:
        raise ValueError(msg)

    # 有效期
    ok, msg = validate_not_expired(cert_info)
    if not ok:
        raise ValueError(msg)

    # 实际应用
    apply_certificate(domain, cert_pem, key_pem)

    return {
        "domain": domain,
        "issuer": cert_info["issuer"],
        "subject": cert_info["subject"],
        "sans": cert_info["sans"],
        "not_before": cert_info["not_before"],
        "not_after": cert_info["not_after"],
        "cert_path": f"{SSL_BASE_DIR}/{domain}/fullchain.pem",
        "key_path": f"{SSL_BASE_DIR}/{domain}/privkey.pem",
    }

#!/usr/bin/env bash
# 把 SimulateE (RetroWeb) 挂到 .53 的外网网关上（幂等，可重复运行）：
#   bash ~/simulatee/deploy/gateway-setup.sh
# 1) Cloudflare 建 A 记录（DNS-only，指向当前公网 IP）
# 2) certbot 用 dns-cloudflare 签证书（续期由现有 crontab 的 renew.sh 自动覆盖）
# 3) 生成 HTTP Basic 认证文件（仅首次；密码存 ~/.secrets/retro-basic-auth.txt）
# 4) 在 ~/gateway/nginx.conf 末尾插入/替换带标记的 server 块，nginx -t 通过后 reload
# 不碰 kiora / console 的任何配置；最后跑 mainstage 的 verify.sh 复核。
set -euo pipefail

HOST="${HOST:-retro.kururu.org}"
ZONE_ID="34b0007c31a22cb79a2e45ba0d36be8b"          # kururu.org
UPSTREAM="http://127.0.0.1:3000"
AUTH_USER="${AUTH_USER:-koy}"
CONF="$HOME/gateway/nginx.conf"
NGINX="$HOME/gateway/pkg/root/usr/sbin/nginx"
HTPASSWD="$HOME/gateway/retro.htpasswd"
PWFILE="$HOME/.secrets/retro-basic-auth.txt"
CF_INI="$HOME/.secrets/cloudflare.ini"
CERTBOT="$HOME/certbot/.venv/bin/certbot"
CERT_ARGS=(--config-dir "$HOME/certbot/config" --work-dir "$HOME/certbot/work" --logs-dir "$HOME/certbot/logs")
MARK_BEGIN="    # >>> SimulateE (RetroWeb) block (managed by ~/simulatee/deploy/gateway-setup.sh) >>>"
MARK_END="    # <<< SimulateE (RetroWeb) block <<<"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }

# ---------- 1. DNS ----------
log "DNS: $HOST"
TOKEN=$(grep -E '^dns_cloudflare_api_token' "$CF_INI" | sed -E 's/^[^=]*=\s*//')
PUBIP=$(curl -fsS -m 10 https://api.ipify.org)
existing=$(curl -fsS -m 15 -H "Authorization: Bearer $TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?type=A&name=$HOST")
rec_id=$(printf '%s' "$existing" | python3 -c 'import sys,json; r=json.load(sys.stdin)["result"]; print(r[0]["id"] if r else "")')
rec_ip=$(printf '%s' "$existing" | python3 -c 'import sys,json; r=json.load(sys.stdin)["result"]; print(r[0]["content"] if r else "")')
if [ -z "$rec_id" ]; then
  curl -fsS -m 15 -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
    --data "{\"type\":\"A\",\"name\":\"$HOST\",\"content\":\"$PUBIP\",\"ttl\":1,\"proxied\":false}" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("created" if d["success"] else d["errors"])'
elif [ "$rec_ip" != "$PUBIP" ]; then
  curl -fsS -m 15 -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$rec_id" \
    --data "{\"content\":\"$PUBIP\"}" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("updated" if d["success"] else d["errors"])'
else
  echo "already $HOST -> $PUBIP"
fi
unset TOKEN

# ---------- 2. 证书 ----------
log "证书"
if [ ! -f "$HOME/certbot/config/live/$HOST/fullchain.pem" ]; then
  "$CERTBOT" certonly --non-interactive --agree-tos "${CERT_ARGS[@]}" \
    --dns-cloudflare --dns-cloudflare-credentials "$CF_INI" --dns-cloudflare-propagation-seconds 30 \
    --key-type ecdsa --elliptic-curve secp256r1 \
    --cert-name "$HOST" -d "$HOST"
else
  echo "already have $(openssl x509 -in "$HOME/certbot/config/live/$HOST/fullchain.pem" -noout -enddate)"
fi

# ---------- 3. Basic 认证 ----------
log "Basic 认证"
mkdir -p "$HOME/.secrets"; chmod 700 "$HOME/.secrets"
if [ ! -s "$HTPASSWD" ]; then
  pw=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  printf '%s:%s\n' "$AUTH_USER" "$(openssl passwd -apr1 "$pw")" > "$HTPASSWD"
  chmod 600 "$HTPASSWD"
  printf 'user=%s\npassword=%s\n' "$AUTH_USER" "$pw" > "$PWFILE"; chmod 600 "$PWFILE"
  echo "new credentials written to $PWFILE"
else
  echo "already exists ($HTPASSWD), keeping it; see $PWFILE"
fi

# ---------- 4. nginx server 块 ----------
log "nginx server 块"
block=$(cat <<NGX
$MARK_BEGIN
    # 公网 https://$HOST（路由器 443 -> 本机 8443）。门禁 = HTTP Basic（应用本身无登录）。
    # 上游是 Next.js standalone(:3000)，/api 由 Next 服务端再转到 uvicorn(:8010)。
    # COOP/COEP 头由上游下发并原样透传（SharedArrayBuffer/PSP 需要）。
    server {
        listen 8443 ssl;
        server_name $HOST;

        ssl_certificate     /home/koy/certbot/config/live/$HOST/fullchain.pem;
        ssl_certificate_key /home/koy/certbot/config/live/$HOST/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        auth_basic           "RetroWeb";
        auth_basic_user_file /home/koy/gateway/retro.htpasswd;

        client_max_body_size    2g;      # ROM 上传上限，与 API 的 MAX_ROM_UPLOAD_BYTES 一致
        proxy_request_buffering off;     # 上传直通，不先落盘到 tmp/body
        proxy_buffering         off;     # ROM Range 流式下发，存档状态 ~40MB
        proxy_read_timeout      600s;
        proxy_send_timeout      600s;

        location / {
            proxy_pass $UPSTREAM;
            proxy_http_version 1.1;
            proxy_set_header Host \$host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For \$remote_addr;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \$connection_upgrade;
        }
    }
$MARK_END
NGX
)
cp -a "$CONF" "$CONF.bak-$(date +%Y%m%d-%H%M%S)"
BLOCK="$block" MB="$MARK_BEGIN" ME="$MARK_END" python3 - "$CONF" <<'PY'
import os, sys, re
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
block, mb, me = os.environ["BLOCK"], os.environ["MB"], os.environ["ME"]
if mb in src and me in src:
    pre, rest = src.split(mb, 1)
    _, post = rest.split(me, 1)
    new = pre + block + post
    print("replaced existing block")
else:
    idx = src.rstrip().rfind("}")          # http {} 的收尾大括号
    new = src[:idx] + block + "\n" + src[idx:]
    print("inserted new block before final }")
open(path, "w", encoding="utf-8").write(new)
PY
"$NGINX" -t -p "$HOME/gateway" -c "$CONF"
bash "$HOME/reload_gateway.sh"

# ---------- 5. 验证 ----------
log "验证 $HOST（本机 --resolve）"
R="--resolve $HOST:8443:127.0.0.1"
echo "无凭据 /            -> $(curl -sk $R -o /dev/null -w '%{http_code}' -m 8 https://$HOST:8443/)   (期望 401)"
# shellcheck disable=SC1090
. "$PWFILE"
echo "有凭据 /            -> $(curl -sk $R -u "$user:$password" -o /dev/null -w '%{http_code}' -m 8 https://$HOST:8443/)   (期望 200)"
echo "有凭据 /api/health  -> $(curl -sk $R -u "$user:$password" -m 8 https://$HOST:8443/api/health)"
echo "COOP/COEP:"; curl -sk $R -u "$user:$password" -D - -o /dev/null -m 8 https://$HOST:8443/ | grep -i cross-origin
echo "证书:"; echo | openssl s_client -connect 127.0.0.1:8443 -servername "$HOST" 2>/dev/null | openssl x509 -noout -subject -issuer -enddate
log "mainstage verify.sh（确认 kiora/console 未受影响）"
bash "$HOME/mainstage/deploy/verify.sh" | tail -6 || true

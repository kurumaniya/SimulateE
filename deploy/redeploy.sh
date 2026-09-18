#!/usr/bin/env bash
# SimulateE (RetroWeb) 在 .53 上的部署 / 重部署脚本。幂等，可反复运行：
#   bash ~/simulatee/deploy/redeploy.sh
# 做的事：装 Node（仅首次）→ git pull → Python 依赖 → npm 依赖 → 拉 EmulatorJS
# → next build → 组装 standalone 运行目录 → 安装/重启 systemd --user 服务 → 健康检查。
# 无 sudo；一切都在 ~/ 下，与 kiora 的部署方式一致。
set -euo pipefail

REPO_URL="https://github.com/kurumaniya/SimulateE.git"
APP="$HOME/simulatee"
NODE_VERSION="v22.23.2"
NODE_SHA256="d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307"
API_PORT=8010
WEB_PORT=3000

export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }

# ---------- 1. Node（仅首次） ----------
if [ ! -x "$HOME/.local/node/bin/node" ] || [ "$("$HOME/.local/node/bin/node" --version)" != "$NODE_VERSION" ]; then
  log "安装 Node $NODE_VERSION 到 ~/.local/node"
  mkdir -p "$HOME/.local/src"
  tarball="$HOME/.local/src/node-$NODE_VERSION-linux-x64.tar.xz"
  [ -f "$tarball" ] || curl -fsSL -o "$tarball" "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz"
  echo "$NODE_SHA256  $tarball" | sha256sum -c -
  rm -rf "$HOME/.local/node-$NODE_VERSION-linux-x64"
  tar -xJf "$tarball" -C "$HOME/.local"
  ln -sfn "$HOME/.local/node-$NODE_VERSION-linux-x64" "$HOME/.local/node"
fi
node --version; npm --version

# ---------- 2. 代码 ----------
if [ ! -d "$APP/.git" ]; then
  log "克隆 $REPO_URL 到 $APP"
  git clone "$REPO_URL" "$APP"
else
  log "git pull --ff-only"
  git -C "$APP" pull --ff-only
fi
cd "$APP"
# 部署文件与仓库解耦：redeploy.sh 所在目录就是权威副本
mkdir -p "$APP/deploy"
[ "$(cd "$(dirname "$0")" && pwd)" = "$APP/deploy" ] || cp -a "$(dirname "$0")"/. "$APP/deploy/"

# ---------- 3. .env（仅首次生成，之后不动） ----------
if [ ! -f "$APP/.env" ]; then
  log "生成 .env"
  secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat > "$APP/.env" <<ENV
APP_NAME=RetroWeb
NEXT_PUBLIC_APP_NAME=RetroWeb
DATABASE_URL=sqlite:///./data/retroweb.db
DATA_PATH=./data
SECRET_KEY=$secret
SINGLE_USER_MODE=true
LOG_FORMAT=json
LOG_LEVEL=INFO
CORS_ORIGINS=http://192.168.1.53:$WEB_PORT
# 构建期写入 Next.js rewrites：浏览器只访问 web，/api 由 Next 服务端转发到这里
API_PROXY_TARGET=http://127.0.0.1:$API_PORT
CROSS_ORIGIN_ISOLATION=true
ENV
  chmod 600 "$APP/.env"
fi
mkdir -p data/roms data/saves data/states data/bios data/covers data/screenshots

# ---------- 4. 后端 ----------
log "Python 依赖 (uv, cpython 3.12)"
cd "$APP/apps/api"
[ -x .venv/bin/python ] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --quiet .
cd "$APP"

# ---------- 5. 前端 ----------
log "npm ci"
npm ci --no-audit --no-fund
log "EmulatorJS 运行时与内核（已安装则跳过）"
node scripts/fetch-emulatorjs.mjs
log "next build"
set -a; . "$APP/.env"; set +a
npm run build --workspace apps/web

log "组装 standalone 运行目录 run/web"
rm -rf "$APP/run/web.new"
mkdir -p "$APP/run"
cp -a apps/web/.next/standalone "$APP/run/web.new"
mkdir -p "$APP/run/web.new/apps/web/.next"
cp -a apps/web/.next/static "$APP/run/web.new/apps/web/.next/static"
cp -a apps/web/public "$APP/run/web.new/apps/web/public"
rm -rf "$APP/run/web.old"
[ -d "$APP/run/web" ] && mv "$APP/run/web" "$APP/run/web.old"
mv "$APP/run/web.new" "$APP/run/web"
rm -rf "$APP/run/web.old"

# ---------- 6. systemd --user ----------
log "安装并重启服务"
mkdir -p "$HOME/.config/systemd/user"
cp "$APP/deploy/simulatee-api.service" "$APP/deploy/simulatee-web.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable simulatee-api simulatee-web >/dev/null
systemctl --user restart simulatee-api
systemctl --user restart simulatee-web

# ---------- 7. 健康检查 ----------
log "健康检查"
for i in $(seq 1 20); do
  sleep 1
  curl -fsS -m 3 "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 && break
done
curl -fsS -m 5 "http://127.0.0.1:$API_PORT/api/health"; echo
for i in $(seq 1 20); do
  sleep 1
  curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$WEB_PORT/" 2>/dev/null && break
done
echo "web /           -> $(curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1:$WEB_PORT/)"
echo "web /api/health -> $(curl -s -m 5 http://127.0.0.1:$WEB_PORT/api/health)"
systemctl --user is-active simulatee-api simulatee-web
echo "部署完成: $(git -C "$APP" rev-parse --short HEAD)  →  http://192.168.1.53:$WEB_PORT"

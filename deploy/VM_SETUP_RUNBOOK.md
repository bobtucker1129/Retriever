# VM Setup Runbook: bggol-vesko01 (coexistence deployment)

**Target:** `bggol-vesko01` — the existing Boone LAN server already running old Retriever  
**Public entry:** `retriever.boonegraphics.net` via Cloudflare Access + Cloudflare Tunnel  
**Old Retriever:** stays live and untouched on its current port — new Retriever runs on port 8810

> **Coexistence note:** VM provisioning was skipped. New Retriever runs beside old Retriever on the same
> box. Old Retriever keeps its current port, its process, and the PrintSmith token authority.
> New Retriever binds to `127.0.0.1:8810` only. The Cloudflare Tunnel is new and targets only port 8810.

Complete each section in order. Check each item before moving on.

---

## Section 0 — Coexistence Preflight (run these before doing anything else)

SSH into `bggol-vesko01` and confirm the following before proceeding.

**Check Python version:**
```bash
python3 --version
# Need 3.10 or newer. If only python3 is available, check: python3.10 --version or python3.11 --version
```

**Check that port 8810 is free (new Retriever's port):**
```bash
ss -tlnp | grep 8810
# Should return nothing. If something is already on 8810, resolve the conflict first.
```

**Check what port old Retriever is on (so you know not to touch it):**
```bash
ss -tlnp | grep node
# or: ss -tlnp | grep python
# Note the port and process — do not stop or change that process.
```

**Check if cloudflared is already installed:**
```bash
cloudflared --version
# If command not found, you will install it in Section 10.
```

**Check if the retriever OS user already exists:**
```bash
id retriever
# If it exists, note the UID/GID and skip the useradd step in Section 2.
```

**Check available disk space:**
```bash
df -h /opt
# Should have at least 2GB free for releases, venvs, and shared storage.
```

Do not proceed until port 8810 is confirmed free and you know old Retriever's port.

---

## Section 1 — Server Prerequisites

Old Retriever is already running on this box, so most prerequisites are met. Confirm:

- [ ] You have SSH access and sudo rights on `bggol-vesko01`
- [ ] OS: Ubuntu LTS or Debian (already installed)
- [ ] Outbound HTTPS (port 443) already works (old Retriever uses it)
- [ ] Port 8810 is confirmed free (from Section 0 check above)
- [ ] Old Retriever process and port are noted — will not be touched
- [ ] Inbound LAN access restricted to approved operators only (no public inbound)
- [ ] Time sync configured (chrony or systemd-timesyncd)
- [ ] Log rotation configured (`logrotate` or equivalent)
- [ ] SSH access limited to approved operators via key authentication only
- [ ] Backup process identified for MySQL `retriever_cloudflare` and `/opt/retriever-rebuild/shared`

---

## Section 2 — OS User and Directory Structure

Run as root or via sudo.

```bash
# Create the retriever service user (no login shell, no home directory)
useradd --system --no-create-home --shell /usr/sbin/nologin retriever

# Create directory tree
mkdir -p /opt/retriever-rebuild/releases
mkdir -p /opt/retriever-rebuild/shared/uploads
mkdir -p /opt/retriever-rebuild/shared/reports
mkdir -p /opt/retriever-rebuild/shared/tmp
mkdir -p /opt/retriever-rebuild/repo
mkdir -p /opt/retriever-rebuild/bin
mkdir -p /etc/retriever-rebuild
mkdir -p /var/log/retriever-rebuild

# Ownership
chown -R retriever:retriever /opt/retriever-rebuild
chown -R root:retriever /etc/retriever-rebuild
chown -R retriever:retriever /var/log/retriever-rebuild

# Permissions
chmod 750 /opt/retriever-rebuild
chmod 750 /etc/retriever-rebuild
chmod 750 /var/log/retriever-rebuild
```

Verify:

```bash
ls -la /opt/retriever-rebuild/
ls -la /etc/retriever-rebuild/
ls -la /var/log/retriever-rebuild/
id retriever
```

---

## Section 3 — Python

The app requires Python 3.10 or newer. Ubuntu 22.04 ships Python 3.10; Ubuntu 24.04 ships Python 3.12. Either works.

```bash
# Check what's available
python3 --version

# If Python 3.10+ is not present, install it:
apt-get update && apt-get install -y python3 python3-venv python3-pip

# Confirm
python3 -m venv --help >/dev/null && echo "venv OK"
```

---

## Section 4 — MySQL Setup

Run these against the Boone MySQL server (from any host with MySQL client access, or the MySQL server itself).

```sql
-- Create the database
CREATE DATABASE IF NOT EXISTS retriever_cloudflare
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create the app user (replace <bggol-retriever01-lan-ip> and <password>)
-- Use the actual LAN IP or hostname of bggol-retriever01
CREATE USER 'retriever_app'@'<bggol-retriever01-lan-ip>'
  IDENTIFIED BY '<strong-password-stored-in-retriever.env>';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
  ON retriever_cloudflare.*
  TO 'retriever_app'@'<bggol-retriever01-lan-ip>';

FLUSH PRIVILEGES;
```

Test connection from `bggol-retriever01`:

```bash
mysql -h <mysql-server-host> -u retriever_app -p retriever_cloudflare -e "SELECT 1 AS test;"
# Should return: test = 1
```

---

## Section 5 — Production Environment File

Create `/etc/retriever-rebuild/retriever.env` with correct ownership and mode.

```bash
touch /etc/retriever-rebuild/retriever.env
chmod 640 /etc/retriever-rebuild/retriever.env
chown root:retriever /etc/retriever-rebuild/retriever.env
```

Now edit the file with real production values. Template:

```bash
nano /etc/retriever-rebuild/retriever.env
```

Paste and fill in real values (never commit this file):

```text
# App identity
RETRIEVER_ENV=production
RETRIEVER_PUBLIC_BASE_URL=https://retriever.boonegraphics.net
RETRIEVER_BIND_HOST=127.0.0.1
RETRIEVER_PORT=8810
RETRIEVER_COOKIE_SECRET=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
RETRIEVER_SESSION_TTL_SECONDS=86400
RETRIEVER_SEED_ADMIN_EMAIL=state@boonegraphics.net

# CRITICAL: both must be exactly as shown for production
LOCAL_DEV_IDENTITY_ENABLED=false
CLOUDFLARE_ACCESS_ENABLED=true
CLOUDFLARE_ACCESS_VALIDATE_JWT=true

# Fill in from Cloudflare dashboard (see CLOUDFLARE_SETUP.md)
CLOUDFLARE_ACCESS_TEAM_DOMAIN=<your-team>.cloudflareaccess.com
CLOUDFLARE_ACCESS_AUDIENCE=<application-audience-tag>
CLOUDFLARE_ACCESS_JWKS_URL=https://<your-team>.cloudflareaccess.com/cdn-cgi/access/certs

# MySQL
MYSQL_HOST=<boone-mysql-server-host>
MYSQL_PORT=3306
MYSQL_DATABASE=retriever_cloudflare
MYSQL_USER=retriever_app
MYSQL_PASSWORD=<password-from-section-4>
MYSQL_SSL_MODE=preferred

# Feature gates (keep disabled until each is proven)
FETCH_ENABLED=false
FETCH_GENERAL_QUESTIONS_ENABLED=false
FETCH_UPLOADS_ENABLED=false
FETCH_DELAYED_REPORTS_ENABLED=true

# Model provider (leave empty until Fetch is enabled)
MODEL_PROVIDER=
ANTHROPIC_API_KEY=
MODEL_DEFAULT=

# All other routes disabled at first launch
DOCS_ROUTE_ENABLED=false
DOCS_SERVICE_URL=
PRINTSMITH_ROUTE_ENABLED=false
PRINTSMITH_TOKEN_AUTHORITY_MODE=disabled
PRINTSMITH_TOKEN_PROXY_URL=
PRINTSMITH_TOKEN_PROXY_KEY=

BOONEOPS_BROKER_ENABLED=false
BOONEOPS_BROKER_URL=
BOONEOPS_BROKER_BEARER_TOKEN=
BOONEOPS_BROKER_HMAC_SECRET=
BOONEOPS_BROKER_REQUIRES_TAILSCALE=true

# Runtime storage
RETRIEVER_SHARED_DIR=/opt/retriever-rebuild/shared
RETRIEVER_UPLOAD_DIR=/opt/retriever-rebuild/shared/uploads
RETRIEVER_REPORT_DIR=/opt/retriever-rebuild/shared/reports

# Logging
LOG_LEVEL=info
AUDIT_LOG_MODE=mysql
AUDIT_LOG_FILE=/var/log/retriever-rebuild/audit.jsonl

# Host identity (populated automatically by deploy.sh, but set manually on first deploy)
GIT_SHA=
GIT_REF=
HOST_NAME=bggol-vesko01
```

Verify file is readable by the retriever group and not world-readable:

```bash
ls -la /etc/retriever-rebuild/retriever.env
# Should show: -rw-r----- 1 root retriever
```

---

## Section 6 — Deploy Scripts

Copy the deployment scripts from the release (or bootstrap them manually before the first release):

```bash
# Option A: Copy from the first release after pulling the repo
cp /opt/retriever-rebuild/repo/deploy/deploy.sh    /opt/retriever-rebuild/bin/deploy.sh
cp /opt/retriever-rebuild/repo/deploy/rollback.sh  /opt/retriever-rebuild/bin/rollback.sh
cp /opt/retriever-rebuild/repo/deploy/smoke.sh     /opt/retriever-rebuild/bin/smoke.sh
cp /opt/retriever-rebuild/repo/deploy/healthcheck.sh /opt/retriever-rebuild/bin/healthcheck.sh

chmod +x /opt/retriever-rebuild/bin/*.sh
chown root:retriever /opt/retriever-rebuild/bin/*.sh
```

Note: `deploy.sh` must be run as root (or via sudo) because it restarts the systemd service. Scripts themselves should be owned by root to prevent tampering.

---

## Section 7 — First Code Pull and Bootstrap

Before `deploy.sh` exists on the server, do the first pull manually:

```bash
# Clone the repo
git clone https://github.com/bobtucker1129/Retriever.git /opt/retriever-rebuild/repo

# Copy deploy scripts
cp /opt/retriever-rebuild/repo/deploy/deploy.sh      /opt/retriever-rebuild/bin/
cp /opt/retriever-rebuild/repo/deploy/rollback.sh    /opt/retriever-rebuild/bin/
cp /opt/retriever-rebuild/repo/deploy/smoke.sh       /opt/retriever-rebuild/bin/
cp /opt/retriever-rebuild/repo/deploy/healthcheck.sh /opt/retriever-rebuild/bin/
chmod +x /opt/retriever-rebuild/bin/*.sh

# Fix ownership of the whole tree
chown -R retriever:retriever /opt/retriever-rebuild/releases
chown -R retriever:retriever /opt/retriever-rebuild/shared
```

---

## Section 8 — Database Migration

Run migrations once, before starting the service for the first time.

```bash
# Set the flag to run migrations on next deploy
export RETRIEVER_RUN_MIGRATIONS=true

# Run first deploy (this will run migrations then start the service)
sudo RETRIEVER_RUN_MIGRATIONS=true /opt/retriever-rebuild/bin/deploy.sh main
```

Or run migrations manually if you prefer:

```bash
# Load the env
set -a; source /etc/retriever-rebuild/retriever.env; set +a

# Run migrations directly
cd /opt/retriever-rebuild/current
.venv/bin/python -c "
from app.db.connection import get_db_connection
from app.db.migrations import run_migrations_and_seeds
import asyncio
async def main():
    conn = await get_db_connection()
    await run_migrations_and_seeds(conn)
    await conn.close()
asyncio.run(main())
"
```

---

## Section 9 — Systemd Service

```bash
# Copy the unit file (use the example from the repo as the base)
cp /opt/retriever-rebuild/current/deploy/systemd/retriever-web.service.example \
   /etc/systemd/system/retriever-web.service

# Reload systemd
systemctl daemon-reload

# Enable the service (start on boot)
systemctl enable retriever-web.service

# Start it
systemctl start retriever-web.service

# Check status
systemctl status retriever-web.service
journalctl -u retriever-web -n 50 --no-pager
```

The service reads environment from `/etc/retriever-rebuild/retriever.env`. If the env file is wrong, the service will fail to start with a config validation error.

---

## Section 10 — Cloudflare Tunnel

See `CLOUDFLARE_SETUP.md` for the full Cloudflare Tunnel and Access setup guide.

Short version:

1. Install `cloudflared` on `bggol-retriever01`
2. Authenticate: `cloudflared tunnel login`
3. Create tunnel: `cloudflared tunnel create retriever`
4. Add DNS route: `cloudflared tunnel route dns retriever retriever.boonegraphics.net`
5. Create config: `/etc/cloudflared/config.yml` pointing to `localhost:8810`
6. Install as service: `cloudflared service install`
7. Start: `systemctl start cloudflared`

---

## Section 11 — First Deploy and Smoke Test

```bash
# Run the full deploy (without migrations if you already ran them)
sudo /opt/retriever-rebuild/bin/deploy.sh main

# Check the service
systemctl status retriever-web.service
journalctl -u retriever-web -n 30 --no-pager

# Local smoke
/opt/retriever-rebuild/bin/smoke.sh

# Cloudflare smoke (after tunnel is running)
RETRIEVER_SMOKE_CF_URL=https://retriever.boonegraphics.net \
  /opt/retriever-rebuild/bin/smoke.sh
```

---

## Section 12 — Acceptance Checklist

The deployment is ready when every item below passes.

**VM (bggol-vesko01):**
- [ ] `retriever` OS user exists with no login shell
- [ ] `/opt/retriever-rebuild/`, `/etc/retriever-rebuild/`, `/var/log/retriever-rebuild/` exist with correct ownership
- [ ] `/etc/retriever-rebuild/retriever.env` is mode 0640, owner root:retriever
- [ ] Old Retriever process is still running normally on its original port

**Database:**
- [ ] `retriever_cloudflare` schema exists on Boone MySQL
- [ ] `retriever_app` user can connect from `bggol-retriever01`
- [ ] Migrations ran successfully (`retriever_cloudflare.schema_migrations` table exists)

**Config:**
- [ ] `RETRIEVER_ENV=production`
- [ ] `LOCAL_DEV_IDENTITY_ENABLED=false`
- [ ] `CLOUDFLARE_ACCESS_ENABLED=true`
- [ ] `CLOUDFLARE_ACCESS_VALIDATE_JWT=true`
- [ ] `RETRIEVER_COOKIE_SECRET` is 64 hex chars, not a placeholder

**Service:**
- [ ] `systemctl status retriever-web.service` shows `active (running)`
- [ ] `journalctl -u retriever-web -n 20` shows no startup errors
- [ ] `curl http://127.0.0.1:8810/health/live` returns `{"status": "ok", ...}`
- [ ] `curl http://127.0.0.1:8810/health/ready` shows `mysql: ok` (or at least no `failed`)
- [ ] `curl http://127.0.0.1:8810/version` shows correct `gitSha` and `environment: production`

**Cloudflare:**
- [ ] `cloudflared` service is running
- [ ] `retriever.boonegraphics.net` resolves via Cloudflare DNS
- [ ] Browser visit to `retriever.boonegraphics.net` shows Cloudflare Access challenge (or app for approved users)
- [ ] `/health/live` and `/version` are reachable through the public hostname

**Security:**
- [ ] Direct LAN HTTP to port 8810 is blocked from outside the VM (only localhost binds)
- [ ] `/fetch` route returns 404 or disabled response (not a working chat interface)
- [ ] App shell shows pending-user page for a new Cloudflare-authenticated user who has not been approved

**Old Retriever (coexistence):**
- [ ] Old Retriever is still running normally on its original port
- [ ] PrintSmith token authority is untouched
- [ ] No old Retriever routes, processes, or config files were modified

---

## Rollback (if needed)

```bash
sudo /opt/retriever-rebuild/bin/rollback.sh "reason for rollback"
```

For emergency manual rollback without scripts:

```bash
sudo systemctl stop retriever-web
sudo ln -sfn /opt/retriever-rebuild/releases/<known-good-sha> /opt/retriever-rebuild/current
sudo systemctl start retriever-web
sudo /opt/retriever-rebuild/bin/healthcheck.sh
```

---

## Log Access

```bash
# Live service logs
sudo journalctl -u retriever-web -f

# Deploy history
cat /var/log/retriever-rebuild/deploy.log

# App audit log (after it starts writing)
sudo tail -f /var/log/retriever-rebuild/audit.jsonl
```

# VM Setup Runbook: bggol-vesko01 (Windows Server)

**Server:** `bggol-vesko01` — Windows Server 2022 (Build 20348)  
**LAN IP:** `192.168.33.12`  
**New Retriever port:** `8810` (localhost only, behind Cloudflare Tunnel)  
**Old Retriever port:** `8000` — do not touch it  
**Public hostname:** `retriever.boonegraphics.net` via Cloudflare Access + Cloudflare Tunnel

> New Retriever runs beside old Retriever on the same box. Old Retriever's process,
> service (`Retriever`), port, and PrintSmith token authority are never touched.

Run all PowerShell commands as Administrator unless noted otherwise.

---

## Deployment Guardrails — Do Not Regress

These are lessons from the first live deploy attempt and should be treated as
fixed facts for future agents:

- This host is **Windows Server**, not Linux. Do not create bash, systemd,
  `/opt`, `/etc`, or `/var/log` deployment instructions for first launch.
- Old Retriever already runs on `bggol-vesko01` as the `Retriever` Windows
  service on port `8000`. New Retriever runs beside it as `RetrieverRebuild`
  on port `8810`.
- New Retriever uses the old server's Python runtime to create its own release
  virtual environments. On the first deploy, the server used Python 3.14 from
  `C:\Program Files\Python314\python.exe`; old Retriever's venv Python is a
  fallback at `D:\Repository\pm-review-dashboard-ContexEng\venv\Scripts\python.exe`.
- PowerShell on this server is Windows PowerShell 5.1. Do not use PowerShell 7+
  syntax such as `?.`; do not use `$Args` as a function parameter name because
  it shadows a PowerShell automatic variable.
- Old Retriever leaves system/user environment variables such as `FETCH_*`,
  `MODEL_*`, `ANTHROPIC_*`, `BOONEOPS_*`, and `PRINTSMITH_*`. `deploy.ps1` and
  `run-service.ps1` intentionally clear those at process scope before loading
  `D:\retriever-rebuild\env\retriever.env`.
- The project uses `pyproject.toml`, not `requirements.txt`. Deploy installs
  with `pip install ".[dev]"` from the release directory.
- Tests are pre-push/local verification, not deploy-time verification. The tests
  expect local config and will fail under production env. Deploy-time checks are
  import check, config validation, optional migrations, service health, and smoke.
- The migration API is `app.db.migrations.run_migrations(include_seeds=True)`.
  Do not call non-existent helpers such as `get_db_connection` or
  `run_migrations_and_seeds`.
- `git clone` and `git checkout` may write normal progress messages to stderr.
  The deploy script uses explicit exit-code checks instead of relying on
  `$ErrorActionPreference = "Stop"` for native commands.

First proven release:

```text
ed41f94261910256edc71d104adcabf7dd00324c
```

That release successfully:

- loaded production env from `D:\retriever-rebuild\env\retriever.env`
- cleared inherited old-Fetch env vars
- installed dependencies from `pyproject.toml`
- passed the import check
- validated production config
- applied `0001_retriever_cloudflare.sql`
- applied `0001_seed_auth_shell.sql`
- pointed `D:\retriever-rebuild\current` at the staged release

---

## Section 0 — Preflight Checks

Open a Command Prompt or PowerShell as Administrator and run these first.

```powershell
# Confirm Python is available (old Retriever's venv Python can be reused to create new venv)
D:\Repository\pm-review-dashboard-ContexEng\venv\Scripts\python.exe --version
# Expected: Python 3.13.x

# Confirm port 8810 is free
netstat -ano | findstr :8810
# Expected: no output (port is free)

# Confirm old Retriever is still on 8000 and running
netstat -ano | findstr :8000
Get-Service -Name Retriever

# Confirm NSSM is available (already installed for old Retriever)
nssm.exe version
# If not in PATH, check: C:\nssm\win64\nssm.exe

# Confirm Git is installed
git --version

# Check free disk space
Get-PSDrive D
# Need at least 2GB free
```

Do not proceed until port 8810 is confirmed free.

---

## Section 1 — Directory Structure

```powershell
# Create the directory tree
New-Item -ItemType Directory -Path "D:\retriever-rebuild\releases"  -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\shared\uploads"  -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\shared\reports"  -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\shared\tmp"      -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\repo"            -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\bin"             -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\env"             -Force
New-Item -ItemType Directory -Path "D:\retriever-rebuild\logs"            -Force

# Restrict env directory to Administrators only
icacls "D:\retriever-rebuild\env" /inheritance:r /grant:r "BUILTIN\Administrators:(OI)(CI)F" /grant:r "NT AUTHORITY\SYSTEM:(OI)(CI)F"
```

---

## Section 2 — Production Environment File

Create the env file and lock it down:

```powershell
New-Item -ItemType File -Path "D:\retriever-rebuild\env\retriever.env" -Force
icacls "D:\retriever-rebuild\env\retriever.env" /inheritance:r /grant:r "BUILTIN\Administrators:F" /grant:r "NT AUTHORITY\SYSTEM:F"
```

Open it in Notepad and fill in real values:

```powershell
notepad D:\retriever-rebuild\env\retriever.env
```

Paste this template and fill in every `<...>` placeholder:

```text
# App identity
RETRIEVER_ENV=production
RETRIEVER_PUBLIC_BASE_URL=https://retriever.boonegraphics.net
RETRIEVER_BIND_HOST=127.0.0.1
RETRIEVER_PORT=8810
RETRIEVER_COOKIE_SECRET=<run: python -c "import secrets; print(secrets.token_hex(32))">
RETRIEVER_SESSION_TTL_SECONDS=86400
RETRIEVER_SEED_ADMIN_EMAIL=state@boonegraphics.net

# CRITICAL: both must be exactly as shown
LOCAL_DEV_IDENTITY_ENABLED=false
CLOUDFLARE_ACCESS_ENABLED=true
CLOUDFLARE_ACCESS_VALIDATE_JWT=true

# From Cloudflare Zero Trust dashboard (see CLOUDFLARE_SETUP.md)
CLOUDFLARE_ACCESS_TEAM_DOMAIN=<your-team>.cloudflareaccess.com
CLOUDFLARE_ACCESS_AUDIENCE=<application-audience-tag>
CLOUDFLARE_ACCESS_JWKS_URL=https://<your-team>.cloudflareaccess.com/cdn-cgi/access/certs

# MySQL (Boone MySQL server at 192.168.33.243)
MYSQL_HOST=192.168.33.243
MYSQL_PORT=3306
MYSQL_DATABASE=retriever_cloudflare
MYSQL_USER=retriever_app
MYSQL_PASSWORD=<strong-password>
MYSQL_SSL_MODE=preferred

# Feature gates — keep disabled until each is proven
FETCH_ENABLED=false
FETCH_GENERAL_QUESTIONS_ENABLED=false
FETCH_UPLOADS_ENABLED=false
FETCH_DELAYED_REPORTS_ENABLED=true
MODEL_PROVIDER=
ANTHROPIC_API_KEY=
MODEL_DEFAULT=

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

# Runtime storage (Windows paths)
RETRIEVER_SHARED_DIR=D:\retriever-rebuild\shared
RETRIEVER_UPLOAD_DIR=D:\retriever-rebuild\shared\uploads
RETRIEVER_REPORT_DIR=D:\retriever-rebuild\shared\reports

# Logging
LOG_LEVEL=info
AUDIT_LOG_MODE=mysql
AUDIT_LOG_FILE=D:\retriever-rebuild\logs\audit.jsonl

# Host identity
HOST_NAME=bggol-vesko01
```

**Generate a cookie secret** (run this in Python once and paste the result):

```powershell
D:\Repository\pm-review-dashboard-ContexEng\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

---

## Section 3 — MySQL Setup

Connect to the Boone MySQL server at `192.168.33.243` and run:

```sql
CREATE DATABASE IF NOT EXISTS retriever_cloudflare
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'retriever_app'@'192.168.33.12'
  IDENTIFIED BY '<same-password-as-env-file>';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
  ON retriever_cloudflare.*
  TO 'retriever_app'@'192.168.33.12';

FLUSH PRIVILEGES;
```

Test from `bggol-vesko01`:

```powershell
# If mysql client is available
mysql -h 192.168.33.243 -u retriever_app -p retriever_cloudflare -e "SELECT 1 AS test;"
```

---

## Section 4 — Copy Deploy Scripts to bin\

After the first Git clone (Section 5), copy scripts into bin\:

```powershell
Copy-Item "D:\retriever-rebuild\repo\deploy\deploy.ps1"      "D:\retriever-rebuild\bin\"
Copy-Item "D:\retriever-rebuild\repo\deploy\rollback.ps1"    "D:\retriever-rebuild\bin\"
Copy-Item "D:\retriever-rebuild\repo\deploy\smoke.ps1"       "D:\retriever-rebuild\bin\"
Copy-Item "D:\retriever-rebuild\repo\deploy\healthcheck.ps1" "D:\retriever-rebuild\bin\"
Copy-Item "D:\retriever-rebuild\repo\deploy\windows\run-service.ps1"      "D:\retriever-rebuild\bin\"
Copy-Item "D:\retriever-rebuild\repo\deploy\windows\install-service.ps1"  "D:\retriever-rebuild\bin\"
```

---

## Section 5 — First Code Pull and Deploy

```powershell
# Clone the repo
git clone https://github.com/bobtucker1129/Retriever.git D:\retriever-rebuild\repo

# Copy scripts to bin\ (see Section 4 above)

# Run first deploy with migrations.
# Use .NET process env so the child PowerShell process receives it.
[System.Environment]::SetEnvironmentVariable("RETRIEVER_RUN_MIGRATIONS", "true", "Process")
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
```

The deploy script will:
1. Clone/fetch from GitHub
2. Create a release directory at `D:\retriever-rebuild\releases\<sha>\`
3. Create a `.venv` and install from `pyproject.toml`
4. Run the import check
5. Validate config against the env file
6. Run migrations (because `RETRIEVER_RUN_MIGRATIONS=true`)
7. Set `D:\retriever-rebuild\current` junction to the new release
8. Try to restart the `RetrieverRebuild` service (will skip if not yet installed)
9. Run health and smoke checks

---

## Section 6 — Install Windows Service

After the first deploy has laid down a release:

```powershell
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\install-service.ps1
```

This registers `RetrieverRebuild` as a Windows Service using NSSM (already installed for old Retriever), sets log rotation, and starts the service.

Verify:

```powershell
Get-Service RetrieverRebuild
# Should show: Status=Running

# Check startup log
Get-Content D:\retriever-rebuild\logs\service-bootstrap.log -Tail 20

# Confirm it's listening on 8810
netstat -ano | findstr :8810
```

---

## Section 7 — Cloudflare Tunnel

See `CLOUDFLARE_SETUP.md` for the full guide. Short version for Windows:

```powershell
# Download cloudflared for Windows
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile "C:\cloudflared\cloudflared.exe"

# Add to PATH (or call with full path)
$env:PATH += ";C:\cloudflared"

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create retriever

# Create config file at C:\cloudflared\config.yml (see CLOUDFLARE_SETUP.md)

# Route DNS
cloudflared tunnel route dns retriever retriever.boonegraphics.net

# Install as Windows Service
cloudflared service install

# Start
Start-Service cloudflared
```

---

## Section 8 — First Smoke Test

```powershell
# Local smoke
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\smoke.ps1

# Cloudflare-path smoke (after tunnel is running)
$env:RETRIEVER_SMOKE_CF_URL = "https://retriever.boonegraphics.net"
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\smoke.ps1
```

---

## Section 9 — Acceptance Checklist

- [ ] `netstat -ano | findstr :8810` shows the Retriever process listening
- [ ] `netstat -ano | findstr :8000` shows old Retriever still listening (untouched)
- [ ] `Get-Service RetrieverRebuild` shows `Running`
- [ ] `Get-Service Retriever` shows `Running` (old Retriever unaffected)
- [ ] `Invoke-WebRequest http://127.0.0.1:8810/health/live` returns `{"status":"ok",...}`
- [ ] `Invoke-WebRequest http://127.0.0.1:8810/health/ready` shows `mysql: ok`
- [ ] `Invoke-WebRequest http://127.0.0.1:8810/version` shows `environment: production` and correct `gitSha`
- [ ] `LOCAL_DEV_IDENTITY_ENABLED=false` confirmed in env file
- [ ] `CLOUDFLARE_ACCESS_VALIDATE_JWT=true` confirmed in env file
- [ ] `RETRIEVER_COOKIE_SECRET` is 64 hex chars, not a placeholder
- [ ] Browser visit to `retriever.boonegraphics.net` shows Cloudflare Access challenge
- [ ] Approved `@boonegraphics.net` login reaches the Retriever app shell
- [ ] A new user who has not been approved sees the pending-user page, not Fetch
- [ ] `/fetch` returns disabled/404 (not a working chat interface)
- [ ] Old Retriever at `http://192.168.33.12:8000` still works normally

---

## Rollback

```powershell
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\rollback.ps1
# With a reason:
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\rollback.ps1 -Reason "health check failure"
```

Emergency manual rollback:

```powershell
Stop-Service RetrieverRebuild
# List available releases to find known-good SHA:
Get-ChildItem D:\retriever-rebuild\releases
# Swap the junction manually:
Remove-Item D:\retriever-rebuild\current -Force
New-Item -ItemType Junction -Path D:\retriever-rebuild\current -Target D:\retriever-rebuild\releases\<known-good-sha>
Start-Service RetrieverRebuild
```

---

## Log Access

```powershell
# Live service output (NSSM-captured stdout)
Get-Content D:\retriever-rebuild\logs\service-stdout.log -Tail 50 -Wait

# Bootstrap log (startup sequence)
Get-Content D:\retriever-rebuild\logs\service-bootstrap.log -Tail 20

# Deploy history
Get-Content D:\retriever-rebuild\logs\deploy.log

# Windows Event Log for service failures
Get-EventLog -LogName Application -Source "RetrieverRebuild" -Newest 20
```

---

## Future Deploys

After the service is installed, all future deploys are one command:

```powershell
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
# Or a specific SHA:
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 <sha>
```

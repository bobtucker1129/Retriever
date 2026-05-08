# Cloudflare Setup: retriever.boonegraphics.net

**Purpose:** Route `retriever.boonegraphics.net` through Cloudflare Access (identity gate) and Cloudflare Tunnel (connection to the VM) so only authenticated Boone employees can reach the app.

**Server:** `bggol-vesko01` (Windows Server)  
**App bind:** `127.0.0.1:8810`  
**Cloudflare account:** the existing Boone boonegraphics.net zone

---

## Overview

```text
Employee browser
  -> Cloudflare Access (identity check, blocks unapproved requests)
  -> Cloudflare Tunnel (encrypted connection to bggol-vesko01)
  -> localhost:8810 (Retriever app)
```

The VM has no public open ports. Traffic enters only through the Cloudflare Tunnel. Direct LAN HTTP to port 8810 is localhost-only.

---

## Part 1 — Cloudflare Tunnel

### Step 1.1 — Install cloudflared

On `bggol-vesko01` (Windows Server), run as Administrator:

```powershell
# Download the Windows binary
New-Item -ItemType Directory -Path "C:\cloudflared" -Force
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
    -OutFile "C:\cloudflared\cloudflared.exe"

# Add to system PATH permanently
[System.Environment]::SetEnvironmentVariable(
    "PATH",
    [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";C:\cloudflared",
    "Machine"
)

# Reload PATH in current session
$env:PATH += ";C:\cloudflared"

# Verify
cloudflared --version
```

### Step 1.2 — Authenticate

```bash
cloudflared tunnel login
```

This opens a browser link. Log in with the Boone Cloudflare account and authorize the `boonegraphics.net` zone. This saves a certificate to `~/.cloudflared/cert.pem`.

### Step 1.3 — Create the tunnel

```bash
cloudflared tunnel create retriever
```

This creates a tunnel and writes credentials to `~/.cloudflared/<tunnel-uuid>.json`. Record the tunnel UUID — you will need it for the config file.

```bash
# List tunnels to confirm and get the UUID
cloudflared tunnel list
```

### Step 1.4 — Create the tunnel config file

Create `/etc/cloudflared/config.yml`:

```powershell
notepad C:\cloudflared\config.yml
```

Paste:

```yaml
# C:\cloudflared\config.yml
tunnel: <tunnel-uuid>
credentials-file: C:\cloudflared\<tunnel-uuid>.json

ingress:
  - hostname: retriever.boonegraphics.net
    service: http://localhost:8810
  - service: http_status:404
```

Replace `<tunnel-uuid>` with the UUID from Step 1.3.

Move the credentials file (created automatically by `cloudflared tunnel create`):

```powershell
Copy-Item "$env:USERPROFILE\.cloudflared\<tunnel-uuid>.json" "C:\cloudflared\"
icacls "C:\cloudflared\<tunnel-uuid>.json" /inheritance:r /grant:r "BUILTIN\Administrators:F" /grant:r "NT AUTHORITY\SYSTEM:F"
```

### Step 1.5 — Create the DNS record

```powershell
cloudflared tunnel route dns retriever retriever.boonegraphics.net
```

This creates a `CNAME` in the Boone Cloudflare DNS pointing `retriever.boonegraphics.net` to the tunnel.

Verify in the Cloudflare dashboard: DNS > Records > look for `retriever` as a CNAME to `<uuid>.cfargotunnel.com`.

### Step 1.6 — Install and start as a Windows Service

```powershell
# Install as a Windows Service (run as Administrator), then force the service
# command to use this config file. cloudflared service install may otherwise
# install only C:\cloudflared\cloudflared.exe with no tunnel/config arguments.
cloudflared --config C:\cloudflared\config.yml service install

sc.exe config cloudflared binPath= '"C:\cloudflared\cloudflared.exe" --config "C:\cloudflared\config.yml" tunnel run retriever'

# Start the service
Start-Service cloudflared

# Check status
Get-Service cloudflared
sc.exe qc cloudflared

# View logs
Get-EventLog -LogName Application -Source "cloudflared" -Newest 20
```

The working `BINARY_PATH_NAME` is:

```text
C:\cloudflared\cloudflared.exe --config C:\cloudflared\config.yml tunnel run retriever
```

If `Stop-Service cloudflared` hangs in `STOP_PENDING`, use:

```powershell
sc.exe queryex cloudflared
taskkill /PID <PID_FROM_QUERYEX> /F
```

### Step 1.7 — Verify tunnel connectivity

```powershell
# From bggol-vesko01 (after the Retriever app is running on 8810)
Invoke-WebRequest -Uri "http://localhost:8810/health/live" -UseBasicParsing

# From outside (before Access policy is active - should return tunnel response)
Invoke-WebRequest -Uri "https://retriever.boonegraphics.net/health/live" -UseBasicParsing
```

---

## Part 2 — Cloudflare Access Policy

Cloudflare Access is the identity gate. Set it up in the Cloudflare Zero Trust dashboard.

### Step 2.1 — Open Zero Trust dashboard

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Select the Boone account
3. Navigate to **Zero Trust** > **Access** > **Applications**

### Step 2.2 — Create the application

Click **Add an application** > **Self-hosted**.

Fill in:

| Field | Value |
|---|---|
| Application name | `Retriever` |
| Session duration | 24 hours (or per Boone policy) |
| Application domain | `retriever.boonegraphics.net` |

### Step 2.3 — Create the Access policy

Under the application, add a policy:

| Field | Value |
|---|---|
| Policy name | `Boone employees` |
| Action | Allow |
| Rule: Include | Emails ending in `@boonegraphics.net` |

This means only addresses ending in `@boonegraphics.net` can pass the Access gate. All others see the Cloudflare login/block page.

You can add a second policy for **Bypass** on `/health/live` and `/version` if you want those routes reachable without login — but that is optional since the Retriever app itself handles health checks through localhost.

### Step 2.4 — Get the Application Audience Tag

After creating the application, Cloudflare shows an **Application Audience (AUD) Tag** — a long hex string.

Copy it. This is `CLOUDFLARE_ACCESS_AUDIENCE` in `/etc/retriever-rebuild/retriever.env`.

Also note your team domain (e.g. `boone.cloudflareaccess.com`). This is `CLOUDFLARE_ACCESS_TEAM_DOMAIN`.

The JWKS URL is always:

```text
https://<team-domain>/cdn-cgi/access/certs
```

Update the env file with these three values before starting the Retriever service.

### Step 2.5 — Test the Access gate

Visit `https://retriever.boonegraphics.net` in a browser.

Expected behavior:
- Without a Boone Google account or authorized email: Cloudflare Access login page
- With an approved `@boonegraphics.net` email: Cloudflare issues a JWT and forwards to the Retriever app
- Retriever app receives `Cf-Access-Jwt-Assertion` header, validates it, and proceeds to the pending-user or home page

---

## Part 3 — Service Token for Smoke Tests

For automated smoke checks that need to pass through Access without a browser, create a Cloudflare Access Service Token.

### Step 3.1 — Create the service token

In Zero Trust dashboard:
1. **Access** > **Service Auth** > **Service Tokens**
2. **Create Service Token**
3. Name it `retriever-smoke` (or `retriever-healthcheck`)
4. Save the **Client ID** and **Client Secret** — these are only shown once

### Step 3.2 — Authorize the token

On the Retriever application policy, add a second policy:

| Field | Value |
|---|---|
| Policy name | `Smoke service token` |
| Action | Service Auth |
| Rule: Include | Service Token: `retriever-smoke` |

### Step 3.3 — Store on the VM

Add to `/etc/retriever-rebuild/retriever.env` (never commit):

```text
# Cloudflare Access service token for smoke checks (client-id:client-secret)
RETRIEVER_SMOKE_CF_SERVICE_TOKEN=<client-id>:<client-secret>
```

Then run Cloudflare-path smoke checks:

```bash
source /etc/retriever-rebuild/retriever.env
RETRIEVER_SMOKE_CF_URL=https://retriever.boonegraphics.net \
  /opt/retriever-rebuild/bin/smoke.sh
```

---

## Troubleshooting

**Tunnel not connecting:**
```bash
journalctl -u cloudflared -n 50 --no-pager
cloudflared tunnel info retriever
```

**Access challenge not appearing (getting 404 instead):**
- Check that the DNS CNAME was created: `dig retriever.boonegraphics.net`
- Check that the ingress rule in `config.yml` matches the hostname exactly

**App starts but health check fails after tunnel is up:**
```bash
# Check app is actually bound
ss -tlnp | grep 8810
# Check config validated
journalctl -u retriever-web -n 30 --no-pager
```

**JWT validation failing (403 on app routes):**
- Confirm `CLOUDFLARE_ACCESS_AUDIENCE` matches the AUD tag in the Cloudflare dashboard exactly
- Confirm `CLOUDFLARE_ACCESS_JWKS_URL` is `https://<team-domain>/cdn-cgi/access/certs`
- Confirm the request is coming through the tunnel (not a direct LAN request without headers)

**Direct LAN spoofing protection:**
The app validates the JWT signature cryptographically against the Cloudflare JWKS endpoint. A direct LAN request with a fake `Cf-Access-Jwt-Assertion` header will fail signature verification. However, for defense in depth, consider a firewall rule on `bggol-retriever01` that blocks port 8810 from any host other than localhost.

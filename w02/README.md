# W02 — EC2 properly: systemd + nginx

## What this is

Deployed a FastAPI "hello" app on an Amazon Linux 2023 EC2 instance (`t3.micro`) behind a fixed Elastic IP.
The app runs as a systemd service (`hello.service`), bound to `127.0.0.1:8000`, so it restarts automatically on crash or reboot — never needs a manual SSH-and-restart.
nginx reverse-proxies port 80 to the app (`hello.conf`, dropped into `/etc/nginx/default.d/`), so the public internet only ever talks to nginx, never the app process directly.
Security group locked down to SSH (22, my IP only), HTTP (80) and HTTPS (443) open to everyone.

Verified live at `http://<Elastic-IP>/` returning:

```json
{"msg": "Hello from EC2 - W02", "owner": "Aman"}
```

Instance terminated and Elastic IP released after verification (free-tier cost discipline — a stopped instance or an unattached Elastic IP still bills).

## Architecture

```
Browser --http--> [Elastic IP:80] --> nginx --proxy_pass--> [127.0.0.1:8000] --> uvicorn (FastAPI, hello.service)
```

## Step-by-step, exactly as run

### 1. Billing guardrail (console, one-time)
- CloudWatch (region **us-east-1**, N. Virginia — billing metric only lives there) → Alarms → Create alarm
  → metric: Billing → Total Estimated Charge (USD) → threshold: Static, ≥ 5
  → new SNS topic, email endpoint → confirmed the subscription via the email link.
- Switched region back to **ap-south-1** (Mumbai) for everything else.

### 2. Launch the instance (console)
- EC2 → Launch instance
  - Name: `w02-fastapi`
  - AMI: Amazon Linux 2023
  - Instance type: `t3.micro` (free tier)
  - Key pair: existing `.pem`
  - Security group `w02-fastapi-sg`: SSH (22) from **My IP** · HTTP (80) from **Anywhere** · HTTPS (443) from **Anywhere**
  - Storage: default 8 GiB gp3
- Launch → wait for state = **Running**.

### 3. Elastic IP (console)
- EC2 → Network & Security → Elastic IPs → Allocate Elastic IP address → Allocate.
- Select it → Actions → Associate Elastic IP address → instance `w02-fastapi` → Associate.

### 4. SSH in (PowerShell, local machine)
```powershell
icacls .\key.pem /inheritance:r
icacls .\key.pem /grant:r "$env:USERNAME:R"
ssh -i .\key.pem ec2-user@<Elastic-IP>
```

### 5. Install runtime (on the instance)
```bash
sudo dnf install -y python3-pip nginx
pip3 install fastapi uvicorn
```

### 6. Write the app (on the instance)
```bash
mkdir -p ~/app && cat > ~/app/main.py <<'EOF'
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def hello():
    return {"msg": "Hello from EC2 - W02", "owner": "Aman"}
EOF
```

### 7. Run it as a systemd service (on the instance)
```bash
sudo tee /etc/systemd/system/hello.service <<'EOF'
[Unit]
Description=FastAPI hello
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/app
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now hello
curl http://127.0.0.1:8000    # confirms the app itself works, before nginx is in the picture
```
Check status/logs any time with:
```bash
sudo systemctl status hello
sudo journalctl -u hello -n 30 --no-pager
```

### 8. nginx reverse proxy (on the instance)
```bash
sudo mkdir -p /etc/nginx/default.d
sudo tee /etc/nginx/default.d/hello.conf <<'EOF'
location / {
    proxy_pass http://127.0.0.1:8000;
}
EOF
sudo nginx -t && sudo systemctl enable --now nginx && sudo systemctl restart nginx
```

### 9. Verify from outside (local machine)
Browser → `http://<Elastic-IP>` (explicit `http://` — no TLS cert was set up, `https` will never load) → JSON renders. Screenshot taken as proof artifact.

### 10. Cleanup (console)
- EC2 → select `w02-fastapi` → Instance state → **Terminate**.
- Elastic IPs → select the IP → Actions → **Disassociate** → Actions → **Release Elastic IP addresses**.

## Files in this folder

| File | Purpose |
|---|---|
| `main.py` | The FastAPI app itself |
| `hello.service` | systemd unit — runs the app as a supervised background service |
| `hello.conf` | nginx `location` block — reverse-proxies port 80 to the app on 8000 |

## Troubleshooting notes hit along the way

- `curl: (7) Failed to connect ... port 8000` right after `systemctl enable --now hello` — a timing false alarm from pasting the enable-and-curl commands as one block; `systemctl status hello` a few seconds later showed `active (running)` fine. Lesson: re-run `curl` before assuming the service is broken.
- nginx serving its own default page instead of the JSON = `hello.conf` wasn't picked up — re-check `sudo nginx -t` and that the file actually landed in `/etc/nginx/default.d/`.
- Nothing loads at all in the browser = usually the security group is missing the HTTP(80) rule, "My IP" changed since the SG was created, or the browser is forcing `https`.

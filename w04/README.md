# W04 — Docker on EC2: build → ECR → pull & run

## What this is

The same FastAPI hello app, but instead of systemd running `uvicorn` directly (w02), it's
packaged as a Docker image, pushed to a private **ECR** repo, then pulled back down and run
as a container. This proves the registry round-trip — build once, ship the image, run it
anywhere with docker installed — which is exactly the shape w06 (CI/CD) builds on.

Same trick as w03: the EC2 instance authenticates to ECR via an **IAM role**, not static
`docker login` credentials sitting on disk.

Target result: `http://<instance-public-ip>/` returning the JSON in [main.py](main.py), served
from a container pulled from ECR.

> Everything here — build, push, pull, run — happens **on the EC2 instance itself** via
> `git clone` of this repo. That's the simplest path (no Docker Desktop needed locally) and
> mirrors how a real deploy box works. If you have Docker installed locally, building and
> pushing from your own machine works identically — only the IAM-role step moves to `aws configure`.

## Architecture

```
EC2 instance (Docker installed, IAM role attached)
     |
     +-- docker build --------------------> local image  app:w04
     |
     +-- docker login (via IAM role, no static creds) --> ECR registry
     |
     +-- docker push  --------------------> ECR repo "app:w04"
     |
     +-- docker rmi (drop the local copy, to prove the next step is real)
     |
     +-- docker pull  <-------------------- ECR repo "app:w04"
     |
     +-- docker run -p 80:8000 -----------> container serving FastAPI
                                                    |
                                           Browser --http--> <public-ip>:80
```

## Step-by-step

### 1. Launch the EC2 instance (console)
- EC2 → Launch instance
  - Name: `w04-docker-demo`
  - AMI: Amazon Linux 2023, Instance type: `t3.micro` (free tier)
  - Key pair: existing `.pem`
  - Security group: SSH (22) from **My IP**, HTTP (80) from **Anywhere** (needed this time — the container serves on 80)
- Launch → wait for **Running**.

### 2. Create the ECR repo (console)
- ECR → Repositories → Create repository
  - Visibility: **Private**
  - Name: `app`
  - Leave scan-on-push / encryption on their defaults
- Create. Note the **URI** shown, e.g. `<account-id>.dkr.ecr.ap-south-1.amazonaws.com/app`.

### 3. Create the IAM role for ECR push/pull (console)
- IAM → Roles → Create role → Trusted entity: **AWS service** → Use case: **EC2**
- Permissions: attach the AWS-managed policy **`AmazonEC2ContainerRegistryPowerUser`**
  (push + pull; broader than the bucket-scoped custom policy from w03 — fine for a learning
  repo, but in production you'd scope this to the one repo ARN the same way w03 did for S3)
- Role name: `w04-ec2-ecr-role`
- Create role.

### 4. Attach the role to the instance (console)
- EC2 → select `w04-docker-demo` → Actions → Security → Modify IAM role → `w04-ec2-ecr-role` → Update.

### 5. SSH in and install Docker (instance)
```bash
ssh -i .\key.pem ec2-user@<instance-public-ip>
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
newgrp docker   # picks up the group change without a fresh login
```

### 6. Get the code onto the instance (instance)
```bash
git clone https://github.com/AmanYadavB/aws-week-by-week.git
cd aws-week-by-week/w04
```

### 7. Build and sanity-check the image locally (instance)
```bash
docker build -t app:w04 .
docker run --rm -d -p 8000:8000 --name test app:w04
curl 127.0.0.1:8000
docker stop test
```
`TODO: confirm output here once run.`

### 8. Authenticate to ECR via the instance role (instance)
```bash
aws sts get-caller-identity   # same proof as w03 — assumed-role identity, no static keys
aws ecr get-login-password --region ap-south-1 \
  | docker login --username AWS --password-stdin <account-id>.dkr.ecr.ap-south-1.amazonaws.com
```

### 9. Tag and push (instance)
```bash
docker tag app:w04 <account-id>.dkr.ecr.ap-south-1.amazonaws.com/app:w04
docker push <account-id>.dkr.ecr.ap-south-1.amazonaws.com/app:w04
```
Check ECR → repository `app` → the `w04` tag should now be listed.
`TODO: confirm output here once run.`

### 10. Prove the round-trip — drop the local image, pull it back (instance)
```bash
docker rmi app:w04 <account-id>.dkr.ecr.ap-south-1.amazonaws.com/app:w04
docker pull <account-id>.dkr.ecr.ap-south-1.amazonaws.com/app:w04
docker run -d -p 80:8000 --name hello <account-id>.dkr.ecr.ap-south-1.amazonaws.com/app:w04
curl 127.0.0.1:80
```

### 11. Verify from outside (local machine)
Browser → `http://<instance-public-ip>/` → JSON renders.
`TODO: paste the confirmed output / screenshot note here once actually run.`

### 12. Cleanup (console)
- On the instance: `docker stop hello`.
- ECR → repository `app` → delete the `w04` image (or the whole repo) — private ECR has a free-tier
  storage cap (500 MB-month for the first 12 months), harmless here but worth clearing.
- IAM → Roles → delete `w04-ec2-ecr-role` (or leave it if reusing next week).
- EC2 → terminate `w04-docker-demo`.

## Files in this folder

| File | Purpose |
|---|---|
| `main.py` | The FastAPI app (same shape as w02, message updated for w04) |
| `requirements.txt` | Python deps baked into the image |
| `Dockerfile` | Builds the image: python slim base, installs deps, runs uvicorn on 8000 |
| `.dockerignore` | Keeps `__pycache__`, `.git`, `README.md` out of the build context |

## Troubleshooting notes hit along the way

`TODO: fill these in as you actually hit them — likely candidates: "permission denied" on
docker.sock before the newgrp/re-login takes effect, ECR login rejected because the instance
role wasn't attached yet, browser showing nothing because the container is bound to 8000 but
the security group/curl check was against 80 (or vice versa).`

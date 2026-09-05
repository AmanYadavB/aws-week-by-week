# W03 — S3 static site + IAM role (no keys on disk)

## What this is

A static site hosted on S3, deployed by a boto3 script running on an EC2 instance —
and the instance never has an AWS access key anywhere on it. Instead it has an **IAM role**
attached, and both the AWS CLI and boto3 pull short-lived, auto-rotating credentials from
that role via the instance metadata service. `aws configure` is never run; `~/.aws/credentials`
never exists on this box.

Target result: `http://<bucket-name>.s3-website.ap-south-1.amazonaws.com/` returning the page
in [index.html](index.html).

> The `w02` EC2 instance was terminated during that week's cleanup, so this week launches a
> fresh instance. It doesn't need nginx/systemd — it's just a shell to run the CLI and the
> boto3 script from.

## Architecture

```
EC2 instance --IAM role--> temporary credentials (via instance metadata service)
     |
     +--(aws CLI: sts get-caller-identity)--> confirms identity, no static keys
     |
     +--(boto3: deploy.py)--> PutObject --> S3 bucket (static website hosting on)
                                                   |
                                          Browser --GetObject--> S3 website endpoint
```

## Step-by-step

### 1. Create the S3 bucket (console)
- S3 → Create bucket
  - Name: something globally unique, e.g. `w03-static-aman-<random>` (S3 bucket names are global across all of AWS, not just your account)
  - Region: **ap-south-1** (Mumbai), same as everything else this build-up
  - Uncheck **Block all public access** (needed — a static website bucket must serve objects publicly) → acknowledge the warning
- Create bucket.

### 2. Turn on static website hosting (console)
- Open the bucket → **Properties** tab → scroll to **Static website hosting** → Edit
  → Enable → Hosting type: "Host a static website" → Index document: `index.html` → Save.
- Note the **Bucket website endpoint** URL shown here — that's today's target URL.

### 3. Allow public reads (console)
- Bucket → **Permissions** tab → **Bucket policy** → Edit → paste [bucket-policy.json](bucket-policy.json)
  with `REPLACE_WITH_BUCKET_NAME` swapped for the real bucket name → Save.
- This only grants `s3:GetObject` (read) to everyone — not write, not list, not delete.

### 4. Upload the page once by hand, to sanity-check the bucket (console)
- Bucket → **Objects** → Upload → add [index.html](index.html) → Upload.
- Visit the website endpoint URL from step 2 → confirm the page renders.
  `TODO: confirm and note the actual output here once run.`

### 5. Create the IAM role (console)
- IAM → Roles → Create role
  - Trusted entity type: **AWS service** → Use case: **EC2**
  - Permissions: attach a policy scoped to just this bucket rather than full S3 access —
    create a custom policy (IAM → Policies → Create policy → **JSON tab**, not the visual
    editor) by pasting [role-policy.json](role-policy.json) with `REPLACE_WITH_BUCKET_NAME`
    swapped for the real bucket name. Name it `w03-ec2-s3-policy`.
    Note the two statements: `s3:ListBucket` is a bucket-level action so its resource is
    `arn:aws:s3:::<bucket-name>` (no `/*`), while `s3:GetObject`/`s3:PutObject` are
    object-level so their resource is `arn:aws:s3:::<bucket-name>/*`.
  - Role name: `w03-ec2-s3-role`
- Create role.

### 6. Launch the EC2 instance with the role attached (console)
- EC2 → Launch instance
  - Name: `w03-s3-demo`
  - AMI: Amazon Linux 2023, Instance type: `t3.micro` (free tier)
  - Key pair: existing `.pem`
  - Security group: SSH (22) from **My IP** only — no HTTP/HTTPS needed this week, nothing is served from the instance itself
  - Advanced details → **IAM instance profile** → select `w03-ec2-s3-role`
- Launch → wait for **Running**.
  (If you forget this at launch, it can be attached later via instance → Actions → Security → Modify IAM role.)

### 7. SSH in and prove there are no static credentials (instance)
```bash
ssh -i .\key.pem ec2-user@<instance-public-ip>
aws sts get-caller-identity
```
This should return an assumed-role identity (`w03-ec2-s3-role`) even though no `aws configure`
was ever run on this box. That's the whole point of the exercise — the CLI and any SDK on this
instance can authenticate as that role automatically.

### 8. Install tooling (instance)
```bash
sudo dnf install -y python3-pip      # AL2023 ships python3 but not pip
pip3 install -r requirements.txt
```
(`awscli` v2 is already preinstalled on Amazon Linux 2023 — no `dnf install` needed for it.
Alternatively, skip pip and get boto3 from the distro repo: `sudo dnf install -y python3-boto3`.)

### 9. Run the boto3 deploy script (instance)
```bash
export BUCKET_NAME=<your-bucket-name>
python3 deploy.py
```
`deploy.py` never passes credentials to `boto3.client("s3")` — see the comment at the top of
[deploy.py](deploy.py) for why that's the point, not an oversight.

### 10. Verify from outside (local machine)
Browser → the S3 website endpoint URL from step 2 → page renders.
`TODO: paste the confirmed output / note here once actually run.`

### 11. CLI basics, worth trying while connected
```bash
aws s3 ls                          # list your buckets
aws s3 ls s3://<bucket-name>       # list objects in this bucket
aws s3 cp index.html s3://<bucket-name>/index.html   # same upload, via CLI instead of boto3
```

### 12. Cleanup (console)
- S3 → bucket → Empty bucket (S3 won't delete a non-empty bucket) → then Delete bucket.
- IAM → Roles → delete `w03-ec2-s3-role` (or leave it if reusing next week).
- EC2 → terminate `w03-s3-demo`. No Elastic IP was allocated this week, so nothing to release there.

## Files in this folder

| File | Purpose |
|---|---|
| `index.html` | The static site page uploaded to S3 |
| `bucket-policy.json` | Public-read bucket policy (GetObject only) — swap in your bucket name |
| `role-policy.json` | IAM policy for the EC2 role — bucket-scoped List + object-scoped Get/Put |
| `deploy.py` | boto3 script that uploads `index.html` using the EC2 instance role, no static keys |
| `requirements.txt` | Python deps for `deploy.py` |

## Troubleshooting notes hit along the way

- `pip3: command not found` at step 8 — Amazon Linux 2023 has `python3` but not pip.
  `sudo dnf install -y python3-pip` first (or `sudo dnf install -y python3-boto3` and skip pip).

`TODO: fill these in as you actually hit them — e.g. bucket policy rejected for still having
Block Public Access on, `aws sts get-caller-identity` returning "Unable to locate credentials"
(role wasn't attached, or attached after boto3/CLI cached a failure — retry after re-SSHing),
403 on the website endpoint (object uploaded but bucket policy not saved / wrong bucket name
in the ARN).`

"""
Uploads index.html to the W03 static site bucket using boto3.

Deliberately does NOT call boto3.client("s3", aws_access_key_id=..., aws_secret_access_key=...).
No keys are configured anywhere on this box (no `aws configure` ever run, no ~/.aws/credentials).
boto3's default credential chain finds the IAM role attached to this EC2 instance via the
instance metadata service and gets short-lived, auto-rotating credentials from it instead.

Usage (on the EC2 instance):
    export BUCKET_NAME=your-bucket-name
    python3 deploy.py
"""
import os
import sys
import boto3

BUCKET_NAME = os.environ.get("BUCKET_NAME")
if not BUCKET_NAME:
    sys.exit("Set BUCKET_NAME env var to your bucket's name first.")

s3 = boto3.client("s3")  # no credentials passed in - comes from the instance role

s3.upload_file("index.html", BUCKET_NAME, "index.html", ExtraArgs={"ContentType": "text/html"})
print(f"Uploaded index.html to s3://{BUCKET_NAME}/index.html")

print("Bucket contents now:")
for obj in s3.list_objects_v2(Bucket=BUCKET_NAME).get("Contents", []):
    print(f"  {obj['Key']}  ({obj['Size']} bytes)")

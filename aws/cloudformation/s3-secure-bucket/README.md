# S3 — Secure Bucket

**When to use:** You need a bucket that is encrypted, versioned and never public by default.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

A baseline-hardened S3 bucket: AES-256 encryption at rest, versioning enabled, all four public access block settings on, and a bucket policy that denies any request not made over TLS.

## Parameters

| Parameter | Description |
|---|---|
| `BucketName` | Globally unique bucket name (no default — S3 names are global) |

## Outputs

| Output | Description |
|---|---|
| `BucketName` | Name of the created bucket |
| `BucketArn` | ARN of the created bucket |

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name my-secure-bucket \
  --parameter-overrides BucketName=my-globally-unique-bucket-name
```

## Notes

- Uses `AES256` (SSE-S3). Swap to `aws:kms` with a `KMSMasterKeyID` property if you need customer-managed key control or cross-account KMS grants.
- To grant access to this bucket, layer on one of the [policies](../../policies/) (e.g. `s3-read-only-access`, `s3-cross-account-access`) rather than loosening the public access block.
- **Retained on stack deletion:** the bucket and its TLS-only bucket policy both have `DeletionPolicy: Retain` (and `UpdateReplacePolicy: Retain`), because CloudFormation cannot delete a bucket that still holds objects and deleting the policy would strip the TLS restriction. After deleting the stack, delete the bucket yourself, or re-import it into another stack. The bucket is versioned, so `aws s3 rb --force` is not enough: first delete every object version and delete marker (for example `aws s3api list-object-versions --bucket <name> --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}'` piped to `aws s3api delete-objects`, repeated for `DeleteMarkers`), then run `aws s3 rb s3://<name>`.

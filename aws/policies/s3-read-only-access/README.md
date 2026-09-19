# S3 Read-Only Access

**When to use:** A principal only needs to list and download from one bucket.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

Grants a principal read-only access (list + get) to a single bucket, with no write, delete, or ACL permissions.

## Files

| File | Purpose |
|---|---|
| [iam-policy.json](iam-policy.json) | Attach to the IAM user/role that needs read-only access |

## Placeholders

| Placeholder | Replace with |
|---|---|
| `<S3_BUCKET_ARN>` | ARN of the bucket, e.g. `arn:aws:s3:::my-bucket` |

## Notes

- Includes `s3:GetObjectVersion` for versioned buckets — remove if the bucket doesn't use versioning.
- To scope to a prefix instead of the whole bucket, see [s3-scoped-folder-access](../s3-scoped-folder-access/).

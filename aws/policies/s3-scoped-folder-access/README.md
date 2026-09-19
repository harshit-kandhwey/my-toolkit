# S3 Scoped Folder Access

**When to use:** You want a user/team to see only one prefix of a shared bucket.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

IAM policy that limits a principal to listing and operating within a single top-level "folder" (key prefix) of a bucket, rather than granting bucket-wide access. Useful for multi-tenant buckets where each user/team should only see their own prefix.

## Files

| File | Purpose |
|---|---|
| [iam-policy.json](iam-policy.json) | Attach to the IAM user/role that should be scoped to one folder |

## How it works

S3 has no native folder concept — `ListBucket` always operates on the whole bucket unless scoped with a `Condition`. This policy uses four statements to reconstruct folder-like isolation:

1. **ListAllBucketsStatement** — lets the principal see the bucket exists in the console (`s3:ListAllMyBuckets`, `s3:GetBucketLocation`).
2. **ListFoldersInBucketStatement** — allows listing only the `<FOLDER>/` prefix with delimiter `/`. The root of the bucket is deliberately not listable, so other teams' folder names are not exposed. Consequence: in the console the user must open `<FOLDER>/` directly (paste the path or use the AWS CLI); they cannot browse down from the bucket root.
3. **ListContentInFolderStatement** — allows listing objects within the target folder specifically.
4. **AllowPermissionsOfFolderStatement** — grants full object-level access (`s3:*`) scoped to `<FOLDER_ARN>/*`.

## Placeholders

| Placeholder | Replace with |
|---|---|
| `<S3_BUCKET_ARN>` | ARN of the bucket, e.g. `arn:aws:s3:::my-bucket` |
| `<FOLDER>` | Folder/prefix name, e.g. `team-a` |
| `<FOLDER_ARN>` | `<S3_BUCKET_ARN>/<FOLDER>`, e.g. `arn:aws:s3:::my-bucket/team-a` |

## Notes

- `AllowPermissionsOfFolderStatement` grants `s3:*` on the folder — narrow this to specific actions (e.g. `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`) if full object management isn't required.

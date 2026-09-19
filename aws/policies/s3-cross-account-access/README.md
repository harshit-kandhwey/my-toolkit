# S3 Cross-Account Access

**When to use:** You need another AWS account to upload to (write) and list one of your buckets. This pattern does not grant reads.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

Grants a user in **Account B** write/list access to a bucket owned by **Account A**, using a pair of policies: an IAM policy attached to the Account B user/role, and a bucket policy attached to the Account A bucket.

## Files

| File | Attach to | Purpose |
|---|---|---|
| [iam-policy.json](iam-policy.json) | IAM user/role in Account B | Grants the consuming account permission to act on the bucket |
| [bucket-policy.json](bucket-policy.json) | S3 bucket in Account A | Delegates access on the bucket to the specific principal in Account B |

Both policies are required — the bucket owner must delegate access via the bucket policy, and the consuming account must separately grant its own principal permission via IAM.

## Placeholders

| Placeholder | Replace with |
|---|---|
| `<S3_BUCKET_ARN>` | ARN of the bucket being shared, e.g. `arn:aws:s3:::my-shared-bucket` |
| `<IAM_USER_ARN>` | ARN of the Account B principal being granted access |

## Notes

- Actions are `s3:ListBucket` (bucket level) and `s3:PutObject`/`s3:PutObjectAcl` (object level). Add `s3:GetObject` to both policies if the other account also needs to read.
- Writes are only allowed when the request carries `x-amz-acl: bucket-owner-full-control` (for the CLI: `aws s3 cp file s3://bucket/ --acl bucket-owner-full-control`), so the owning account keeps control of uploaded objects and the writer cannot set any other ACL.
- Simplest alternative: set the bucket's Object Ownership to **Bucket owner enforced** (ACLs disabled). Objects are then always owned by the bucket owner, and you can drop `s3:PutObjectAcl` and the condition.

#!/usr/bin/env bash
# Requires GNU date and bash: run in WSL or AWS CloudShell (not native Windows / macOS).
# List S3 buckets that may be publicly accessible: bucket policy status is
# public, a public ACL grant exists, or neither the bucket nor the account
# fully blocks public access.
#
# A check that fails (for example missing s3:GetBucketPolicyStatus) is reported as an
# audit-error row, never treated as private.
#
# Usage: ./audit-public-s3-buckets.sh

set -euo pipefail

command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

all_blocked='(.BlockPublicAcls // false) and (.BlockPublicPolicy // false) and (.IgnorePublicAcls // false) and (.RestrictPublicBuckets // false)'

echo "Bucket,Reason"

# Run an aws command; on success print its output. A missing-configuration error
# (bucket has no policy / no public access block) prints $2; any other error
# is reported as an audit-error row so a failed check is never read as "private".
check() {
  local bucket="$1" missing_code="$2" fallback="$3"
  shift 3
  local out
  if out=$("$@" 2>&1); then
    printf '%s' "$out"
  elif [[ "$out" == *"$missing_code"* ]]; then
    printf '%s' "$fallback"
  else
    echo "${bucket},audit-error: ${out//$'
'/ }" >&2
    return 1
  fi
}

account_id=$(aws sts get-caller-identity --query Account --output text)
if account_pab=$(check "account:${account_id}" NoSuchPublicAccessBlockConfiguration '{}' \
    aws s3control get-public-access-block --account-id "$account_id" \
    --query 'PublicAccessBlockConfiguration' --output json); then
  account_blocked=$(echo "$account_pab" | jq -r "$all_blocked")
else
  echo "account:${account_id},audit-error"
  account_blocked=unknown # do not flag buckets for account-level protection we could not read
fi

for bucket in $(aws s3api list-buckets --query 'Buckets[].Name' --output text); do
  if bucket_pab=$(check "$bucket" NoSuchPublicAccessBlockConfiguration '{}'       aws s3api get-public-access-block --bucket "$bucket"       --query 'PublicAccessBlockConfiguration' --output json); then
    bucket_blocked=$(echo "$bucket_pab" | jq -r "$all_blocked")
    if [ "$account_blocked" = "false" ] && [ "$bucket_blocked" != "true" ]; then
      echo "${bucket},public-access-block-not-fully-enabled"
    fi
  else
    echo "${bucket},audit-error"
  fi

  if policy_public=$(check "$bucket" NoSuchBucketPolicy False       aws s3api get-bucket-policy-status --bucket "$bucket"       --query 'PolicyStatus.IsPublic' --output text); then
    [ "$policy_public" = "True" ] && echo "${bucket},public-bucket-policy"
  else
    echo "${bucket},audit-error"
  fi

  if acl=$(check "$bucket" NEVER_MATCHES '' aws s3api get-bucket-acl --bucket "$bucket" --output json); then
    public_acl=$(echo "$acl" | jq -r '
      [.Grants[]?.Grantee.URI? // empty] |
      any(. == "http://acs.amazonaws.com/groups/global/AllUsers" or
          . == "http://acs.amazonaws.com/groups/global/AuthenticatedUsers")
    ')
    [ "$public_acl" = "true" ] && echo "${bucket},public-acl-grant"
  else
    echo "${bucket},audit-error"
  fi
done

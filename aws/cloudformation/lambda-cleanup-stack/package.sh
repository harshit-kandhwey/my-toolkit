#!/usr/bin/env bash
# Zips the three Lambda functions and uploads them to the code bucket.
# Usage: ./package.sh <code-bucket> [profile]
set -euo pipefail

bucket="${1:?usage: package.sh <code-bucket> [profile]}"
profile_args=()
[[ -n "${2:-}" ]] && profile_args=(--profile "$2")

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../lambda-functions" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for fn in resource-cleanup resource-protect resource-inventory cost-report; do
  (cd "$root/$fn" && zip -q -j "$tmp/$fn.zip" lambda_function.py)
  aws s3 cp ${profile_args[@]+"${profile_args[@]}"} "$tmp/$fn.zip" "s3://$bucket/$fn.zip"
done

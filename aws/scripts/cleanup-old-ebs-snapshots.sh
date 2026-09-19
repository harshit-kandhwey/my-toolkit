#!/usr/bin/env bash
# Requires GNU date and bash: run in WSL or AWS CloudShell (not native Windows / macOS).
# Delete self-owned EBS snapshots older than a given age, skipping any
# snapshot still referenced by an AMI. Dry-run by default — pass --apply
# to actually delete.
#
# Usage: ./cleanup-old-ebs-snapshots.sh [age-days] [--apply]
#   age-days: default 90
#   --apply:  actually delete (default is dry-run, prints what would be deleted)

set -euo pipefail

command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

AGE_DAYS=90
APPLY=false

for arg in "$@"; do
  if [ "$arg" = "--apply" ]; then
    APPLY=true
  else
    AGE_DAYS="$arg"
    [[ "$AGE_DAYS" =~ ^[0-9]+$ ]] || { echo "age-days must be a whole number" >&2; exit 1; }
  fi
done

CUTOFF_EPOCH=$(( $(date -u +%s) - AGE_DAYS * 86400 ))

echo "Mode: $([ "$APPLY" = true ] && echo APPLY || echo DRY-RUN) | Age threshold: ${AGE_DAYS} days" >&2
echo "SnapshotId,StartTime,Action"

# Snapshots backing an AMI in the current region must not be deleted.
# (AMIs in other regions or other accounts are not checked.)
amis_in_use=$(aws ec2 describe-images --owners self \
  --query 'Images[].BlockDeviceMappings[].Ebs.SnapshotId' --output text)

snapshots=$(aws ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[].[SnapshotId,StartTime]' --output json)

failure_log=$(mktemp)
trap 'rm -f "$failure_log"' EXIT

echo "$snapshots" | jq -c '.[]' | while read -r row; do
  snapshot_id=$(echo "$row" | jq -r '.[0]')
  start_time=$(echo "$row" | jq -r '.[1]')
  start_epoch=$(date -u -d "$start_time" +%s)

  if [ "$start_epoch" -ge "$CUTOFF_EPOCH" ]; then
    continue
  fi

  if grep -qw "$snapshot_id" <<<"$amis_in_use"; then
    echo "${snapshot_id},${start_time},skipped-in-use-by-ami"
    continue
  fi

  if [ "$APPLY" = true ]; then
    if aws ec2 delete-snapshot --snapshot-id "$snapshot_id" 2>/dev/null; then
      echo "${snapshot_id},${start_time},deleted"
    else
      echo "${snapshot_id},${start_time},delete-failed"
      echo 1 >>"$failure_log"
    fi
  else
    echo "${snapshot_id},${start_time},would-delete"
  fi
done

if [ -s "$failure_log" ]; then
  echo "$(wc -l <"$failure_log") snapshot deletion(s) failed" >&2
  exit 1
fi

#!/usr/bin/env bash
# Requires GNU date and bash: run in WSL or AWS CloudShell (not native Windows / macOS).
# List IAM roles that have not been used (per IAM's role last-used data)
# within the given number of days, or have never been used at all.
#
# Usage: ./audit-unused-iam-roles.sh [days-threshold]
#   days-threshold: default 90

set -euo pipefail

command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

DAYS_THRESHOLD="${1:-90}"
# IAM only tracks role last-used for the trailing 400 days, so a longer threshold
# would report roles as unused that were merely last used before the window.
if ! [[ "$DAYS_THRESHOLD" =~ ^[0-9]+$ ]] || (( DAYS_THRESHOLD > 400 )); then
  echo "days-threshold must be a whole number from 0 through 400" >&2
  exit 1
fi
CUTOFF_EPOCH=$(( $(date -u +%s) - DAYS_THRESHOLD * 86400 ))

echo "RoleName,LastUsed"

aws iam list-roles --query "Roles[?!starts_with(Path,'/aws-service-role/')].RoleName" --output text | tr '\t' '\n' | while read -r role; do
  [ -z "$role" ] && continue

  if ! last_used=$(aws iam get-role --role-name "$role" \
    --query 'Role.RoleLastUsed.LastUsedDate' --output text 2>/dev/null); then
    echo "${role},error-reading-role"
    continue
  fi

  if [ "$last_used" = "None" ] || [ -z "$last_used" ]; then
    echo "${role},not-used-in-tracking-window"
    continue
  fi

  if ! last_used_epoch=$(date -u -d "$last_used" +%s 2>/dev/null); then
    echo "${role},error-parsing-date"
    continue
  fi

  if [ "$last_used_epoch" -lt "$CUTOFF_EPOCH" ]; then
    echo "${role},${last_used}"
  fi
done

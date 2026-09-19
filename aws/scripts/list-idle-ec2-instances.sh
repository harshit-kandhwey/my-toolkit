#!/usr/bin/env bash
# Requires GNU date and bash: run in WSL or AWS CloudShell (not native Windows / macOS).
# List running EC2 instances whose average CPU utilization over the lookback
# window is below the given threshold — candidates for downsizing or stopping.
#
# Usage: ./list-idle-ec2-instances.sh [cpu-threshold-percent] [lookback-days]
#   cpu-threshold-percent: default 5
#   lookback-days: default 7

set -euo pipefail

command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

CPU_THRESHOLD="${1:-5}"
LOOKBACK_DAYS="${2:-7}"
if ! [[ "$CPU_THRESHOLD" =~ ^[0-9]+([.][0-9]+)?$ ]] || ! awk -v t="$CPU_THRESHOLD" 'BEGIN{exit !(t <= 100)}'; then
  echo "cpu-threshold-percent must be a number from 0 through 100" >&2
  exit 1
fi
if ! [[ "$LOOKBACK_DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "lookback-days must be a positive whole number" >&2
  exit 1
fi

START_TIME=$(date -u -d "-${LOOKBACK_DAYS} days" +%Y-%m-%dT%H:%M:%S)
END_TIME=$(date -u +%Y-%m-%dT%H:%M:%S)

echo "InstanceId,Name,AvgCpuPercent"

instance_ids=$(aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].InstanceId' --output text)

for instance_id in $instance_ids; do
  name=$(aws ec2 describe-tags \
    --filters "Name=resource-id,Values=${instance_id}" "Name=key,Values=Name" \
    --query 'Tags[0].Value' --output text 2>/dev/null || echo "-")
  [ "$name" = "None" ] && name="-"

  avg_cpu=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/EC2 \
    --metric-name CPUUtilization \
    --dimensions Name=InstanceId,Value="$instance_id" \
    --start-time "$START_TIME" \
    --end-time "$END_TIME" \
    --period 86400 \
    --statistics Average \
    --query 'Datapoints[].Average' --output json | jq -r 'if length == 0 then "none" else (add / length) end')

  # No datapoints (e.g. just launched): unknown, not idle.
  [ "$avg_cpu" = "none" ] && continue

  below=$(echo "$avg_cpu $CPU_THRESHOLD" | awk '{print ($1 < $2)}')

  if [ "$below" = "1" ]; then
    jq -rn --arg id "$instance_id" --arg name "$name" --argjson cpu "$avg_cpu" '[$id, $name, ($cpu * 100 | round / 100)] | @csv'
  fi
done

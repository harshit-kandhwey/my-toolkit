#!/usr/bin/env bash
# Requires GNU date and bash: run in WSL or AWS CloudShell (not native Windows / macOS).
# Report Standard-storage size and total object count for every bucket, using
# the daily CloudWatch storage metrics (no need to list every object).
# Size counts StandardStorage only: other storage classes are not included.
# A bucket whose location or metrics cannot be read, or that has no datapoint yet, gets
# an ERROR row (details on stderr).
#
# Usage: ./s3-bucket-size-report.sh

set -euo pipefail

command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

END_TIME=$(date -u +%Y-%m-%dT%H:%M:%S)
START_TIME=$(date -u -d "-2 days" +%Y-%m-%dT%H:%M:%S)

echo "Bucket,SizeBytes,ObjectCount"

buckets=$(aws s3api list-buckets --query 'Buckets[].Name' --output text)

# Query one daily metric. Prints the latest value; fails on API errors and when there
# is no datapoint (an empty bucket or a metric not yet published is not proof of size 0).
metric() {
  local region="$1" bucket="$2" name="$3" storage="$4" value
  value=$(aws cloudwatch get-metric-statistics     --region "$region"     --namespace AWS/S3     --metric-name "$name"     --dimensions Name=BucketName,Value="$bucket" Name=StorageType,Value="$storage"     --start-time "$START_TIME" --end-time "$END_TIME"     --period 86400 --statistics Average     --query 'Datapoints | sort_by(@, &Timestamp)[-1].Average' --output text) || return 1
  [ "$value" != "None" ] || return 1
  printf '%s' "$value"
}

for bucket in $buckets; do
  if ! region=$(aws s3api get-bucket-location --bucket "$bucket"       --query 'LocationConstraint' --output text 2>/dev/null); then
    echo "${bucket},ERROR,ERROR" && echo "${bucket}: could not read bucket location" >&2
    continue
  fi
  [ "$region" = "None" ] && region="us-east-1"
  [ "$region" = "EU" ] && region="eu-west-1"

  if size=$(metric "$region" "$bucket" BucketSizeBytes StandardStorage) &&
     count=$(metric "$region" "$bucket" NumberOfObjects AllStorageTypes); then
    printf "%s,%.0f,%.0f
" "$bucket" "$size" "$count"
  else
    echo "${bucket},ERROR,ERROR"
    echo "${bucket}: CloudWatch request failed in ${region}" >&2
  fi
done

# Section 71 (Part 9): Image Retention Policies and Garbage Collection

## 1. Definition

**Plain language:** Registries grow forever unless something removes old images. A *retention policy* decides which tags and manifests are no longer wanted; *garbage collection* (GC) is the separate step that actually frees the disk space held by data nothing references any more.

**Precise definition:** In an OCI registry, a repository holds manifests (referenced by tag or digest) that reference config and layer blobs. Deleting a tag removes only a pointer. Deleting a manifest (`DELETE /v2/<name>/manifests/<digest>`) removes the reference to its blobs. A blob becomes *unreferenced* when no manifest in any repository sharing the blob store points to it, and only GC removes unreferenced blobs. Managed registries (ECR, ACR, Artifact Registry, Docker Hub) perform GC for you as part of their lifecycle or cleanup policies. The self-hosted `registry:2` (CNCF Distribution) and Harbor require you to run it explicitly or on a schedule ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)).

> ⚠️ **Warning:** Retention deletes data permanently. Test policies in dry-run or preview mode and never point experiments at a production registry.

## 2. Why This Matters

- Every CI build pushes a new tag. A 500 MB image built 50 times a day adds up to terabytes in months, and registry storage is billed ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)).
- Deleting tags without GC reclaims nothing, so teams "clean up" and the disk stays full.
- Over-aggressive retention deletes an image a deployment still needs, which breaks rollbacks, autoscaling, and node replacement with `ImagePullBackOff`.
- Old images carry old CVEs; keeping them around lengthens audit scope ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- Compliance may require keeping released images for a fixed period, so retention must be intentional and documented.

## 3. Prerequisites and Dependencies

You need the tag, digest and manifest model from [§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md) and the layer/manifest anatomy from [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md). Registry-specific mechanics build on [§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md) (Hub), [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md) (self-hosted and Harbor) and [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md) (cloud). Multi-arch indexes ([§72](Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)) and signature/SBOM artifacts ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)) add referrer relationships that retention must respect.

## 4. Architecture / Conceptual Diagram

```text
  Retention (policy)                       Garbage collection (storage)
  decides WHAT to unreference              decides WHICH BLOBS to delete

  repo myapp
  tags:  v1.4.2 ─┐                         Mark phase: walk every manifest
         v1.4.1 ─┤► manifest M2 ─► layers  in every repo, mark each referenced
         v1.3.0 ─► manifest M1 ─► layers   blob (config, layers, child manifests)
         (untagged) M0 ─► layers
                                           Sweep phase: delete blobs not marked
  Step 1  retention rule: expire M0 and
          v1.3.0 (older than N / not in    ┌────────┬──────────┬───────────────┐
          the newest K tags)               │ blob   │ marked?  │ action        │
                                           ├────────┼──────────┼───────────────┤
  Step 2  manifests M0, M1 deleted         │ L-base │ yes (M2) │ keep (shared) │
          (references removed)             │ L-old1 │ no       │ delete        │
                                           │ L-old2 │ no       │ delete        │
  Step 3  GC sweeps blobs only M0, M1      └────────┴──────────┴───────────────┘
          referenced; shared L-base stays

  Self-hosted registry:2 GC problem: an upload racing the sweep can leave a manifest
  pointing at a blob that GC just removed. Mitigate: run GC read-only (maintenance mode)
  or use a registry/Harbor version with online GC.
```

- **Shared layers survive:** a blob is deleted only when no manifest anywhere references it.
- **Multi-arch parents:** an index references child manifests; deleting a child while keeping the index breaks that platform, and deleting the index leaves children untagged.
- **Referrers:** signatures, SBOMs and attestations attach to a subject digest; a good policy deletes them together with the subject.

## 5. Hands-On

### 5.1 List Tags and Dates Before Deciding

```bash
# Docker Hub style API, or any registry that supports the Distribution API
curl -s -u "$USER:$TOKEN" https://registry.example.com/v2/team/myapp/tags/list
```

```text
{"name":"team/myapp","tags":["1.3.0","1.4.1","1.4.2","latest"]}
```

The tag-list API gives names only, not ages. Use the registry's own metadata (ECR, ACR, Harbor APIs) or the config blob's `created` field to see age.

### 5.2 Self-Hosted Registry: Enable Deletion

```bash
docker run -d --name registry -p 5000:5000 \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  -v registry-data:/var/lib/registry registry:2
```

Without `storage.delete.enabled`, `DELETE` requests return `405 Method Not Allowed`. The named volume keeps data off the host filesystem root.

### 5.3 Delete a Manifest by Digest, Then Garbage-Collect

```bash
DIGEST=$(curl -sI -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  localhost:5000/v2/myapp/manifests/1.3.0 | awk -F': ' '/Docker-Content-Digest/{print $2}' | tr -d '\r')
curl -X DELETE localhost:5000/v2/myapp/manifests/$DIGEST          # 202 Accepted

# dry run first
docker exec registry registry garbage-collect --dry-run /etc/docker/registry/config.yml
# real run (registry should be read-only or stopped during this)
docker exec registry registry garbage-collect --delete-untagged /etc/docker/registry/config.yml
```

```text
myapp: marking manifest sha256:4c1d...
myapp: marking blob sha256:aa91...
49 blobs marked, 12 blobs and 3 manifests eligible for deletion
blob eligible for deletion: sha256:b7e2...
```

`--delete-untagged` also removes manifests with no tag, which is how superseded builds are reclaimed. The delete call only removes the manifest reference; the blobs vanish at the GC step.

### 5.4 Harbor: Tag Retention Rules and GC Schedule

In the Harbor UI, under a project, open Policy then Tag Retention and add a rule such as "retain the most recently pushed 10 artifacts" with a tag filter like `v*`, plus an exclusion for `release-*`. Run it with Dry Run first. Separately, under Administration then Clean Up, set Garbage Collection to a weekly schedule and enable "delete untagged artifacts". Harbor's GC runs without taking the registry read-only in current releases, but schedule it in a quiet window anyway. Tag *immutability* rules (a different feature) block overwrites and deletes of matching tags and take precedence over retention.

### 5.5 ECR Lifecycle Policy

```json
{
  "rules": [
    { "rulePriority": 1,
      "description": "Expire untagged after 7 days",
      "selection": { "tagStatus": "untagged", "countType": "sinceImagePushed",
                     "countUnit": "days", "countNumber": 7 },
      "action": { "type": "expire" } },
    { "rulePriority": 2,
      "description": "Keep last 30 release images",
      "selection": { "tagStatus": "tagged", "tagPrefixList": ["v"],
                     "countType": "imageCountMoreThan", "countNumber": 30 },
      "action": { "type": "expire" } }
  ]
}
```

```bash
aws ecr put-lifecycle-policy --repository-name team/myapp --lifecycle-policy-text file://policy.json
aws ecr start-lifecycle-policy-preview --repository-name team/myapp --lifecycle-policy-text file://policy.json
aws ecr get-lifecycle-policy-preview --repository-name team/myapp
```

Always run the preview and read the list of images that would expire. ECR rules are evaluated by priority and an image matched by a lower-numbered rule is not reconsidered. There is no separate GC step; ECR frees storage after expiry.

### 5.6 Azure and Google Equivalents

```bash
# Azure ACR: purge old tags (dry run first)
az acr run --registry myreg --cmd \
  "acr purge --filter 'myapp:.*' --ago 30d --keep 10 --untagged --dry-run" /dev/null

# Google Artifact Registry: cleanup policies, with dry run enabled
gcloud artifacts repositories set-cleanup-policies myrepo \
  --location=us-central1 --policy=policy.json --dry-run
```

Both support "older than" and "keep most recent N" conditions. ACR also supports retention of untagged manifests for Premium SKUs; Artifact Registry's `--dry-run` logs what would be deleted before you switch it off.

### 5.7 Local Daemon Cleanup (Different Problem)

```bash
docker image prune                  # dangling images only
docker image prune -a --filter "until=720h"   # unused images older than 30 days
docker builder prune --keep-storage 20GB      # BuildKit cache
docker system df                    # see what occupies space
```

This frees space on a build host or developer machine, not in the registry. Run on CI runners to keep them from filling up, but test any scripted prune in a throwaway environment first.

## 6. Production Usage Notes

- **Protect what is deployed.** Retention must never expire a digest that any cluster, environment or rollback target uses. Typical approach: tag deployed digests with `prod-<date>` or an `in-use` marker and exclude that pattern, or keep the last N releases regardless of age.
- **Layer rules by tag class:** feature-branch and PR tags expire after days; main-branch build tags after weeks; semantic release tags are kept long-term or forever; `latest` and floating tags are exempt because they are pointers.
- **Expire untagged manifests quickly** (days), but not instantly: a multi-arch push or in-flight `buildx` build briefly creates untagged child manifests.
- **Order of operations:** apply retention, then GC. In Harbor and `registry:2` GC is a scheduled job; in managed registries it is automatic.
- **Self-hosted GC safety:** with `registry:2`, run GC in read-only mode (`storage.maintenance.readonly.enabled: true`) or with writers stopped; pushing during the sweep can corrupt references. Back up the storage first. Harbor and recent Distribution versions reduce this risk, but confirm for your version.
- **Storage backends:** S3/GCS/Azure Blob back many registries; enable bucket versioning only if you can afford it, because versioned deleted blobs still bill until lifecycle rules remove them.
- **Cache images in CI:** `--cache-to type=registry` creates cache manifests that need their own short retention rule.
- **Observe:** track repository size, image count and monthly storage cost; alert when growth is outside the norm.
- **Docker Hub:** inactive images in free or personal repositories may be subject to expiry under Docker's retention terms, so verify current policy for anything you rely on ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)).

## 7. Security Considerations

- **Deletion rights are powerful.** Grant delete permission only to registry admins and to the retention job's identity; developers should be push-only.
- **Audit logs:** record who or what deleted manifests (Harbor audit logs, CloudTrail, Azure Activity Log, Cloud Audit Logs).
- **Immutability beats retention conflicts:** use immutability rules on release tags so a misconfigured policy or compromised credential cannot silently remove or replace them.
- **Deleted is not secure.** A secret baked into a layer stays in any machine that pulled it, and in registry backups or bucket versions. Rotate the secret; do not rely on expiry.
- **Keep SBOMs and signatures aligned** with their subject image so audits can still verify what ran in the past ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Supply-chain angle:** stale, unmaintained images with known CVEs are a liability; expiring them reduces accidental redeployment.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Registry disk still full after deleting tags | Only pointers removed; GC not run | Run GC (`registry garbage-collect`, Harbor GC) |
| `DELETE` returns `405 Method Not Allowed` | Deletion disabled in `registry:2` | Set `REGISTRY_STORAGE_DELETE_ENABLED=true` |
| `DELETE` returns `404` for a tag | Must delete by digest, not tag | Resolve digest from `Docker-Content-Digest` header |
| `manifest unknown` right after GC | Image pushed during GC, blob swept | Restore from backup, re-push; use read-only mode in future |
| `ImagePullBackOff` after a retention run | Policy expired an in-use image | Rebuild or restore from replica; add an exemption rule |
| Multi-arch image missing one platform | Child manifest deleted while index remained | Re-push the index; exclude child digests from untagged expiry |
| Retention deleted nothing | Rule order, tag filter mismatch, or immutability blocking | Use dry-run or preview and check priorities |
| Storage bill unchanged after cleanup | Bucket versioning keeps deleted blobs | Add a bucket lifecycle rule for noncurrent versions |
| Harbor GC job fails or hangs | Job queue or database issue, running concurrently with replication | Check job logs, reschedule outside replication windows |
| Signature artifacts orphaned | Subject deleted, referrers left behind | Delete referrers with the subject, or enable cascade cleanup |

## 9. Best Practices

- Write retention rules by tag class (PR, branch, release, deployed) and document them with the reason and owner.
- Always dry-run or preview, review the list, then enable.
- Exempt anything deployed or designated as a rollback target; automate the exemption from your deployment record.
- Pair every retention policy with GC, and schedule both.
- Use immutability on release tags and least-privilege delete rights.
- Expire untagged manifests after a short grace period, not immediately.
- Back up self-hosted registry storage before the first GC and test the restore.
- Monitor storage growth and alert on anomalies.
- Prune CI runners and build caches separately from the registry.

## 10. Common Anti-Patterns / Mistakes

- Expiring "everything older than 30 days" with no exemption for long-running production images.
- Deleting tags manually in a UI and assuming space is returned.
- Running `registry garbage-collect` against a registry that is accepting pushes.
- Running GC without `--dry-run` first on a registry without a backup.
- Counting `latest` toward a "keep last N" rule so real releases are expired early.
- Treating `docker system prune -a` on shared build hosts as a registry strategy.
- Deleting individual child manifests of a multi-arch index by hand.
- No policy at all, discovering the problem when the bill or the disk alarm arrives.

## 11. Interview Questions

**🎯 Beginner:** _"You deleted 200 old tags from a self-hosted registry but disk usage did not change. Why?"_
**Model answer:** Deleting a tag only removes a pointer, and even deleting the manifest only removes the reference to the layer blobs. The blobs stay on disk until garbage collection runs, which marks every blob still referenced by any manifest and deletes the rest. In `registry:2` you must enable deletion and run `registry garbage-collect` (with `--delete-untagged` to include untagged manifests), ideally after a `--dry-run`. Managed registries do this automatically after expiry.
_What the interviewer is probing for:_ Separation of reference removal from storage reclamation.

**🎯 Intermediate:** _"How would you design retention rules for a repository that receives builds from feature branches, main, and release tags?"_
**Model answer:** Classify tags by pattern and give each class its own rule. Branch and PR images expire after a few days, main-branch build tags after a few weeks or after the newest N, and semantic release tags are kept for the compliance period or indefinitely. Untagged manifests expire after a short grace window to avoid racing in-flight multi-arch pushes. Anything currently deployed is exempt by marker tag or a deployed-digest list. I would preview the rules first (ECR preview, Harbor dry run, ACR `--dry-run`) and enable release-tag immutability so retention cannot touch them.
_What the interviewer is probing for:_ Practical rule design, protecting deployed images, and use of dry-run.

**🎯 Senior:** _"After a nightly cleanup, a Kubernetes node autoscaled and half the pods hit ImagePullBackOff with `manifest unknown`. Walk through root cause and prevention."_
**Model answer:** A new node has an empty image cache, so it must pull from the registry; the digest or tag referenced by the Deployment was expired by the retention rule, perhaps because it was an older release still running, or because the rule counted by age without regard to use. I would confirm via registry audit logs which job deleted the manifest and when, then restore from a replica, backup, or by rebuilding from the git SHA noted in the OCI labels. Prevention: derive an exemption list from what clusters actually run (admission webhook or deployment records), keep the last N releases regardless of age, use immutability on release tags, replicate production images to a second registry, and make the retention job preview its deletions into a review step before enforcement.
_What the interviewer is probing for:_ Incident reasoning linking retention to runtime pulls, and layered safeguards.

**🎯 Architect:** _"Design the image lifecycle and storage-cost strategy for a platform serving 300 repositories on a self-hosted Harbor plus a cloud registry."_
**Model answer:** Define lifecycle tiers centrally as code (Terraform or Harbor API) so every project inherits default rules: short for ephemeral builds, medium for main, long for releases, with deployed-image protection fed from the GitOps source of truth. Production artifacts replicate to the cloud registry for availability, with its own lifecycle policy. Harbor GC runs on a schedule with database and storage backups, in a maintenance window away from replication jobs, using object storage with lifecycle rules on noncurrent versions. Signatures and SBOMs share their subject's retention. Governance includes quotas per project, dashboards for storage per team, chargeback, audit logging for deletes, and a quarterly review of rules against compliance retention requirements. Failure handling covers restore drills and an expiry "soft delete" period where feasible.
_What the interviewer is probing for:_ Policy as code, safety nets, multi-registry coordination, and cost governance.

## 12. Common Misconceptions

- "Deleting a tag frees the space." Space is freed only after the manifest is gone and GC removes unreferenced blobs.
- "Retention and garbage collection are the same thing." Retention decides what to unreference; GC reclaims storage.
- "Layers belong to one image." They are shared; a blob lives until the last manifest referencing it is gone.
- "`docker image prune` cleans the registry." It only affects the local daemon.
- "Cloud registries need a GC job." They run it automatically; you manage policies, not sweeps.
- "Expiry makes leaked secrets safe." Copies persist in caches, backups and pulled nodes.

## 13. 🔑 Key Takeaways

- Retention removes references; GC reclaims blobs. You need both.
- Always preview or dry-run, and always exempt deployed digests.
- Classify tags (PR, branch, release, deployed) and set a rule per class.
- Self-hosted GC needs read-only mode or a quiet window and a backup.
- Use immutability and least-privilege delete rights to protect releases.
- Keep multi-arch children and signatures consistent with their parents and subjects.

## 14. Related Concepts & What's Next

Related: tagging and promotion ([§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), self-hosted registry and Harbor ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)), cloud registry lifecycle features ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)), image layers ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), signing and SBOMs ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Next, [§72](Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md) covers multi-architecture images, where a single tag points to an index of per-platform manifests that retention and GC must treat as a unit.

**Next Section:** [§72](Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md) — `Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md`

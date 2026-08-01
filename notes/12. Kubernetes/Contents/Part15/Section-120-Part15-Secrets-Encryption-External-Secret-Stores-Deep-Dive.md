# Section 120 (Part 15): Secrets Encryption and External Secret Stores Deep Dive

## 1. Definition

**Plain language:** §42 (Part 6) established that a native Kubernetes Secret is only base64-encoded, and §80 (Part 10) covered the external tooling — Vault, External Secrets Operator, Sealed Secrets — that layers centralized management, dynamic rotation, and safe GitOps storage on top of that native object. Both of those sections, however, largely treated "Secret exists as an object" as the endpoint. This section goes one layer deeper, into the exact mechanics of what actually protects a Secret's content once it's written to etcd — `EncryptionConfiguration`, envelope encryption, KMS provider integration, and the specific CKS-exam-relevant question of what happens to already-encrypted data when a key is rotated or an encryption provider is changed.

**Precise definition:** **Encryption at rest** for Kubernetes Secrets is configured via an `EncryptionConfiguration` resource passed to `kube-apiserver` at startup, defining an ordered list of **providers** for each resource type (typically `secrets`) — `identity` (no encryption, plaintext), `aescbc`/`aesgcm` (a locally-held symmetric key baked into the config file itself), or `kms` (a **KMS provider** plugin, communicating over a Unix domain socket with an external key management service such as AWS KMS, Azure Key Vault, GCP Cloud KMS, or HashiCorp Vault's Transit engine). The **KMS v2** provider (the modern, CKS-relevant approach) uses **envelope encryption**: the API server generates a random Data Encryption Key (DEK) per resource, encrypts the actual Secret content with that DEK locally, and only sends the DEK itself — not the Secret data — to the external KMS to be wrapped by a Key Encryption Key (KEK) that never leaves the KMS. This means the highly sensitive Secret payload never crosses the network to the external KMS at all; only the small, per-object DEK does, and the KMS never has to be trusted with (or capable of leaking) the actual plaintext Secret content in transit.

## 2. Why This Matters

- **`EncryptionConfiguration` is a named, explicit CKS domain item under Minimizing Microservice Vulnerabilities, and it is trivially easy to configure incorrectly** — a provider list with `identity` listed _before_ `aescbc` or `kms` results in new writes being stored as plaintext even though the configuration file appears, at a glance, to enable encryption; provider _order_ is the encryption policy, not merely its presence in the list.
- **Enabling `EncryptionConfiguration` does not retroactively encrypt Secrets already sitting in etcd** — every existing Secret object remains in whatever state it was written in until it is rewritten, meaning a cluster that just enabled encryption still has plaintext-at-rest Secrets from before that change until an explicit re-encryption pass runs.
- **KMS v2's envelope-encryption design is the specific reason the actual Secret payload never needs to be sent to (or trusted to) the external key management service** — only the small DEK is; this is a frequently tested distinction between "the KMS holds your secrets" (false) and "the KMS wraps the key that encrypted your secrets" (true, and much smaller attack surface).

🔑 **Key Takeaway:** Encryption at rest is governed entirely by `EncryptionConfiguration`'s provider list, ordered from most-preferred to least-preferred; KMS v2's envelope encryption keeps the actual Secret content out of the external KMS entirely by only ever sending it the small, per-object Data Encryption Key; and enabling encryption is not retroactive — existing Secrets require an explicit re-encryption pass (typically a no-op `kubectl replace` or a dedicated storage migration) to actually be rewritten under the new scheme.

## 3. Prerequisites and Dependencies

Builds on §119 (mTLS and service mesh security — protecting data in transit between workloads) as the complementary boundary this section's encryption-at-rest and external-secret-store coverage addresses for data at rest and in use, and back-references §42 (Secrets, Part 6, the native object this section deep-dives) and §80 (Secrets Management Integration, Part 10 — this section goes considerably deeper than that Part's introductory coverage of Vault, External Secrets Operator, and Sealed Secrets, focusing here specifically on encryption-at-rest mechanics, KMS provider internals, and re-encryption/rotation procedures those sections didn't cover mechanically). Assumes familiarity with etcd's role as the cluster's data store (§10, Part 2) and RBAC (§75, Part 10). Forward-references §121, this Part's capstone.

## 4. Architecture Diagram

```text
        WITHOUT EncryptionConfiguration (identity provider, default):

  kubectl create secret ──► kube-apiserver ──► etcd stores base64(value) as-is
                                                  (readable by anyone with etcd access
                                                   or an etcd backup/snapshot, §108)

        WITH KMS v2 envelope encryption:

  ┌────────────────────────────────────────────────────────────────────────┐
  │ kube-apiserver                                                         │
  │                                                                        │
  │  1. Secret write request arrives                                       │
  │  2. Generate a random Data Encryption Key (DEK), locally               │
  │  3. Encrypt the Secret's actual content with the DEK, locally          │
  │  4. Send ONLY the small DEK to the KMS plugin over a Unix socket       │
  │           │                                                            │
  │           ▼                                                            │
  │  ┌──────────────────────────┐                                          │
  │  │ KMS provider plugin      │                                          │
  │  │  (talks to external KMS: │                                          │
  │  │   AWS KMS / Azure KV /   │                                          │
  │  │   GCP Cloud KMS / Vault) │                                          │
  │  └──────────────────────────┘                                          │
  │           │  KMS wraps the DEK with its own Key Encryption Key (KEK)   │
  │           │  KEK NEVER leaves the external KMS                         │
  │           ▼                                                            │
  │  5. Store: {encrypted Secret content} + {wrapped DEK} in etcd          │
  └────────────────────────────────────────────────────────────────────────┘

  Result in etcd: ciphertext + a wrapped DEK — NOT the plaintext Secret,
  and the external KMS itself never received the Secret's actual content,
  only the small DEK it was asked to wrap.
```

- **The Secret's actual content never leaves the API server's own process boundary in plaintext form** — only the small DEK is sent externally, and only in already-generated (not plaintext-derivable) form once the KMS wraps it, which is the specific design property that limits the external KMS's exposure to a compromise.
- **A compromise of etcd alone (a stolen snapshot, §108, or a database file lifted from disk) yields only ciphertext plus a wrapped DEK** — decrypting it requires also compromising the external KMS's ability to unwrap that specific DEK, meaningfully raising the bar over the identity (no encryption) or even a locally-held `aescbc` key baked directly into a config file sitting on the same control-plane node as etcd.
- **The provider list order in `EncryptionConfiguration` determines behavior for both reads and writes** — the first provider in the list is used for all new writes; on read, the API server tries each provider in order until one successfully decrypts, which is exactly the mechanism that allows a phased migration between providers (e.g., introducing KMS while old `aescbc`-encrypted Secrets still exist) without breaking existing data.

## 5. Hands-On

### 5.1 Configuring EncryptionConfiguration with a KMS v2 Provider

**Purpose:** Enable envelope encryption for Secrets using a KMS v2 provider, so new Secret writes are encrypted with a per-object DEK wrapped by an external KMS.

**Syntax:**

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - kms:
          apiVersion: v2
          name: aws-kms-provider
          endpoint: unix:///var/run/kmsplugin/socket.sock
          timeout: 3s
      - identity: {}
```

```bash
# on each control-plane node, referenced by kube-apiserver's --encryption-provider-config flag:
kube-apiserver \
  --encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml \
  ...
```

**Example usage:**

```bash
$ kubectl create secret generic db-password --from-literal=password=hunter2
secret/db-password created

$ ETCDCTL_API=3 etcdctl get /registry/secrets/default/db-password | xxd | head -3
# output shows opaque ciphertext, NOT a recognizable base64-decodable plaintext value
00000000  2f 72 65 67 69 73 74 72  79 2f 73 65 63 72 65 74  |/registry/secret|
00000010  6b 38 73 3a 65 6e 63 3a  61 65 73 63 62 63 3a 76  |k8s:enc:kms:v2:a|
```

**Production usage example:** The `identity: {}` entry listed _after_ the `kms` provider is deliberately kept as a fallback for reads only — it lets the API server still decrypt any Secret that predates the encryption rollout (which was stored via `identity`, i.e., plaintext) while ensuring every _new_ write goes through the `kms` provider listed first; removing `identity` entirely before a full re-encryption pass would make pre-existing plaintext Secrets undecryptable-by-design (the API server would refuse to serve them since no provider in the list can "decrypt" already-plaintext data), which is a subtle but real production gotcha.

**Common errors:** Listing `identity` _before_ `kms` in the providers list — since the first provider is always used for new writes, this silently disables encryption for all new Secrets while the config file superficially looks like encryption is enabled; this exact ordering mistake is a well-known CKS exam trap.

### 5.2 Re-Encrypting Existing Secrets After Enabling Encryption

**Purpose:** Force every existing Secret (written before `EncryptionConfiguration` was applied, and therefore still in whatever provider state it was originally stored under) to be rewritten under the new, current first-listed provider.

**Syntax:**

```bash
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
```

**Example usage:**

```bash
$ ETCDCTL_API=3 etcdctl get /registry/secrets/default/legacy-secret | head -c 40
# before: readable, unencrypted content (this Secret predates EncryptionConfiguration)

$ kubectl get secret legacy-secret -o json | kubectl replace -f -
secret/legacy-secret replaced

$ ETCDCTL_API=3 etcdctl get /registry/secrets/default/legacy-secret | head -c 40
# after: opaque ciphertext — this Secret has now been rewritten under the current
# first-listed provider (the KMS v2 provider from 5.1)
```

**Production usage example:** In a production cluster with a large existing Secret population, this replace-all pattern is typically run as a one-time migration job immediately after `EncryptionConfiguration` is first applied or its provider order changes — running it against `--all-namespaces` ensures no Secret is silently left behind in its old encryption state, since Kubernetes itself never automatically re-encrypts data at rest on its own initiative.

**Common errors:** Assuming that applying `EncryptionConfiguration` alone protects data that already existed in etcd before the change — it does not; every pre-existing object remains stored exactly as it was until something (this replace pass, or any other update to that object) triggers a rewrite through the now-current provider chain.

## 6. Production Usage Notes

- **KMS v2 is the modern, CKS-relevant approach and materially improves on KMS v1's design**, which required a full round-trip to the external KMS for every Secret read (a latency and availability dependency); KMS v2's envelope encryption caches and reuses DEKs more efficiently and reduces that per-read dependency, though the exact mechanics are a KMS-provider implementation detail worth confirming for the specific cloud provider in use.
- **Key rotation at the external KMS (KEK rotation) does not require re-encrypting every Secret in etcd** — only the wrapped DEKs need to be re-wrapped under the new KEK, a materially cheaper operation than a full Secret-content re-encryption pass, and this distinction (KEK rotation vs. DEK rotation vs. full Secret re-encryption) is a common area of confusion worth being precise about.
- **`EncryptionConfiguration` applies per resource type, not globally** — a cluster can (and often should) encrypt `secrets` while leaving less-sensitive resource types on the `identity` provider, since encryption/decryption is not free and applying it indiscriminately to every resource type adds unnecessary API server overhead.

## 7. Security Considerations

- **`EncryptionConfiguration` protects data at rest in etcd specifically — it does nothing for a Secret's exposure once read through the Kubernetes API** — anyone with sufficient RBAC (§75) `get`/`list` access to Secrets in a namespace still receives the plaintext value; encryption at rest and RBAC are independent boundaries, exactly as §80 already noted for external secrets tooling.
- **A locally-held `aescbc` key baked directly into the `EncryptionConfiguration` file is a materially weaker posture than a KMS provider** — that key sits on the same control-plane node's disk as the config file itself, meaning anyone who can read the file (or a backup of it) can decrypt every Secret; a KMS provider keeps the actual unwrapping capability external to the cluster entirely.
- **The `EncryptionConfiguration` file itself, and any locally-held keys within it, deserve the same backup, access-control, and rotation discipline as any other cluster root-of-trust material** — a lost or leaked local key is equivalent to losing the confidentiality guarantee for every Secret encrypted under it.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                   | Cause                                                                                                          | Fix                                                                                                   |
| ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| New Secrets are still stored as plaintext despite `EncryptionConfiguration` being applied | `identity` provider is listed before `kms`/`aescbc` in the providers list                                      | Reorder providers so the encrypting provider (`kms` or `aescbc`) is listed first                      |
| Existing Secrets remain readable in plaintext from etcd after enabling encryption         | Encryption is not retroactive; pre-existing objects were never rewritten                                       | Run a `kubectl get secrets --all-namespaces -o json \| kubectl replace -f -` re-encryption pass       |
| `kube-apiserver` fails to start after adding a `kms` provider entry                       | KMS plugin socket isn't reachable at the configured `endpoint`, or the plugin process isn't running yet        | Confirm the KMS provider plugin is deployed and its Unix socket path matches the config exactly       |
| A Secret written before a KEK rotation suddenly fails to decrypt                          | The KMS's wrapped-DEK metadata references a KEK version that was deleted rather than rotated-with-history kept | Never delete an old KEK version until confirming every wrapped DEK referencing it has been re-wrapped |

## 9. Best Practices

- Always place the intended encrypting provider (`kms` v2 preferred, `aescbc` as a fallback) first in the `EncryptionConfiguration` providers list, with `identity` last and used only as a read-compatibility fallback during migration.
- Run an explicit re-encryption pass immediately after enabling or changing `EncryptionConfiguration`, since Kubernetes never does this automatically.
- Prefer a KMS v2 provider over a locally-held `aescbc` key for any production cluster, since the KMS keeps the actual unwrapping key outside the cluster's own disk entirely.
- Treat KEK rotation and full Secret re-encryption as two separate operations with two different costs, and understand which one a given key-management event actually requires.
- Pair encryption at rest with RBAC discipline (§75) and mTLS (§119) — encryption-at-rest addresses only the etcd-storage exposure surface, not API-level read access or in-transit interception.

## 10. Common Anti-Patterns / Mistakes

- **Listing `identity` before the encrypting provider in `EncryptionConfiguration`**, silently leaving new Secrets unencrypted despite an apparently-correct configuration file.
- **Assuming enabling `EncryptionConfiguration` retroactively encrypts existing Secrets**, leaving a population of still-plaintext objects in etcd indefinitely.
- **Treating encryption at rest as a substitute for RBAC discipline**, when anyone with sufficient API-level read access still receives plaintext regardless of etcd-storage encryption.
- **Deleting an old KEK version immediately after rotating to a new one**, before confirming every DEK wrapped under the old KEK has actually been re-wrapped, permanently bricking any Secret still referencing it.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a Secret being base64-encoded and a Secret being encrypted at rest?"_
**Model answer:** Base64 encoding, which is what a native Kubernetes Secret's `data` field uses by default, is not encryption at all — it's a reversible text encoding anyone can decode with a single command, offering no confidentiality whatsoever. Encryption at rest is a separate, explicitly configured mechanism (`EncryptionConfiguration` on the API server) that actually encrypts the Secret's content before it's written to etcd, so that anyone with access to etcd's storage directly, or a backup/snapshot of it, sees only ciphertext rather than a trivially decodable value.
_What the interviewer is probing for:_ Correctly distinguishing encoding from encryption, a foundational and frequently-tested distinction.

**🎯 Intermediate:** _"You enable `EncryptionConfiguration` with a KMS provider on a cluster that already has hundreds of existing Secrets. Are those existing Secrets now encrypted?"_
**Model answer:** No — enabling `EncryptionConfiguration` only changes how _new_ writes are handled going forward; it has no retroactive effect on objects already stored in etcd. Every one of those hundreds of existing Secrets remains in whatever state it was originally written in (typically plaintext, under the default `identity` provider) until something actually rewrites that specific object. The standard way to force this is running `kubectl get secrets --all-namespaces -o json | kubectl replace -f -`, which reads and rewrites every Secret, causing each one to pass through the API server's current encryption provider chain and come out the other side actually encrypted.
_What the interviewer is probing for:_ Awareness that encryption configuration changes are not retroactive, and knowledge of the concrete re-encryption remediation step.

**🎯 Senior:** _"Explain why KMS v2's envelope encryption is considered more secure than sending the Secret's actual content directly to an external KMS for encryption."_
**Model answer:** With envelope encryption, the API server generates a random Data Encryption Key locally and uses it to encrypt the Secret's actual content entirely within its own process — the plaintext Secret value never leaves the API server. Only the small DEK itself is sent to the external KMS, which wraps it with a Key Encryption Key that never leaves the KMS's own boundary, and the wrapped DEK is stored alongside the encrypted Secret content in etcd. This design means the external KMS never sees, handles, or is capable of leaking the actual Secret payload at all — its exposure surface is limited to a small, randomly generated key rather than the sensitive data itself. If you instead sent the Secret's actual content to the KMS directly for encryption, every Secret's plaintext would cross the network to that external system and be handled by it directly, a materially larger trust and exposure surface, plus a latency and availability dependency on that external round-trip for every single write.
_What the interviewer is probing for:_ Precise understanding of the DEK/KEK split in envelope encryption and why it minimizes the external KMS's exposure to the actual sensitive payload.

**🎯 Architect:** _"Design the encryption-at-rest and key-management strategy for a regulated financial-services platform running Kubernetes across multiple regions, where you must support key rotation without downtime and prove auditability for compliance."_
**Model answer:** I'd mandate a KMS v2 provider backed by each region's cloud-native KMS (or a centrally managed HashiCorp Vault Transit engine for a cloud-agnostic posture) as the only acceptable `EncryptionConfiguration` provider for the `secrets` resource type — no locally-held `aescbc` keys in any production cluster, since those keys sitting on control-plane node disks are a materially weaker and harder-to-audit posture than an external KMS's centrally logged key operations. For key rotation, I'd establish two distinct, separately scheduled operations: KEK rotation at the external KMS on a defined cadence (cheap — only wrapped DEKs need re-wrapping, not full Secret content) and a periodic full re-encryption pass (the `kubectl replace` pattern) run as a scheduled, audited job to guarantee no Secret silently remains encrypted under a deprecated scheme indefinitely. I'd never delete an old KEK version until an explicit verification step confirms zero remaining wrapped DEKs reference it. For auditability, every KMS operation (key use, rotation, access) is already logged by the external KMS itself, and I'd feed that log stream into the same centralized audit pipeline (§96, Part 12) capturing Kubernetes API audit logs, giving compliance a single, correlated timeline of both API-level Secret access (gated by RBAC, §75) and key-management-level operations. Finally, I'd layer this alongside mTLS (§119) for in-transit protection and RBAC for API-level read gating, since encryption at rest addresses one specific exposure surface — etcd storage and backups — and is not a substitute for those other two boundaries.
_What the interviewer is probing for:_ Ability to design a coherent, auditable, multi-region key-management strategy that correctly distinguishes KEK rotation from full re-encryption, mandates external KMS over locally-held keys for compliance-grade auditability, and layers correctly with RBAC and mTLS rather than treating encryption at rest as a complete solution.

## 12. Common Misconceptions

1. **"Base64 encoding and encryption at rest are the same protection."** Base64 is a trivially reversible encoding with zero confidentiality; encryption at rest, via `EncryptionConfiguration`, is a genuinely separate and additional mechanism.
2. **"Enabling `EncryptionConfiguration` automatically protects every existing Secret."** It only governs behavior going forward; pre-existing objects require an explicit re-encryption pass to actually be rewritten under the new scheme.
3. **"The external KMS in a KMS v2 setup handles the actual Secret content."** It only ever wraps and unwraps the small, randomly generated Data Encryption Key — the Secret's actual plaintext content is encrypted locally by the API server and never sent to the KMS.
4. **"Rotating the KMS key requires re-encrypting every Secret in etcd."** KEK rotation only requires re-wrapping the existing DEKs under the new KEK — a materially cheaper operation than a full Secret-content re-encryption pass, and the two should not be conflated.

## 13. 🔑 Key Takeaways

- `EncryptionConfiguration`'s provider list order determines actual behavior — the first-listed provider governs all new writes, and an `identity` provider listed before an encrypting one silently disables encryption despite an apparently correct config.
- Enabling encryption at rest is never retroactive; existing Secrets require an explicit re-encryption pass (typically `kubectl replace` against every existing Secret) to actually be rewritten under the current provider chain.
- KMS v2's envelope encryption keeps the actual Secret content local to the API server, sending only a small, per-object Data Encryption Key to the external KMS for wrapping — a materially smaller exposure surface than sending Secret content directly to an external system.
- KEK rotation (cheap, re-wraps existing DEKs) and full Secret re-encryption (more expensive, rewrites Secret content) are two distinct operations that address different needs and should not be conflated.
- Encryption at rest, RBAC (§75), and mTLS (§119) are three independent boundaries protecting data at rest, API-level read access, and in-transit confidentiality respectively — none substitutes for the others.

## 14. Related Concepts & What's Next

This section deep-dived the actual encryption-at-rest mechanics underlying every Secret and external-secrets pattern introduced in §42 (Part 6) and §80 (Part 10) — `EncryptionConfiguration` provider ordering, KMS v2 envelope encryption's DEK/KEK split, and the non-retroactive nature of enabling encryption — building on §119's in-transit mTLS coverage to round out data protection across both states. §121, next and the capstone of Part 15, synthesizes every CKS-relevant mechanism covered across this entire Part — cluster setup hardening (§113) through this section's encryption depth — into a consolidated monitoring, logging, and runtime threat-detection view for the CKS exam.

**Next Section:** §121 — `Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md`

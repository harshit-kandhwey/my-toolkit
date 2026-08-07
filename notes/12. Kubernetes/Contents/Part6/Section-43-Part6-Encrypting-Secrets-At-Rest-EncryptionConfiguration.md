# Section 43 (Part 6): Encrypting Secrets at Rest (EncryptionConfiguration)

## 1. Definition

**Plain language:** By default, everything Kubernetes stores — including Secrets — lands in etcd as ordinary, unencrypted data (base64-encoded at the API layer, but not cryptographically protected, as [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) established). Anyone who gets hold of etcd's data files, a snapshot backup, or an unencrypted disk from the etcd host can read every Secret in the cluster directly, bypassing Kubernetes' RBAC entirely. EncryptionConfiguration closes that specific gap by telling the api-server to encrypt certain resource types before writing them to etcd.

**Precise definition:** **EncryptionConfiguration** is a static YAML configuration file passed to `kube-apiserver` via the `--encryption-provider-config` flag that defines an ordered list of **encryption providers** applied to specified API resources (most commonly `secrets`, optionally `configmaps` and others) before they are persisted to etcd. Supported providers range from `identity` (no encryption, the default), through software-based providers like `aescbc` and `aesgcm` using a locally-stored key, up to `kms` — the recommended production approach — which delegates the actual encryption key to an external **Key Management Service** (cloud KMS, HashiCorp Vault's transit engine, etc.), so the raw key material never has to live on the control-plane filesystem at all. Enabling this only affects objects written _after_ the configuration is applied — existing Secrets remain in their prior, unencrypted form in etcd until an explicit re-encryption pass rewrites them.

## 2. Why This Matters

- **etcd stores data in plaintext by default ([§10](../Part2/Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md)), and Secrets are the highest-value target that fact puts at risk.** Without EncryptionConfiguration, an attacker (or a mishandled backup, or an unencrypted disk snapshot) with access to etcd's raw data files reads every cluster Secret directly, completely bypassing the RBAC boundary that [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) identified as the real day-to-day defense.
- **This is the actual fix for the base64-is-not-encryption gap called out explicitly in [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)** — EncryptionConfiguration is the mechanism that turns "Secrets are technically recoverable by anyone touching etcd" into genuine ciphertext requiring the encryption key to reverse.
- **CKS treats this as core cluster-hardening material**, and expects hands-on fluency configuring and verifying encryption at rest, not just conceptual awareness — this is directly assessed in Part 15's cluster-hardening domain ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)) and is one of the CIS Benchmark checks `kube-bench` ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)) flags when absent.

🔑 **Key Takeaway:** EncryptionConfiguration is what actually encrypts Secrets (and optionally other resources) before they hit etcd's disk — without it, "Secrets are stored securely" is false regardless of RBAC, and enabling it retroactively still requires an explicit re-encryption pass over existing objects.

## 3. Prerequisites and Dependencies

Builds directly on [§10](../Part2/Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md) (etcd's data model, where "stores data in plaintext by default" is first established) and [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) (Secrets encoding vs. encryption, whose unresolved gap this section closes). Assumes familiarity with static Pod manifests and kube-apiserver flags from [§17](../Part3/Section-17-Part3-Static-Pods-Kubelet-Configuration.md).

## 4. Architecture: Where EncryptionConfiguration Sits in the Write Path

```text
 kubectl apply -f secret.yaml
          │
          ▼
 ┌────────────────────────┐
 │   kube-apiserver       │
 │                        │
 │  1. Admission chain    │  (§77 — validating/mutating webhooks)
 │  2. Encryption filter  │  ◄── EncryptionConfiguration applies HERE,
 │     (this section)     │      just before the write to etcd
 └──────────┬─────────────┘
            │  ciphertext (if a real provider is configured)
            ▼
 ┌────────────────────────┐
 │        etcd            │
 │  key: /registry/       │
 │    secrets/prod/db-pw  │
 │  value: k8s:enc:aescbc:│
 │   v1:key1:<ciphertext> │  ◄── opaque, unreadable without the key
 └────────────────────────┘
            ▲
            │  reverse path: api-server decrypts on READ,
            │  serves plaintext (base64-encoded) to authorized clients
 kubectl get secret db-credentials -o yaml
```

- **The encryption/decryption step happens entirely inside the api-server** — etcd itself has no awareness that encryption is happening; it simply stores whatever bytes the api-server hands it.
- **RBAC and encryption at rest are complementary, not redundant** — RBAC governs API-level read access; EncryptionConfiguration governs what an attacker with _direct storage access_ (bypassing the API entirely) can recover.
- **A `kms` provider stores no long-term key on the control-plane host at all** — the api-server calls out to an external KMS plugin for each encrypt/decrypt operation, meaning key compromise requires compromising the KMS itself, not just the etcd host's filesystem.

## 5. Hands-On: Enabling and Verifying Encryption at Rest

### 5.1 Writing an EncryptionConfiguration File

**Purpose:** Define which resources get encrypted, with which provider, on a kubeadm-managed control plane.

**Syntax:**

```yaml
# /etc/kubernetes/enc/encryption-config.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
      # - configmaps          # optionally extend to other sensitive resources
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: <base64-encoded-32-byte-key> # generate: head -c 32 /dev/urandom | base64
      - identity: {} # fallback: reads of not-yet-encrypted objects still work
```

**Example usage and expected output:**

```bash
$ head -c 32 /dev/urandom | base64
Vh8k3mQpR7wZ2sT9xN4bL6cY1eA0dF5g==

# Wire the file into the api-server static Pod manifest:
$ sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml
# add: --encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml
# and a hostPath volume mount for /etc/kubernetes/enc

$ kubectl -n kube-system get pod -l component=kube-apiserver
NAME                            READY   STATUS    RESTARTS   AGE
kube-apiserver-control-plane-1   1/1     Running   0          8s
```

**Production usage example:** Since kubeadm manages the api-server as a static Pod, editing the manifest triggers the kubelet to restart it automatically — no separate `systemctl restart` is needed here (unlike the certificate renewal case in [§18](../Part3/Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md)), because static Pod manifests are watched continuously by the kubelet.

**Common errors:** Providing a key that isn't exactly 32 bytes before base64 encoding (`aescbc` requires a 32-byte key for AES-256) causes the api-server to crash-loop immediately on startup with a key-length error visible in `kubectl logs` or the container runtime's logs directly (since `kubectl` itself may be unreachable if the api-server won't start).

### 5.2 Verifying Encryption Actually Took Effect

**Purpose:** Prove that a Secret's bytes are genuinely ciphertext in etcd, not just base64, distinguishing this from the false confidence flagged in [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md).

**Syntax:**

```bash
ETCDCTL_API=3 etcdctl \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  get /registry/secrets/production/db-credentials | hexdump -C | head -3
```

**Example usage and expected output:**

```bash
$ ETCDCTL_API=3 etcdctl --cacert=... --cert=... --key=... \
    get /registry/secrets/production/db-credentials | hexdump -C | head -3
00000000  2f 72 65 67 69 73 74 72  79 2f 73 65 63 72 65 74  |/registry/secret|
00000010  73 2f 70 72 6f 64 75 63  74 69 6f 6e 2f 64 62 2d  |s/production/db-|
00000020  0a 6b 38 73 3a 65 6e 63  3a 61 65 73 63 62 63 3a  |.k8s:enc:aescbc:|
```

**Production usage example:** The `k8s:enc:aescbc:` prefix in the raw etcd value is the definitive proof encryption is active — before enabling it, this same command would show the Secret's base64-encoded value in a readable JSON structure directly, with no such prefix.

**Common errors:** Checking only via `kubectl get secret -o yaml` to "verify encryption" — this always shows the same base64 output regardless of whether encryption at rest is enabled, since the api-server transparently decrypts on read; verification must inspect etcd's raw stored bytes directly, not the API response.

### 5.3 Re-Encrypting Existing Secrets

**Purpose:** Enabling EncryptionConfiguration only affects newly written objects — Secrets that existed beforehand remain in their old, unencrypted form until explicitly rewritten.

**Syntax:**

```bash
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
```

**Example usage and expected output:**

```bash
$ kubectl get secrets --all-namespaces -o json | kubectl replace -f -
secret/db-credentials replaced
secret/regcred replaced
secret/web-tls replaced
...
```

**Production usage example:** This re-encryption pass is a mandatory, easy-to-forget step immediately after first enabling EncryptionConfiguration on an already-running cluster — teams that skip it walk away believing all Secrets are encrypted when only newly created ones actually are.

**Common errors:** Running this command against a very large Secret population without considering api-server/etcd load — for clusters with thousands of Secrets, batching the re-encryption (by namespace, for instance) avoids a sudden write-load spike against etcd.

## 6. Production Usage Notes

- The `identity` provider should generally be listed **last** in the providers list, not first — providers are tried in order, and listing `identity` first would mean Secrets are written unencrypted by default, while listing it last means it's only used as a fallback for reading pre-existing unencrypted objects.
- The `aescbc`/`aesgcm` local-key providers are a real improvement over no encryption, but the key itself still lives on the control-plane filesystem, meaning root access to a control-plane node can still recover it — a `kms` provider backed by a cloud KMS or Vault's transit engine is the CKS-recommended production posture specifically because it removes that local key entirely.
- Key rotation for `aescbc`/`aesgcm` providers requires adding a new key to the providers list (ahead of the old one), then re-running the same re-encryption pass shown in the hands-on example above to migrate existing objects onto the new key before removing the old key from the configuration.

## 7. Security Considerations

- **Encryption at rest defends against a fundamentally different threat than RBAC** — it protects against someone with direct etcd/disk/backup access, not someone with a valid, over-permissioned Kubernetes credential; both controls are necessary, and neither substitutes for the other.
- **A `kms` provider is materially stronger than a local-key provider** because the encryption key material never needs to be present on a control-plane node's disk at all, removing an entire class of "root on control-plane host recovers all Secrets" attack.
- **etcd backups ([§109](../Part14/Section-109-Part14-Certificate-Rotation-Renewal.md)) taken before encryption was enabled — or before a re-encryption pass — remain unencrypted** regardless of the cluster's current configuration; backup retention policy needs to account for this when encryption is enabled partway through a cluster's life.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                        | Likely Cause                                                                                 | Resolution Path                                                                                                  |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| api-server crash-loops immediately after adding `--encryption-provider-config` | Malformed EncryptionConfiguration YAML, or a key of the wrong byte length                    | Check container logs directly (kubelet/containerd logs, since `kubectl` may be unreachable), validate key length |
| Secrets still appear unencrypted in raw etcd inspection after enabling config  | Existing Secrets were never re-encrypted (only new writes are affected)                      | Run the re-encryption pass: `kubectl get secrets --all-namespaces -o json \| kubectl replace -f -`               |
| Encryption verified for Secrets but a security audit still flags exposure      | ConfigMaps or another sensitive custom resource type wasn't included in the `resources` list | Extend the `resources` list in EncryptionConfiguration to cover every resource type holding sensitive data       |

## 9. Best Practices

- Prefer a `kms`-backed provider over local `aescbc`/`aesgcm` keys for any production cluster, specifically to remove the local-key-on-disk risk.
- Always run the re-encryption pass immediately after first enabling EncryptionConfiguration on a cluster with pre-existing Secrets — treat it as a mandatory step of the rollout, not an optional cleanup.
- Extend encryption coverage to any custom resource type that may carry sensitive data, not just the built-in `secrets` resource, if the cluster runs operators that store credentials in CRDs.

## 10. Common Anti-Patterns / Mistakes

- **Enabling EncryptionConfiguration and assuming it retroactively protects existing Secrets** without running the required re-encryption pass.
- **Storing the local `aescbc`/`aesgcm` key alongside the encryption config file with overly permissive filesystem permissions**, effectively defeating the purpose since anyone who can read the config can also read the key.
- **Treating encryption at rest as a substitute for RBAC hardening**, rather than a complementary control addressing a different threat model (disk/backup access vs. API access).

## 11. Interview Questions

**🎯 Beginner:** _"What does EncryptionConfiguration actually protect against that RBAC doesn't?"_
**Model answer:** RBAC controls who can read a Secret through the Kubernetes API — it's an authorization boundary. EncryptionConfiguration protects against someone who bypasses the API entirely and gets direct access to etcd's stored data, a disk snapshot, or an etcd backup — without it, that data is essentially plaintext (base64, per [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)) regardless of how tight RBAC is. They're complementary controls addressing different attack surfaces, not alternatives to each other.
_What the interviewer is probing for:_ Clear separation between the API-level and storage-level threat models.

**🎯 Intermediate:** _"You've just enabled EncryptionConfiguration with an `aescbc` provider on a cluster that already had hundreds of Secrets. Is the cluster now fully protected?"_
**Model answer:** Not yet. EncryptionConfiguration only affects objects written after it takes effect — the hundreds of pre-existing Secrets remain in their original, unencrypted form in etcd until they're explicitly rewritten. The required step is to force a write of every existing Secret, typically via `kubectl get secrets --all-namespaces -o json | kubectl replace -f -`, which triggers the api-server to write each one back through the now-active encryption provider. Only after that re-encryption pass completes is the entire existing Secret population actually protected.
_What the interviewer is probing for:_ Awareness of this specific, easy-to-miss operational gap that leaves a false sense of security if skipped.

**🎯 Senior:** _"Why would you choose a `kms` provider over `aescbc` for a production cluster, given that `aescbc` is simpler to set up?"_
**Model answer:** With `aescbc`, the actual encryption key has to exist somewhere on the control-plane host's filesystem for the api-server to use it — meaning root-level compromise of a control-plane node still recovers every Secret, because the key and the ciphertext both sit on the same machine. A `kms` provider instead delegates the actual encrypt/decrypt operation to an external key management service — the api-server calls out to it per-operation via a plugin, and no long-lived key material is ever stored locally. That means compromising a control-plane node alone is no longer sufficient to decrypt Secrets; the attacker would also need access to the external KMS, which typically has its own independent audit trail, access controls, and often hardware-backed key protection. For any production cluster handling genuinely sensitive data, that additional separation of the key from the encrypted data is worth the added operational complexity of integrating a KMS plugin.
_What the interviewer is probing for:_ Understanding of the actual threat-model improvement `kms` provides, not just "it's the newer option."

**🎯 Architect:** _"Design the full secrets-at-rest strategy for a regulated environment (e.g., handling financial or health data) running on Kubernetes."_
**Model answer:** I'd start with EncryptionConfiguration using a `kms` provider backed by a cloud-native KMS or an on-prem HSM-backed equivalent, covering both `secrets` and any custom resources known to carry sensitive data, with `identity` retained only as a last-resort fallback provider for compatibility during migration windows. I'd enforce this at cluster-bootstrap time (via the kubeadm ClusterConfiguration or an equivalent Infrastructure-as-Code template) so it's never an optional post-hoc step, and bake the mandatory re-encryption pass into the same automation that enables it. Beyond native encryption, I'd layer an external secret store (Vault or a managed equivalent) fronting the actual credential material via the External Secrets Operator, giving dynamic, short-lived, individually auditable secrets rather than long-lived static ones sitting in etcd at all — genuinely regulated data (cardholder data, PHI) generally shouldn't touch a native Kubernetes Secret directly if a compliant secret-management platform is available. Finally, I'd ensure etcd backups ([§109](../Part14/Section-109-Part14-Certificate-Rotation-Renewal.md)) taken after encryption was enabled are themselves stored encrypted-at-rest at the storage layer too, and that key rotation for the KMS-backed provider follows the organization's existing key-rotation policy and audit cadence, treating this as part of the same governance framework as any other regulated cryptographic material.
_What the interviewer is probing for:_ Ability to compose native Kubernetes encryption with external secret management and organizational compliance requirements into one coherent strategy, not just configuring one YAML file.

## 12. Common Misconceptions

1. **"Enabling EncryptionConfiguration instantly encrypts all existing Secrets."** It only affects subsequent writes; a re-encryption pass is required for objects that already existed.
2. **"`kubectl get secret -o yaml` will look different once encryption at rest is enabled."** It won't — the api-server transparently decrypts on read and always returns the same base64-encoded form to authorized clients regardless of at-rest encryption status; verification requires inspecting etcd's raw stored bytes directly.
3. **"Local-key providers like `aescbc` are just as secure as `kms`."** They're a real improvement over no encryption, but the key itself still resides on the control-plane filesystem, unlike a `kms` provider which keeps key material external to the cluster entirely.
4. **"Encryption at rest replaces the need for RBAC on Secrets."** They protect against entirely different threats — API-level access versus direct storage/backup access — and a hardened cluster needs both.

## 13. 🔑 Key Takeaways

- etcd stores Secrets in plaintext-equivalent (base64) form by default ([§10](../Part2/Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md), [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)); EncryptionConfiguration is the mechanism that actually encrypts them before they hit disk.
- Enabling encryption only protects newly written objects — a mandatory re-encryption pass (`kubectl get secrets --all-namespaces -o json | kubectl replace -f -`) is required for pre-existing Secrets.
- `kms`-backed providers are the recommended production approach over local `aescbc`/`aesgcm` keys, since they remove key material from the control-plane filesystem entirely.
- Verification must inspect etcd's raw stored bytes directly (via `etcdctl`), never the Kubernetes API response, since the api-server always transparently decrypts on read.
- For the highest-sensitivity secrets, external secret stores (Vault, External Secrets Operator) covered at CKS depth in [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) and Part 15's secrets material go beyond what native encryption at rest alone provides.

## 14. Related Concepts & What's Next

This section closed the gap left open in [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) (base64 is not encryption) by building on [§10](../Part2/Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md)'s fact that etcd stores data in plaintext by default. It connects forward to [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) (Part 15, CKS cluster hardening), where encryption at rest is revisited as one of several hardening checklist items alongside CIS Benchmarks and `kube-bench`, and to Part 15's broader treatment of external secret stores (Vault, External Secrets Operator) for organizations needing dynamic, short-lived credentials beyond what native Kubernetes Secrets provide — this repo's separate Ansible roadmap also covers Vault integration in operational depth for teams standardizing on it outside Kubernetes specifically. [§44](./Section-44-Part6-Environment-Variable-Injection-Precedence-Rules.md), next, returns to the application layer to cover environment variable injection precedence when multiple sources — ConfigMaps, Secrets, and direct values — define the same variable name.

**Next Section:** [§44](./Section-44-Part6-Environment-Variable-Injection-Precedence-Rules.md) — `Section-44-Part6-Environment-Variable-Injection-Precedence-Rules.md`

# Section 65 (Part 8): Supply Chain Security: Image Signing, SBOM, Content Trust

## 1. Definition

**Plain language:** Supply chain security answers three questions about an image before you run it: *who built it* (provenance), *has it been altered* (integrity and signatures), and *what is inside it* (the software bill of materials, SBOM).

**Precise definition:**

- **Digest pinning:** referencing an image by its content hash (`repo@sha256:...`) so the bytes are immutable; tags are mutable pointers ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- **Image signing:** a cryptographic signature over the image digest, stored in the registry as an OCI artifact next to the image. Current tools: **Sigstore cosign** (keyed or keyless via OIDC identity and a transparency log) and **Notation** (Notary Project, X.509 based).
- **Docker Content Trust (DCT):** the legacy Notary v1 / TUF-based mechanism enabled by `DOCKER_CONTENT_TRUST=1`. It signs tags (not just digests) and makes the CLI refuse unsigned tags. It is little used today, Docker has signalled retirement of the Notary v1 service for Docker Hub, and most ecosystems moved to cosign or Notation; check the current Docker announcements before depending on it.
- **SBOM:** a machine-readable inventory of packages in an image, in SPDX or CycloneDX format.
- **Attestations:** signed statements about an image (SBOM, build provenance such as SLSA, vulnerability scan results) attached to the image digest using the in-toto format.

> 💡 **Tip:** Signing proves *who* published a digest; it does not prove the content is safe. Combine signing, SBOM, provenance and scanning ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)), and verify at deploy time, not just at build time.

## 2. Why This Matters

- Attacks like compromised base images, typosquatted images and poisoned dependencies reach production through trust in a tag or a registry.
- A mutable tag (`:latest`, even `:1.4`) can silently change underneath you.
- Regulations and customers (US Executive Order 14028, EU CRA, SLSA, FedRAMP) increasingly demand an SBOM and provenance.
- When a new CVE lands (Log4Shell style), an SBOM answers "are we affected?" in minutes instead of days.

## 3. Prerequisites and Dependencies

Requires image manifests and digests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), OCI specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), tagging conventions ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), and vulnerability scanning ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)). Signing and attestations are stored in registries ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)) and produced in pipelines ([§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)). BuildKit attestation flags rely on [§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md) and [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md).

## 4. Architecture / Conceptual Diagram

```text
  BUILD (CI)                          REGISTRY                        DEPLOY (cluster/host)

  source ──► docker buildx build      repo:tag ──► sha256:abc... (image index)
              --provenance=mode=max        ▲
              --sbom=true                  │ referrers / .sig tags
                    │                      │
                    ▼                ┌─────┴──────────────────────────┐
              image + attestations   │ sha256:abc...  (image)          │
                    │                │ ├─ signature   (cosign/notation)│
         cosign sign (OIDC, keyless) │ ├─ SBOM        (SPDX/CycloneDX) │
                    │                │ └─ provenance  (SLSA, in-toto)  │
                    └──────────────► └─────┬──────────────────────────┘
                                           │ pull by digest
                                           ▼
                                  admission / policy check
                              verify signature identity + attestations
                              ┌── pass ──► run
                              └── fail ──► reject

  Trust roots:  keyless ──► Fulcio cert (OIDC identity) + Rekor transparency log
                keyed   ──► your public key (KMS/HSM held private key)
                DCT     ──► Notary v1 TUF root/targets/snapshot keys
```

- **Signature** binds an identity or key to a digest, not to a tag.
- **SBOM and provenance** are attestations: signed claims you can verify and query.
- **Policy enforcement** (admission controller or CI gate) is what makes signing meaningful; unchecked signatures protect nothing.

## 5. Hands-On

### 5.1 Pin by Digest

```bash
docker buildx imagetools inspect myorg/api:1.4.2
docker pull myorg/api:1.4.2
docker image inspect myorg/api:1.4.2 --format '{{index .RepoDigests 0}}'
```

```text
Name:      docker.io/myorg/api:1.4.2
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:9f2c...e41a
```

```dockerfile
FROM python:3.12-slim@sha256:3a1b...c9d0
```

Pinning by digest makes the build reproducible and tamper-evident; automate bumps with Renovate or Dependabot so pins do not rot ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).

### 5.2 Sign with cosign (Keyed)

```bash
cosign generate-key-pair                       # creates cosign.key / cosign.pub
cosign sign --key cosign.key myorg/api@sha256:9f2c...e41a
cosign verify --key cosign.pub myorg/api@sha256:9f2c...e41a
```

```text
Verification for myorg/api@sha256:9f2c...e41a --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - The signatures were verified against the specified public key
```

Always sign the **digest**, not the tag; cosign warns when given a tag because the tag could move. Keep the private key in a KMS or HSM (`--key awskms://...`) rather than a file.

### 5.3 Keyless Signing in CI (GitHub Actions)

```yaml
permissions:
  id-token: write      # OIDC token for Sigstore
  contents: read
  packages: write

steps:
  - uses: sigstore/cosign-installer@v3
  - name: Sign image
    run: cosign sign --yes ghcr.io/myorg/api@${{ steps.build.outputs.digest }}
```

```bash
cosign verify ghcr.io/myorg/api@sha256:9f2c...e41a \
  --certificate-identity-regexp 'https://github.com/myorg/api/.github/workflows/release.yml@refs/tags/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Keyless signing has no long-lived key to steal: Fulcio issues a short-lived certificate for the workflow identity and the signature is logged in Rekor. The verifier checks **who** signed (identity and issuer), which is the important policy decision.

### 5.4 Generate and Attach an SBOM and Provenance at Build Time

```bash
docker buildx build \
  --sbom=true \
  --provenance=mode=max \
  -t ghcr.io/myorg/api:1.4.2 --push .

docker buildx imagetools inspect ghcr.io/myorg/api:1.4.2 \
  --format '{{ json .SBOM }}' | head
docker buildx imagetools inspect ghcr.io/myorg/api:1.4.2 \
  --format '{{ json .Provenance }}' | head
```

BuildKit stores these as in-toto attestation manifests inside the image index. Provenance records the source repo, commit, builder, build arguments and materials; `mode=max` includes more detail and may expose build args, so do not pass secrets as args ([§64](Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)). Recent Docker Engine/Buildx versions emit minimal provenance by default for registry pushes.

### 5.5 Generate an SBOM with Syft and Scan It

```bash
syft myorg/api:1.4.2 -o spdx-json > sbom.spdx.json
syft myorg/api:1.4.2 -o cyclonedx-json > sbom.cdx.json
grype sbom:./sbom.spdx.json
```

```text
NAME          INSTALLED  TYPE    VULNERABILITY   SEVERITY
openssl       3.0.13     deb     CVE-XXXX-XXXXX  High
```

Scanning the stored SBOM later (without pulling the image) lets you re-evaluate the fleet whenever new CVEs are published. Trivy (`trivy image --format cyclonedx`) and Docker Scout (`docker scout sbom`, `docker scout cves`) offer equivalent flows. The older `docker sbom` plugin has been superseded by Scout.

### 5.6 Attach and Verify an SBOM Attestation with cosign

```bash
cosign attest --yes --predicate sbom.spdx.json --type spdxjson \
  ghcr.io/myorg/api@sha256:9f2c...e41a

cosign verify-attestation --type spdxjson \
  --certificate-identity-regexp '...' --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/myorg/api@sha256:9f2c...e41a | jq -r '.payload' | base64 -d | jq '.predicate.packages | length'
```

### 5.7 Docker Content Trust (Legacy)

```bash
export DOCKER_CONTENT_TRUST=1
docker pull alpine:3.20            # succeeds only if the tag has trust data
docker pull someorg/unsigned:1.0   # fails: no trust data for 1.0

docker trust inspect --pretty alpine:3.20
docker trust sign myorg/api:1.4.2  # signs the tag with your delegation key
```

```text
Error: remote trust data does not exist for docker.io/someorg/unsigned: ...
```

DCT is enforced client-side only by the Docker CLI, covers pull/push/run/create, and is bypassed by tools that do not use that CLI (containerd, Kubernetes). It also signs tags and needs root/targets key management. This is why admission controllers with cosign or Notation are the modern enforcement point.

### 5.8 Enforce in Kubernetes (Policy Sketch)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata: { name: verify-image-signatures }
spec:
  validationFailureAction: Enforce
  rules:
    - name: require-cosign
      match: { any: [ { resources: { kinds: [Pod] } } ] }
      verifyImages:
        - imageReferences: ["ghcr.io/myorg/*"]
          attestors:
            - entries:
                - keyless:
                    issuer: https://token.actions.githubusercontent.com
                    subject: https://github.com/myorg/*
```

Sigstore policy-controller, Ratify (for Notation) and Connaisseur are alternatives. The same idea applies to non-Kubernetes hosts via a deploy-script gate that runs `cosign verify` before `docker run`.

## 6. Production Usage Notes

- **Sign in CI only, from a protected branch or tag**, using keyless OIDC or a KMS-held key; developers should not hold signing keys.
- **Sign the index digest** for multi-arch images ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)); signing a platform manifest leaves the index unsigned.
- **Copy signatures when promoting** images between registries (`cosign copy`, `crane copy`, `oras`) or re-sign at promotion ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)).
- **Store SBOMs with the image** and in an inventory system (Dependency-Track, Scout) so fleet-wide queries are possible.
- **Mirror and vet base images** in an internal registry; build from approved bases only.
- **Registry support:** Docker Hub, GHCR, ECR, ACR, Artifact Registry and Harbor store cosign signatures and OCI referrers; verify support for your registry ([§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](../Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)).
- **Docker Official Images and Docker Hardened Images** carry provenance and SBOM attestations; verify them rather than assume.
- Frameworks to align with: SLSA levels, OpenSSF Scorecard, NIST SSDF.

## 7. Security Considerations

- **A valid signature is not a safe image.** A compromised build pipeline can sign malicious output; protect CI itself (pinned actions, least-privilege tokens, ephemeral runners).
- **Verify identity, not just validity.** `cosign verify` without `--certificate-identity` accepts any Sigstore signer; always constrain identity and issuer.
- **Key custody:** keyed signing moves risk to key theft; use KMS/HSM, rotation, and revocation plans.
- **Tag mutability:** verifying `repo:tag` and then pulling `repo:tag` is a race; resolve to a digest first and run the digest.
- **Rekor is public** for the public Sigstore instance: workflow names and repo identities become visible. Use a private Sigstore deployment for sensitive code.
- **Provenance can leak build args**; keep secrets out of `ARG` ([§64](Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Dependency confusion and typosquatting** bypass signing entirely if you trust the wrong publisher; pin and review base images and package sources.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `no matching signatures` on verify | Signed a different digest, a platform manifest instead of the index, or not copied after promotion | Verify the exact digest; re-sign or copy signatures |
| `none of the expected identities matched` | Workflow ref/identity regex too strict or wrong issuer | Inspect the certificate (`cosign verify ... | jq`), adjust regex |
| `remote trust data does not exist` (DCT) | Tag has no Notary signature | Sign with `docker trust sign` or disable DCT for that image |
| DCT does not block pulls in Kubernetes | DCT is a Docker CLI feature only | Use an admission controller |
| SBOM missing from `imagetools inspect` | Built with the classic builder or without `--sbom` | Use `docker buildx build --sbom=true` and push to a registry |
| Attestations vanish after `docker pull`/`save` | Local image store does not keep attestation manifests | Inspect in the registry; use `imagetools` or `crane` |
| 401/403 pushing signatures | Registry credentials lack write to the signature tag | Grant push rights; check registry referrers support |
| Policy rejects every pod after rollout | Verification enforced before signing was in place | Start in audit mode, sign existing images, then enforce |

## 9. Best Practices

- Pin base images and deployments by digest; keep tags for humans only.
- Generate SBOM and provenance on every build (`--sbom=true --provenance=mode=max`) and store them with the image.
- Sign in CI with keyless OIDC or KMS keys; verify identity and issuer at deploy time.
- Enforce verification with an admission policy; roll out in audit mode first.
- Continuously rescan stored SBOMs against fresh vulnerability data.
- Build from minimal, vetted bases ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)) and rebuild regularly to pick up patches.
- Document and test key compromise and signer-revocation procedures.

## 10. Common Anti-Patterns / Mistakes

- Signing tags rather than digests, or verifying one reference and deploying another.
- Verifying signatures without constraining identity.
- Generating an SBOM once and never using it.
- Relying on `DOCKER_CONTENT_TRUST` as the only control while workloads run via containerd or Kubernetes.
- Developers signing from laptops with long-lived keys.
- Using `:latest` for base images in production Dockerfiles.
- Treating "signed" as "scanned and approved".

## 11. Interview Questions

**🎯 Beginner:** _"Why is `FROM node:22` less safe than `FROM node:22@sha256:...`?"_
**Model answer:** A tag is a mutable pointer; the publisher (or an attacker with registry access) can repoint `node:22` to different content at any time, so two builds can pull different bytes. A digest is a hash of the manifest, so it identifies exactly one immutable set of layers, and the daemon verifies it on pull. Digest pinning gives reproducibility and tamper evidence. The cost is that you must update the pin deliberately, usually with Renovate or Dependabot, to receive security patches.
_What the interviewer is probing for:_ Tag mutability versus content addressing.

**🎯 Intermediate:** _"What is an SBOM, how do you produce one for an image, and what do you do with it?"_
**Model answer:** An SBOM lists the packages and versions inside an image in SPDX or CycloneDX. Produce it at build time with `docker buildx build --sbom=true`, or after the fact with Syft, Trivy or `docker scout sbom`. Store it with the image as an attestation and in an inventory. Use it to match components against vulnerability feeds without re-pulling images, to answer "which services contain library X" when a new CVE appears, and for compliance and license checks. Accuracy depends on the scanner's ability to detect packages, so statically linked binaries and vendored code can be missed.
_What the interviewer is probing for:_ Practical SBOM generation and the incident-response use case, including its limits.

**🎯 Senior:** _"Explain keyless signing with cosign. What does a verifier check, and what are the failure modes?"_
**Model answer:** In CI, the job obtains an OIDC token from the CI provider. Cosign sends it to Fulcio, which issues a short-lived X.509 certificate binding the workflow identity (subject) and issuer to an ephemeral key. Cosign signs the image digest, discards the key, and records the signature in the Rekor transparency log. A verifier checks the signature, validates the certificate chain to the Sigstore root, checks the Rekor entry, and, critically, matches the certificate's identity and issuer against policy. Failure modes: verifying without identity constraints, an over-broad identity regex that allows other repos or branches, signing a tag-resolved digest that differs from what is deployed, and a compromised pipeline signing malicious output. Public Rekor also exposes identities.
_What the interviewer is probing for:_ Understanding of the trust chain and that identity policy is the real control.

**🎯 Architect:** _"Design supply-chain controls so only images built by your CI from reviewed code can run in production, across multiple registries and clusters."_
**Model answer:** Build in hardened ephemeral CI from protected branches with pinned actions and base images by digest. Emit SBOM and SLSA provenance via BuildKit, sign the index digest with keyless OIDC (or KMS keys), and attest scan results. Promote by digest between registries, copying signatures and attestations (or re-signing at promotion gates). In every cluster, an admission controller (Kyverno, policy-controller or Ratify) enforces: signature from the expected workflow identity, a provenance attestation naming the approved repo and builder, no critical vulnerabilities from a recent attestation, and digest-only references. Restrict registries to an allowlist and mirror upstream bases through an internal proxy. Monitor with SBOM inventory for fleet-wide CVE queries, rehearse key/identity revocation, and measure against SLSA levels. Start in audit mode to avoid outages.
_What the interviewer is probing for:_ End-to-end design connecting build, registry, promotion and runtime enforcement, with rollout realism.

## 12. Common Misconceptions

- "Signed means secure." It means a known party published it; the content may still be vulnerable or malicious.
- "DCT protects all my pulls." It only affects the Docker CLI, and it is a legacy mechanism.
- "An SBOM finds vulnerabilities." It is an inventory; matching against vulnerability data is a separate step.
- "Tags with version numbers are immutable." Most registries allow overwriting unless immutability is enforced.
- "Official images need no verification." They are well maintained, but you should still pin and verify.

## 13. 🔑 Key Takeaways

- Pin images by digest; tags are mutable.
- Sign digests with cosign (keyless OIDC or KMS) or Notation, and verify identity and issuer.
- Produce SBOM and provenance at build time with `--sbom=true --provenance=mode=max`.
- Docker Content Trust (Notary v1) is legacy and CLI-only; use admission-time verification instead.
- Signing, SBOM, provenance and scanning are complementary; none alone proves an image is safe.
- Enforcement at deploy time (admission control) is what makes the rest worthwhile.

## 14. Related Concepts & What's Next

Related: image anatomy and digests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), OCI specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), vulnerability scanning ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)), secrets ([§64](Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), CI pipelines ([§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), image promotion ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)). This closes Part 8. Next, [§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md) begins Part 9 with registries, starting from Docker Hub fundamentals, where these signed artifacts are stored and distributed.

**Next Section:** [§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md) — `Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md`

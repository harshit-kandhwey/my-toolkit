# Section 116 (Part 15): Supply Chain Security — Image Scanning (Trivy), Signing (Cosign/Sigstore), SBOM

## 1. Definition

**Plain language:** §115 hardened the container spec itself and, for the highest-risk workloads, changed the isolation model entirely — but both of those controls assume the image being deployed is exactly what it claims to be, built from source the team actually wrote, free of known vulnerable dependencies. Supply Chain Security asks the question that comes before any of that: how do you know the image sitting in the registry hasn't been tampered with, doesn't bundle a vulnerable library nobody reviewed, and was actually produced by the build pipeline your organization trusts — before it ever reaches a cluster to be hardened?

**Precise definition:** **Supply chain security**, the CKS domain tied with Minimize Microservice Vulnerabilities for the highest exam weight (20%), covers three complementary controls applied before and during deployment. **Image scanning** (via **Trivy**, an open-source scanner from Aqua Security) statically analyzes a container image's OS packages and application dependencies against known-vulnerability databases (CVE feeds), reporting matches by severity. **Image signing** (via **Cosign**, part of the **Sigstore** project) cryptographically signs an image's content digest at build time and lets an admission-time policy verify that signature before allowing the image to run, proving provenance and detecting tampering. An **SBOM (Software Bill of Materials)** is a structured, machine-readable manifest — commonly in **SPDX** or **CycloneDX** format — enumerating every package, library, and version an image contains, generated at build time and used both for vulnerability tracking and as an auditable record of exactly what shipped in a given image.

## 2. Why This Matters

- **Most real-world container compromises exploit a known, already-patched vulnerability in a dependency nobody updated** — not a novel zero-day — meaning image scanning against CVE databases is disproportionately high-leverage: it catches the overwhelming majority of realistic supply-chain risk with automated tooling, not manual review.
- **Without cryptographic image signing, "which image is actually running in production" is an assumption, not a verified fact** — a mutable tag (`:latest`, or even a seemingly pinned version tag that got silently overwritten in the registry) can point to different content over time; signature verification at admission time is the only mechanism that makes "this exact, reviewed content is what's running" a provable statement rather than a hope.
- **An SBOM turns "what's in this image" from an archaeological exercise into a lookup** — when a new CVE is disclosed for a widely used library (a Log4Shell-class event), an organization with SBOMs for every deployed image can identify every affected image in minutes by querying the SBOM inventory, instead of re-scanning the entire fleet from scratch under incident-response time pressure.

🔑 **Key Takeaway:** Supply chain security establishes trust in an image before it ever reaches the hardening controls covered in §114 and §115 — Trivy scans for known vulnerabilities in what an image actually contains, Cosign/Sigstore cryptographically proves an image is unmodified and came from a trusted build, and an SBOM provides the auditable inventory that makes both scanning and incident response tractable at fleet scale.

## 3. Prerequisites and Dependencies

This section assumes §115's SecurityContext and sandboxed-runtime hardening as prior layers of defense, and positions supply chain security as the control that must succeed _before_ those layers are ever exercised — a perfectly hardened SecurityContext running a maliciously tampered image is still a compromised workload. It assumes basic familiarity with container image and registry concepts from Part 1/Part 2 (image layers, tags, digests) and CI/CD pipeline concepts from GitOps coverage in Part 13 (§88-adjacent), since scanning, signing, and SBOM generation are typically wired into the build pipeline rather than performed manually. Forward-references §117, which covers static analysis of Kubernetes manifests themselves (kube-linter, Kubesec) — a complementary check on the deployment configuration rather than the image content this section addresses.

## 4. Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────────┐
│  CI/CD build pipeline                                                      │
│                                                                            │
│  1. docker build → produces image layers                                   │
│           │                                                                │
│           ▼                                                                │
│  2. trivy image myapp:1.4  → scans OS packages + app deps vs CVE feeds     │
│           │  FAIL if CRITICAL/HIGH found → pipeline blocks push            │
│           ▼                                                                │
│  3. syft myapp:1.4 -o spdx-json > sbom.json  → generates SBOM              │
│           │                                                                │
│           ▼                                                                │
│  4. docker push registry/myapp:1.4  → image pushed, gets a content digest  │
│           │                                                                │
│           ▼                                                                │
│  5. cosign sign --key cosign.key registry/myapp@sha256:abc123...           │
│           │  attaches signature as an OCI artifact alongside the image     │
│           ▼                                                                │
│  6. cosign attest --predicate sbom.json registry/myapp@sha256:abc123...    │
│           │  attaches signed SBOM attestation                              │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │  at deploy time
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Kubernetes admission control                                                │
│    Policy engine (Kyverno / OPA Gatekeeper) verifyImages rule:               │
│      - Cosign signature valid for registry/myapp@sha256:abc123...?           │
│      - Signed by the expected build-pipeline key / Sigstore keyless identity?│
│    PASS → Pod admitted        FAIL → Pod rejected outright                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Scanning happens at build time (pre-push, "shift-left") and ideally again continuously against images already deployed** — a CVE disclosed after an image was scanned clean still needs to be caught, which requires re-scanning the fleet's already-running images on a recurring basis, not treating a build-time scan as a permanent guarantee.
- **Signing verifies _integrity and provenance_, not _safety_** — a perfectly signed image can still contain a critical CVE; signing and scanning are answering different questions ("is this the image the pipeline actually built" versus "does this image contain known vulnerabilities") and neither substitutes for the other.
- **Sigstore's "keyless" signing model uses short-lived certificates issued via OIDC identity (tied to a CI pipeline's own identity, e.g., a GitHub Actions workflow) rather than long-lived private keys** — this removes the operational burden and risk of managing a persistent signing key, since the signing identity is proven per-build against an OIDC provider instead.

## 5. Hands-On

### 5.1 Scanning an Image with Trivy

**Purpose:** Identify known CVEs in an image's OS packages and application dependencies before it's pushed to a registry or deployed.

**Syntax:**

```bash
trivy image --severity CRITICAL,HIGH --exit-code 1 myregistry/myapp:1.4
```

```yaml
# CI pipeline step (conceptual, e.g. GitLab CI / GitHub Actions)
- name: Scan image for critical vulnerabilities
  run: |
    trivy image --severity CRITICAL,HIGH --exit-code 1 \
      --ignore-unfixed myregistry/myapp:${{ github.sha }}
```

**Example usage and expected output:**

```bash
$ trivy image --severity CRITICAL,HIGH myregistry/myapp:1.4
myregistry/myapp:1.4 (alpine 3.19.1)
=====================================
Total: 2 (CRITICAL: 1, HIGH: 1)

┌─────────────┬────────────────┬──────────┬───────────────────┐
│   Library    │ Vulnerability   │ Severity │ Fixed Version      │
├─────────────┼────────────────┼──────────┼───────────────────┤
│ openssl      │ CVE-2024-XXXXX  │ CRITICAL │ 3.1.4-r2            │
│ libcurl      │ CVE-2023-YYYYY  │ HIGH     │ 8.5.0-r1            │
└─────────────┴────────────────┴──────────┴───────────────────┘
```

**Production usage example:** `--ignore-unfixed` is a standard production flag — it suppresses findings for CVEs with no available patch yet, since blocking a pipeline on a vulnerability the team cannot remediate today produces no security benefit, only friction; those unfixed findings should still be tracked, just not used as a hard release gate.

**Common errors:** Scanning only the final application layer and missing vulnerabilities baked into an early base-image layer that a multi-stage Dockerfile never removes — Trivy scans the full image by default, but teams sometimes misconfigure scans to target only a specific path or layer, silently missing base-OS-level CVEs that make up the bulk of real findings.

### 5.2 Signing an Image and Verifying at Admission Time

**Purpose:** Cryptographically prove an image's provenance and integrity, then enforce that only signed images are admitted to the cluster.

**Syntax:**

```bash
# Keyless signing using Sigstore's OIDC-backed identity (typical CI usage)
cosign sign --yes myregistry/myapp@sha256:abc123def456...

# Or key-based signing
cosign generate-key-pair
cosign sign --key cosign.key myregistry/myapp@sha256:abc123def456...

# Verify manually
cosign verify --key cosign.pub myregistry/myapp@sha256:abc123def456...
```

```yaml
# Kyverno ClusterPolicy enforcing signature verification at admission
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-signature
      match:
        any:
          - resources:
              kinds: ["Pod"]
      verifyImages:
        - imageReferences:
            - "myregistry/*"
          attestors:
            - entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcD...
                      -----END PUBLIC KEY-----
```

**Example usage and expected output:**

```bash
$ kubectl apply -f unsigned-pod.yaml
Error from server: admission webhook "validate.kyverno.svc-fail" denied the request:
resource Pod/default/unsigned-pod was blocked due to the following policies:
verify-image-signatures: check-signature: 'image signature verification failed
for myregistry/myapp@sha256:...: no matching signatures found'
```

**Production usage example:** Keyless signing tied to a specific CI pipeline's OIDC identity (e.g., "this image was signed by a GitHub Actions run in the `myorg/myapp` repository on the `main` branch") is generally preferred over long-lived key-based signing in production, since it removes the operational burden of storing, rotating, and protecting a private signing key entirely — the trust anchor becomes the CI provider's own identity federation instead.

**Common errors:** Enforcing signature verification cluster-wide before every image source (including third-party and base images pulled directly from public registries) has been re-signed or otherwise brought under the organization's own signing pipeline — a blanket enforcement policy rolled out without first identifying every legitimate unsigned image source causes a fleet-wide outage the moment it's set to `Enforce` rather than `Audit`.

### 5.3 Generating and Attaching an SBOM

**Purpose:** Produce a structured inventory of every package an image contains, for vulnerability tracking and audit purposes, and attach it to the image as a verifiable attestation.

**Syntax:**

```bash
# Generate an SPDX-format SBOM using Syft (commonly paired with Trivy/Cosign)
syft myregistry/myapp:1.4 -o spdx-json > sbom.json

# Attach the SBOM as a signed attestation to the image
cosign attest --yes --predicate sbom.json --type spdxjson \
  myregistry/myapp@sha256:abc123def456...

# Query an SBOM later against a newly disclosed CVE
trivy sbom sbom.json --severity CRITICAL
```

**Example usage and expected output:**

```bash
$ syft myregistry/myapp:1.4 -o spdx-json > sbom.json
✔ Loaded image
✔ Parsed image
✔ Cataloged packages [142 packages]

$ cosign attest --yes --predicate sbom.json --type spdxjson myregistry/myapp@sha256:abc123...
Uploading attestation to registry/myapp:sha256-abc123.att
tlog entry created with index: 128374921
```

**Production usage example:** When a critical CVE is disclosed for a widely used library, organizations with SBOM attestations for every deployed image can run a single query (`trivy sbom` or an equivalent SBOM-querying tool) against their entire stored SBOM inventory to identify every affected image within minutes — versus re-scanning every image in the fleet from scratch, which is materially slower under incident-response time pressure.

**Common errors:** Generating an SBOM once at initial image build and never regenerating it on subsequent rebuilds of the "same" image tag — dependency versions drift across rebuilds even without an explicit code change (a base image update, a floating dependency version), and a stale SBOM produces false negatives when queried against a newly disclosed CVE.

## 6. Production Usage Notes

- **Scanning should happen at multiple points, not just once pre-push** — build-time scanning (blocking the pipeline on CRITICAL/HIGH findings) catches known-bad images before deployment, but a recurring registry-wide or admission-time scan is necessary to catch CVEs disclosed _after_ an image was already scanned clean and deployed.
- **Signature enforcement should roll out in `Audit` mode before `Enforce`**, mirroring the staged rollout pattern already established for Pod Security Admission (§78) and AppArmor/seccomp (§114) — flipping straight to `Enforce` cluster-wide without first identifying every legitimate unsigned image source (base images, third-party dependencies not yet brought under the organization's signing pipeline) causes avoidable outages.
- **SBOMs should be regenerated on every image build, not just the first, and stored centrally (not just attached to the image itself)** — a centralized SBOM inventory queryable independent of any single image being pulled is what makes fleet-wide incident response fast when a new CVE is disclosed.

## 7. Security Considerations

- **Who can approve exceptions to scanning/signing enforcement (an image allowed through despite a CRITICAL finding, or an unsigned image granted a policy exemption) must be a tightly scoped, reviewed decision** — a policy engine exemption (§78-adjacent OPA Gatekeeper/Kyverno exception mechanism) granted broadly or without expiry becomes a permanent, silently-forgotten hole in the supply chain trust boundary.
- **A signing key compromise (in key-based signing) or an OIDC identity compromise (in keyless signing) undermines the entire trust chain retroactively** — every image ever signed with that key or identity becomes suspect, not just future ones; this is precisely why keyless signing's short-lived, per-build certificates are preferred over long-lived static keys whose compromise has unbounded blast radius.
- **A scanner or signing tool that's misconfigured to silently pass (a scan that exits 0 regardless of findings due to a missed `--exit-code 1` flag, or a verification policy that fails open instead of closed on a webhook timeout) provides worse-than-nothing false assurance** — teams see a green pipeline and believe images are vetted when the gate was never actually enforcing anything; admission policies should default to fail-closed, and pipeline scan steps should be periodically tested with a known-bad image to confirm they actually block as designed.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                 | Cause                                                                                                                    | Fix                                                                                                                                    |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| CI pipeline scan step passes even though the image has known CRITICAL CVEs              | Missing or misconfigured `--exit-code 1` flag, so Trivy reports findings but doesn't fail the build                      | Explicitly set `--exit-code 1 --severity CRITICAL,HIGH` and periodically test the pipeline against a known-bad image                   |
| Legitimate image rejected at admission with "no matching signatures found"              | Image was never signed, or signed with a key/identity the verification policy doesn't recognize                          | Confirm the image passed through the organization's signing step; check the policy's configured public key or OIDC identity matcher    |
| Signature verification policy causes a fleet-wide outage right after enabling `Enforce` | Third-party/base images not yet brought under the signing pipeline were never identified before enforcement              | Roll out via `Audit` mode first, inventory every unsigned image source, then flip to `Enforce` once all legitimate sources are covered |
| SBOM query misses a package known to be in the image                                    | SBOM was generated once at an earlier build and never regenerated after a subsequent rebuild changed dependency versions | Regenerate the SBOM on every build as a standard pipeline step, not a one-time action                                                  |
| Scanner reports large numbers of findings with no available fix                         | Scan configured without `--ignore-unfixed`, surfacing CVEs with no remediation path yet                                  | Add `--ignore-unfixed` to the release-gating scan; track unfixed findings separately for monitoring, not as a hard blocker             |

## 9. Best Practices

- Gate the CI pipeline on Trivy scans for CRITICAL/HIGH severity findings, using `--ignore-unfixed` to avoid blocking on vulnerabilities with no available patch.
- Sign every image at build time using Sigstore's keyless (OIDC-backed) model where the CI platform supports it, avoiding the operational burden of long-lived private keys.
- Roll out signature-verification admission policies in `Audit` mode first, inventory legitimate unsigned image sources, then switch to `Enforce`.
- Regenerate and re-attach an SBOM on every image build, and store SBOMs centrally so they're queryable independent of pulling the image itself.
- Periodically test scanning and signing gates against a deliberately known-bad or unsigned image to confirm the gate actually fails closed, not just that it exists.

## 10. Common Anti-Patterns / Mistakes

- **Scanning an image once at build time and never re-scanning already-deployed images**, missing CVEs disclosed after deployment.
- **Enforcing signature verification cluster-wide in one step without first auditing which image sources are actually unsigned**, causing a self-inflicted outage.
- **Treating a signed image as automatically safe**, conflating provenance verification (this is the image the pipeline built) with vulnerability safety (this image has no known CVEs) — they answer different questions.
- **Generating an SBOM once and never regenerating it across subsequent rebuilds**, producing a stale inventory that misses newly introduced dependency versions.
- **Granting broad, unreviewed, non-expiring policy exceptions** for scanning or signing enforcement that quietly become permanent trust-boundary holes.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between what Trivy does and what Cosign does?"_
**Model answer:** Trivy scans an image's contents — OS packages and application dependencies — against known-vulnerability databases and reports which CVEs are present by severity. Cosign does something entirely different: it cryptographically signs an image's content digest at build time and later verifies that signature, proving the image hasn't been tampered with and came from a trusted build pipeline. Trivy answers "does this image contain known vulnerabilities," Cosign answers "is this actually the exact image my pipeline built" — a signed image can still be vulnerable, and a vulnerability-free image can still be unsigned and unverifiable.
_What the interviewer is probing for:_ Clear separation between vulnerability scanning and provenance verification as distinct, complementary concerns.

**🎯 Intermediate:** _"Why is keyless signing via Sigstore generally preferred over traditional key-based signing in a CI/CD pipeline?"_
**Model answer:** Key-based signing requires generating, securely storing, rotating, and protecting a long-lived private key — if that key is ever compromised, every image signed with it, past and future, becomes suspect, and the operational burden of key management is itself a real risk surface. Sigstore's keyless model instead issues a short-lived certificate per signing operation, tied to the CI pipeline's own OIDC identity (for example, proving "this specific GitHub Actions workflow run in this specific repository performed this signature"). There's no long-lived key to steal or rotate, and the trust anchor becomes the CI platform's existing identity federation, which is both more auditable and has a much smaller blast radius if any single signing event is compromised.
_What the interviewer is probing for:_ Understanding of the operational and security trade-offs between static key management and short-lived, identity-federated signing, not just "keyless is newer."

**🎯 Senior:** _"Your team wants to enforce that only signed, scanned images can run in production. Walk through how you'd roll that out without breaking existing workloads."_
**Model answer:** I'd start with an inventory phase — identify every currently deployed image across the fleet, and classify each by whether it's already produced by the organization's own build pipeline (and can be retroactively signed and scanned) versus a third-party or base image pulled directly from an external registry that needs to be brought under an internal re-signing process first. I'd wire scanning into the CI pipeline immediately as a build-gate for new builds, using `--ignore-unfixed` so the gate doesn't block on unpatchable CVEs. For signature enforcement, I'd deploy the admission policy (Kyverno or OPA Gatekeeper) in `Audit` mode first, letting it log which currently-running or newly-deployed images would fail verification without actually blocking anything, and use that audit data to complete the unsigned-image inventory rather than guessing. Only once that audit period confirms every legitimate image source is covered would I flip the policy to `Enforce`, and even then I'd stage it namespace-by-namespace rather than cluster-wide in one step, starting with the namespaces owning the fully-covered image sources. Throughout, I'd track any necessary policy exceptions explicitly, with an owner and expiry, rather than letting them become permanent silent gaps.
_What the interviewer is probing for:_ A staged, audit-before-enforce rollout methodology that avoids a flag-day outage, and recognition that third-party/base images need a distinct remediation path from internally-built images.

**🎯 Architect:** _"Design an end-to-end supply chain security program for an organization running several hundred microservices across multiple CI systems and cloud providers."_
**Model answer:** I'd standardize the build pipeline's security gates as a shared, reusable pipeline template rather than letting each team implement scanning/signing independently, since consistency across several hundred services is unmanageable otherwise — this template runs Trivy (severity-gated, `--ignore-unfixed`) and generates an SBOM (Syft, SPDX format) on every build, regardless of which underlying CI system or cloud provider a given service uses. For signing, I'd standardize on Sigstore's keyless model tied to each CI system's OIDC identity, since it scales across heterogeneous CI systems without requiring a shared, centrally-managed key store that becomes its own single point of failure. SBOMs get attached as signed Cosign attestations to each image but also pushed to a centralized, queryable SBOM inventory service independent of any registry, so a newly disclosed CVE can be searched against the entire fleet in minutes rather than requiring a live re-scan of every service's current image. Admission-time signature verification rolls out per business-unit or cluster in `Audit` mode first, with a fixed audit period and an explicit sign-off gate before any cluster moves to `Enforce`, and any signing/scanning policy exception requires a named owner and an expiry date, tracked in the same system used for other compliance exceptions rather than as an ad hoc annotation. Finally, I'd build a recurring (not just build-time) re-scan of all currently deployed images against the latest CVE feeds, since a large fleet with long-lived deployments otherwise accumulates unnoticed post-deployment vulnerability exposure between redeploys.
_What the interviewer is probing for:_ Fleet-scale program design across heterogeneous CI/cloud environments, standardization via shared tooling templates rather than per-team reinvention, and treating supply chain security as a continuous, centrally-tracked program rather than a per-image, one-time checklist.

## 12. Common Misconceptions

1. **"A signed image is a safe image."** Signing proves provenance and integrity — that the image is unmodified and came from a known build — not the absence of vulnerabilities; scanning and signing answer different questions and both are necessary.
2. **"Scanning an image once before deployment is sufficient forever."** CVE databases are updated continuously; an image clean at build time can become known-vulnerable later as new CVEs are disclosed, requiring recurring re-scans of already-deployed images.
3. **"SBOMs are just documentation with no real operational use."** A centralized, queryable SBOM inventory is what makes fleet-wide vulnerability identification fast during incident response, versus re-scanning the entire fleet from scratch under time pressure.
4. **"Keyless signing means 'no verification happens.'"** Keyless signing still cryptographically verifies signatures — it simply anchors trust to a short-lived, OIDC-identity-backed certificate per build instead of a long-lived static private key.

## 13. 🔑 Key Takeaways

- Supply chain security establishes trust in an image before deployment, addressing a layer that SecurityContext hardening and sandboxed runtimes (§115) cannot — a hardened but tampered or vulnerable image is still a compromised workload.
- Trivy scans image contents against CVE databases; Cosign/Sigstore cryptographically verifies provenance and integrity; SBOMs provide a queryable inventory of exactly what an image contains — three distinct, complementary controls.
- Scanning and signature enforcement should roll out in audit-then-enforce stages, exactly like the staged-rollout pattern already established for PSA (§78) and seccomp/AppArmor (§114), to avoid flag-day outages.
- Keyless, OIDC-identity-backed signing via Sigstore removes the operational risk of long-lived private key management compared to traditional key-based signing.
- SBOMs must be regenerated on every build and stored centrally to be operationally useful during incident response to newly disclosed CVEs.

## 14. Related Concepts & What's Next

This section closed the loop on establishing trust in a container image before it ever reaches the runtime and spec-level hardening covered in §114 and §115 — Trivy scanning catches known vulnerabilities, Cosign/Sigstore signature verification proves provenance and integrity, and SBOMs make that trust auditable and queryable at fleet scale. Together, §113 through §116 have covered cluster configuration hardening, host-kernel restriction, Pod-spec and runtime isolation, and now image-level supply chain trust — four layers that compound rather than substitute for one another. §117, next, shifts to a complementary but distinct concern: static analysis of the Kubernetes manifests themselves (kube-linter, Kubesec), checking the deployment configuration surrounding a now-trusted, now-hardened image for its own class of misconfiguration risk.

**Next Section:** §117 — `Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md`

# Section 117 (Part 15): Static Analysis of Manifests (kube-linter, Kubesec)

## 1. Definition

**Plain language:** [§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md) established trust in the image itself — scanned for known vulnerabilities, signed for provenance, inventoried via SBOM. But a perfectly trustworthy image can still be deployed with a manifest that runs it as root, mounts the host filesystem, disables all resource limits, or grants a ServiceAccount cluster-admin it never needed. Static analysis of manifests asks a different question than [§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md): not "is this image safe," but "is this deployment configuration itself safe" — and it answers that question before the manifest is ever applied to a cluster, by reading the YAML the same way a linter reads source code.

**Precise definition:** **Static analysis of Kubernetes manifests** is the practice of scanning YAML (or Helm chart templates, Kustomize output) against a ruleset of known misconfiguration patterns, entirely offline, without ever contacting a cluster or admission controller. **kube-linter**, an open-source tool from StackRox (now part of Red Hat), evaluates manifests against built-in checks — missing resource limits, privileged containers, host namespace usage, missing liveness probes, mutable tags — and returns pass/fail per rule, designed to run in CI as a build-gate. **Kubesec** takes a scoring approach instead: it evaluates a manifest against a weighted set of security-relevant fields (`securityContext`, `capabilities`, `resources`, `readOnlyRootFilesystem`) and produces a single numeric score with itemized point deductions, making it easy to track a manifest's security posture trending up or down over time as changes are made.

## 2. Why This Matters

- **Manifest misconfiguration is the most common real-world Kubernetes security failure, and it's entirely preventable before deployment** — a `Deployment` YAML with no `resources` block, no `securityContext`, and `hostNetwork: true` copy-pasted from an example is a far more frequent root cause of an incident than a sophisticated supply-chain attack, and every one of those issues is visible in the YAML text itself without ever running the workload.
- **Catching misconfiguration in CI is dramatically cheaper than catching it at admission time or in production** — a kube-linter failure in a pull-request pipeline costs a developer a few minutes to fix before merge; the same misconfiguration caught by an admission controller ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md), OPA Gatekeeper/Kyverno) blocks a deployment mid-rollout, and if neither catches it, it's now running in production as a live risk.
- **Static analysis and admission control are complementary, not redundant** — a static linter reviews the manifest as written by a developer, in their editor or CI pipeline, before it's ever templated through Helm or merged with Kustomize overlays; admission control ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) evaluates the final, fully-rendered object the API server actually receives. Relying on only one leaves a gap: pure CI-side linting misses drift introduced by cluster-side templating, and pure admission-side enforcement gives a developer no fast local feedback loop.

🔑 **Key Takeaway:** kube-linter and Kubesec shift manifest security review left, into the developer's local workflow and CI pipeline, catching the same class of misconfiguration that Pod Security Admission ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) and policy engines catch at the cluster boundary — but earlier, cheaper to fix, and without requiring a live cluster to evaluate against.

## 3. Prerequisites and Dependencies

This section assumes the Pod Security Standards and SecurityContext hardening fields from [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md) and [§115](./Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md) (privileged, capabilities, runAsNonRoot, readOnlyRootFilesystem) as the vocabulary both kube-linter and Kubesec check against — static analysis largely re-evaluates the same fields, just earlier in the lifecycle and without a cluster. It also assumes the supply chain controls from [§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md) (scanning, signing, SBOM) as the layer this section complements rather than replaces: a signed, scanned, vulnerability-free image can still be paired with an insecure manifest, which is exactly the gap static analysis closes. Basic familiarity with CI/CD pipeline mechanics (Part 13 GitOps coverage) is assumed, since both tools are designed to run as a pipeline step rather than a manual, ad hoc command. Forward-references [§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md), which covers detecting threats at runtime — a workload that passed every static and admission-time check can still behave maliciously once running, which is the gap Falco closes.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────────┐
│  Developer workstation / CI pipeline (pre-cluster, offline)               │
│                                                                           │
│  deployment.yaml  (no cluster contact required)                           │
│        │                                                                  │
│        ├──► kube-linter lint deployment.yaml                              │
│        │      checks: privileged, hostNetwork, missing limits,            │
│        │              missing probes, mutable tag, run-as-root            │
│        │      output: PASS/FAIL per rule                                  │
│        │                                                                  │
│        └──► kubesec scan deployment.yaml                                  │
│               checks: securityContext fields, capabilities,               │
│                       resources, readOnlyRootFilesystem                   │
│               output: numeric score + itemized point deductions           │
│                                                                           │
│  CI gate: fail build if kube-linter reports FAIL on critical rules        │
│           or Kubesec score below threshold                                │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │  manifest passes static checks, proceeds
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  kubectl apply / GitOps sync → API server                                │
│    Admission control (§78 PSA, Kyverno/OPA Gatekeeper) re-evaluates      │
│    the fully-rendered object — catches templating drift static           │
│    analysis on the raw source YAML cannot see                            │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Static analysis runs before the manifest ever reaches Helm templating or Kustomize overlay merging in many pipelines** — meaning it can miss issues introduced only after templating (a values file that injects `privileged: true` for one environment); running a linter against the final rendered output, not just the source template, closes that gap.
- **kube-linter and Kubesec check overlapping but not identical fields** — running both catches a broader set of misconfigurations than either alone, and their different output styles (pass/fail rules versus a weighted score) serve different reporting needs: rule-level detail for developers fixing issues, a trending score for tracking posture over time.
- **Neither tool requires a running cluster or API server access** — this is precisely what makes them suitable for a fast, local, pre-commit or CI check, unlike admission-time enforcement which by definition requires an actual API request against a live cluster.

## 5. Hands-On

### 5.1 Linting a Manifest with kube-linter

**Purpose:** Catch common misconfiguration patterns (privileged containers, missing resource limits, host namespace usage) in raw YAML before it's ever applied to a cluster.

**Syntax:**

```bash
kube-linter lint deployment.yaml
kube-linter lint deployment.yaml --config kube-linter-config.yaml
```

```yaml
# kube-linter-config.yaml — customize which checks run and at what severity
checks:
  addAllBuiltIn: false
  include:
    - "no-read-only-root-fs"
    - "privileged-container"
    - "run-as-non-root"
    - "unset-cpu-requirements"
    - "unset-memory-requirements"
    - "latest-tag"
  exclude:
    - "dnsconfig-with-search-domain-set"
```

**Example usage and expected output:**

```bash
$ kube-linter lint deployment.yaml
deployment.yaml: (object: <no namespace>/myapp apps/v1, Kind=Deployment) container "myapp"
does not have a read-only root file system (check: no-read-only-root-fs, remediation:
Set readOnlyRootFilesystem to true in the container securityContext.)

deployment.yaml: (object: <no namespace>/myapp apps/v1, Kind=Deployment) container "myapp"
has cpu request and limit unset (check: unset-cpu-requirements, remediation:
Set CPU requests and limits for your container based on its expected usage.)

Error: found 2 lint errors
```

**Production usage example:** Teams typically run `kube-linter lint` as a required CI check on every pull request touching a manifest, with a custom config that promotes a curated subset of built-in checks (privileged containers, missing `runAsNonRoot`, `:latest` tags) to build-blocking severity while leaving lower-priority checks as warnings — mirroring the same staged-enforcement philosophy already established for admission policies in [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md).

**Common errors:** Running `kube-linter lint` against a raw Helm chart template directory instead of the fully rendered output (`helm template . | kube-linter lint -`) — the unrendered template contains Go templating syntax (`{{ .Values.replicas }}`) that isn't valid YAML on its own, causing the linter to either error out or silently skip checks it can't parse.

### 5.2 Scoring a Manifest with Kubesec

**Purpose:** Produce a single trackable security score for a manifest, with itemized point deductions, useful for measuring security posture improvement over time rather than just pass/fail gating.

**Syntax:**

```bash
kubesec scan deployment.yaml
# or via the hosted API
curl -sSX POST --data-binary @deployment.yaml https://v2.kubesec.io/scan
```

**Example usage and expected output:**

```bash
$ kubesec scan deployment.yaml
[
  {
    "object": "Deployment/myapp.default",
    "valid": true,
    "message": "Passed with a score of 2 points",
    "score": 2,
    "scoring": {
      "advise": [
        {
          "selector": "containers[] .securityContext .readOnlyRootFilesystem == true",
          "reason": "An immutable root filesystem can prevent malicious binaries being added to PATH"
        },
        {
          "selector": "containers[] .resources .limits .cpu",
          "reason": "Enforcing CPU limits prevents DoS via resource exhaustion"
        }
      ],
      "critical": [
        {
          "selector": "containers[] .securityContext .privileged == true",
          "reason": "Privileged containers can allow almost complete host access"
        }
      ]
    }
  }
]
```

**Production usage example:** A CI pipeline gates the merge on a minimum Kubesec score (for example, requiring a score of at least 5), and the score is tracked over time as a trend metric per team or namespace — making it possible to show measurable improvement in manifest security posture across a quarter, which a binary pass/fail linter alone doesn't surface as cleanly.

**Common errors:** Treating a positive Kubesec score as "secure enough" without reading the itemized `critical` deductions — a manifest can score positively overall while still carrying a `critical`-severity finding (a privileged container) that a numeric threshold alone would not catch if the threshold is set too low relative to the critical-item weighting.

## 6. Production Usage Notes

- **Run static analysis on the fully rendered manifest, not the raw template** — `helm template . | kube-linter lint -` catches issues introduced by values-file overrides that the unrendered chart source doesn't reveal; linting only the template source misses environment-specific misconfiguration.
- **Use kube-linter's pass/fail rules as the CI merge gate and Kubesec's score as a trend metric**, not the other way around — a hard gate needs a deterministic pass/fail signal, while a numeric score is better suited to dashboards tracking posture improvement across teams and time.
- **Pair static analysis with admission control ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) rather than treating either as sufficient alone** — static analysis catches issues at authoring time with fast local feedback, but only admission control sees the final object the API server actually receives, including any drift introduced by GitOps reconciliation or manual `kubectl edit` after deployment.

## 7. Security Considerations

- **A CI-side linter is only as strong as its enforcement — a check configured as a warning instead of a build-blocking failure provides no actual gate**, just a log line nobody reads; critical checks (privileged containers, `runAsNonRoot` violations, host namespace usage) should be configured to fail the build, not merely warn.
- **Static analysis cannot catch runtime behavior or logic bugs — it only evaluates the manifest's declared configuration**, meaning a manifest can pass every kube-linter and Kubesec check while the application itself still contains a vulnerable dependency (caught instead by [§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)'s Trivy scanning) or exhibits malicious behavior only visible once running (caught instead by [§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)'s Falco).
- **Custom rule configuration drift across repositories undermines consistency** — if each team maintains its own kube-linter config with different included/excluded checks, the organization loses the ability to assert a uniform minimum security bar across its manifest fleet; a shared, centrally-maintained config imported by every repository's CI pipeline avoids this.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Cause                                                                                                           | Fix                                                                                                           |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| kube-linter reports parse errors on a Helm chart template file           | Linter was pointed at the raw template source containing unrendered Go templating syntax                        | Render the chart first (`helm template . \| kube-linter lint -`) and lint the fully rendered output           |
| CI pipeline passes despite kube-linter reporting failed checks           | Checks configured as warnings rather than build-blocking, or exit code not checked by the pipeline              | Promote critical checks to blocking severity in the linter config and ensure the CI step checks exit code     |
| Kubesec score looks acceptable but a privileged container still exists   | Numeric threshold set too low relative to the weight of a `critical`-severity deduction                         | Read itemized `critical` findings explicitly, not just the aggregate score, and gate on zero criticals        |
| Same manifest scores differently across two team pipelines               | Each team maintains a divergent kube-linter/Kubesec config with different included checks                       | Centralize a shared, version-controlled config imported by every repository's CI pipeline                     |
| A manifest that passed CI linting is still rejected by admission control | Static analysis ran against the template source; the final rendered object differs after Helm/Kustomize merging | Lint the fully rendered manifest, and treat admission control as the authoritative final check, not redundant |

## 9. Best Practices

- Run both kube-linter and Kubesec in CI, since their overlapping-but-distinct checks catch a broader set of misconfigurations together than either alone.
- Lint the fully rendered manifest (post-Helm-template, post-Kustomize-build), not just the raw source, to catch environment-specific overrides that introduce misconfiguration.
- Configure critical checks (privileged containers, missing `runAsNonRoot`, host namespace usage, `:latest` tags) as build-blocking failures, not warnings.
- Maintain a single shared, version-controlled linter configuration imported across every repository's pipeline, rather than letting each team's config drift independently.
- Treat static analysis as complementary to admission control ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)), not a substitute — static analysis gives fast local feedback, admission control is the authoritative last check against the actual object the API server receives.

## 10. Common Anti-Patterns / Mistakes

- **Configuring kube-linter or Kubesec checks as advisory warnings only**, so a "failing" pipeline still merges and the check provides no real gate.
- **Linting the raw Helm chart template instead of the rendered output**, missing misconfiguration introduced by values-file overrides.
- **Chasing a higher Kubesec score without reading itemized critical findings**, allowing a privileged container or other critical issue to hide behind an acceptable aggregate number.
- **Letting each team maintain its own divergent linter configuration**, losing a consistent organization-wide minimum security bar.
- **Treating a clean static-analysis pass as sufficient security review on its own**, ignoring that it cannot catch runtime behavior, vulnerable dependencies, or admission-time templating drift.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between what kube-linter and Kubesec each report?"_
**Model answer:** kube-linter evaluates a manifest against a set of built-in checks — privileged containers, missing resource limits, host namespace usage, missing probes — and reports each as a pass or fail, designed to run as a CI build-gate that blocks a merge on a rule violation. Kubesec instead evaluates a manifest against a weighted set of security-relevant fields and produces a single numeric score with itemized point deductions for each finding, which is more useful for tracking a manifest's security posture trending up or down over time than for hard pass/fail gating. Both tools run entirely offline against the YAML text, without ever contacting a cluster.
_What the interviewer is probing for:_ Understanding that the two tools serve different reporting purposes — rule-based gating versus trend scoring — rather than being interchangeable.

**🎯 Intermediate:** _"Why would you run static manifest analysis in CI when Pod Security Admission already enforces similar checks at the cluster boundary?"_
**Model answer:** They catch the same class of misconfiguration at very different points in the lifecycle, with very different costs. A kube-linter failure in a pull-request pipeline is visible to the developer in minutes, before the manifest is even merged, and costs almost nothing to fix. The same misconfiguration caught only by Pod Security Admission at deploy time blocks a rollout mid-deployment, after the manifest has already been merged, reviewed, and possibly templated through Helm — a much more expensive point to discover the same issue. Static analysis also runs without needing cluster access at all, which makes it usable in a developer's local workflow or a pre-merge CI job that has no cluster credentials. Relying on admission control alone means every misconfiguration is discovered late; relying on static analysis alone misses drift introduced by templating or manual changes after the manifest left the developer's hands.
_What the interviewer is probing for:_ Recognition that shift-left static analysis and cluster-side admission control are complementary defense-in-depth layers, not redundant duplicate checks.

**🎯 Senior:** _"You inherit a CI pipeline where kube-linter is installed but the team says 'it's not really doing anything.' How do you investigate and fix that?"_
**Model answer:** First I'd check whether the checks are actually configured to fail the build — the most common version of "not doing anything" is a linter that runs, reports findings to a log nobody reads, but exits 0 regardless, or a CI step that runs the linter without checking its exit code at all. Next I'd check whether it's being pointed at the right target — if it's linting raw Helm chart template source rather than the rendered output (`helm template . | kube-linter lint -`), it may be silently failing to parse the templating syntax or only checking a subset of the actual deployed configuration. I'd also check whether the configured ruleset even includes the checks that matter — a default or overly narrow `include` list can mean critical checks like `privileged-container` or `run-as-non-root` were never actually enabled. Once I've confirmed the actual gap, I'd fix it by rendering the full manifest before linting, promoting the critical checks to build-blocking severity, wiring the pipeline to fail on nonzero exit code, and then validating the fix by deliberately introducing a known-bad manifest (a privileged container) in a test branch to confirm the pipeline now actually blocks it — the same fail-closed verification habit that matters for scanning and signing gates in [§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md).
_What the interviewer is probing for:_ A methodical debugging approach to a "security tool that isn't actually enforcing anything" report, and the habit of proving a gate works by testing it against a known-bad input rather than trusting its presence alone.

**🎯 Architect:** _"Design a manifest-governance strategy for an organization with dozens of teams, each maintaining their own Helm charts, where you need a consistent security baseline without blocking every team's ability to move independently."_
**Model answer:** I'd centralize the linting configuration itself as a shared, version-controlled artifact (a small internal package or a pinned config file referenced identically from every team's CI pipeline) rather than letting each team define its own kube-linter and Kubesec rules — this is what prevents configuration drift from silently eroding the organization-wide baseline over time. I'd split checks into two tiers: a small, non-negotiable set of build-blocking rules (privileged containers, `runAsNonRoot` violations, missing resource limits, `:latest` tags) that every team's pipeline enforces identically, and a broader set of advisory checks surfaced as warnings or as a trending Kubesec score per team, giving teams room to improve incrementally without a hard gate on every possible finding. The CI step would always lint the fully rendered chart output, not the raw template, to catch values-file-introduced drift specific to each team's actual deployment configuration. I'd pair this with admission control ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md), Kyverno/OPA Gatekeeper) enforcing the same non-negotiable tier at the cluster boundary as a backstop for anything that bypasses CI (a manual `kubectl apply`, a GitOps reconciliation applying a manifest that was edited outside the normal PR flow). Finally, I'd track the Kubesec trend score per team on a shared dashboard, making security posture visible and comparable across teams without turning every incremental improvement into a blocking gate — preserving each team's velocity while keeping the non-negotiable baseline uniformly enforced.
_What the interviewer is probing for:_ Governance design that balances a uniform non-negotiable baseline against team autonomy, layered defense combining CI-side and admission-side enforcement, and centralized configuration management to prevent per-team drift at scale.

## 12. Common Misconceptions

1. **"kube-linter and Kubesec check the same things, so running one is enough."** Their rule sets overlap but aren't identical, and their output formats serve different purposes — rule-based pass/fail versus a weighted trend score — running both catches a broader set of issues.
2. **"A clean static analysis pass means the manifest is secure."** Static analysis only evaluates the declared YAML configuration; it cannot catch a vulnerable dependency inside the image ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)), templating drift introduced after the linted source (caught by admission control, [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)), or malicious runtime behavior ([§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)).
3. **"Static analysis makes admission control redundant."** Static analysis runs against the authored or rendered manifest before it reaches the cluster; admission control evaluates the final object the API server actually receives, which can differ due to GitOps reconciliation, manual edits, or templating performed after the linted source was checked.
4. **"A positive Kubesec score means no critical issues exist."** The aggregate score can be positive even while a `critical`-severity finding (like a privileged container) is present if the scoring threshold is set without explicitly checking for zero criticals.

## 13. 🔑 Key Takeaways

- kube-linter provides rule-based pass/fail checks suited to a CI build-gate; Kubesec provides a weighted numeric score suited to tracking manifest security posture trends over time — running both catches more than either alone.
- Static analysis shifts the same class of misconfiguration that Pod Security Admission ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) enforces at the cluster boundary left into the developer's local workflow and CI pipeline, where it's dramatically cheaper to fix.
- Static analysis and admission control are complementary layers, not substitutes — static analysis reviews the authored/rendered manifest before it reaches a cluster; admission control is the authoritative check against the final object the API server receives.
- Critical checks (privileged containers, missing `runAsNonRoot`, host namespace usage) must be configured as build-blocking failures, not advisory warnings, or the gate provides no real enforcement.
- Static analysis cannot catch vulnerable dependencies ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)), templating drift introduced after linting, or malicious runtime behavior ([§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)) — it is one layer among several, not a complete security review on its own.

## 14. Related Concepts & What's Next

This section addressed the manifest configuration surrounding a now-trusted, now-hardened image ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)) — kube-linter and Kubesec catch misconfiguration in the YAML itself, offline and before a cluster is ever involved, complementing rather than replacing the admission-time enforcement covered in [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md). Together, [§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) through [§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md) have progressively narrowed the trust boundary: cluster configuration hardening, host-kernel restriction, Pod-spec and runtime isolation, image-level supply chain trust, and now manifest-level static analysis. But every one of those controls evaluates a workload before or at the moment it starts running — none of them can tell you what a workload actually does once it's live. [§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md), next, closes that final gap with runtime security and threat detection using Falco, which observes live system-call and kernel-event behavior to catch a compromise that passed every static and admission-time check clean.

**Next Section:** [§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md) — `Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md`

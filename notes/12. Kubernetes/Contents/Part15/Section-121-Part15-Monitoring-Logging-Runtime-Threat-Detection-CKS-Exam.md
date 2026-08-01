# Section 121 (Part 15): Monitoring, Logging, and Runtime Threat Detection for the CKS Exam

## 1. Definition

**Plain language:** Every mechanism this Part has built — CIS-benchmarked cluster setup (§113), host and container hardening (§114–§115), supply-chain scanning and signing (§116), static manifest analysis (§117), runtime detection with Falco (§118), mesh-enforced mTLS (§119), and encryption-at-rest depth (§120) — is a preventive or detective control operating at a different layer of the stack. None of them, alone, tells a security team "an attack is happening right now" or "here is the evidence trail after the fact." That is the job of monitoring, logging, and runtime threat detection working together as a single observability plane specifically for security events — and it is the capstone of the CKS curriculum precisely because the exam (and real production incident response) expects a candidate to reason about the whole detection-and-response pipeline, not any one tool in isolation.

**Precise definition:** For CKS purposes, **security monitoring and logging** is the combination of the Kubernetes **audit log** (a structured, configurable record of every request made to `kube-apiserver`, defined by an `Audit Policy` specifying which request stages and resource types to log at what verbosity), **Falco** (§118, kernel-syscall-level runtime anomaly detection, generating alerts on suspicious in-container behavior that the audit log — an API-layer mechanism — cannot see at all), and a **centralized aggregation and alerting pipeline** (typically feeding both audit logs and Falco alerts into the same log-shipping and SIEM-style tooling used for the rest of cluster observability, §89–§96, Part 12) that together give a security team the ability to detect an in-progress compromise, reconstruct what happened during an incident, and prove compliance with an audit trail. The CKS exam's "Monitoring, Logging and Runtime Security" domain (20% weight, the joint-highest alongside Supply Chain Security) specifically tests configuring audit policy, interpreting Falco rules and alerts, and reasoning about which layer of this combined pipeline would have caught a given attack scenario.

## 2. Why This Matters

- **The CKS exam's four highest-weighted domains — Minimize Microservice Vulnerabilities (20%), Supply Chain Security (20%), and Monitoring/Logging/Runtime Security (20%) — together account for 60% of the exam**, and this section's synthesis role is making sure the boundary between "prevention" (§113–§117, §119–§120) and "detection" (§118, this section) is crisp, since exam scenarios routinely hinge on correctly identifying which layer of the stack would actually have caught a specific described attack.
- **No preventive control covered in this Part is perfect, and audit logging plus Falco are what turn a missed prevention into a caught detection** — a supply-chain-scanned, CIS-hardened, mTLS-enforced cluster can still be compromised via a zero-day or a misconfiguration nobody caught, and the audit log plus Falco alerts are frequently the only evidence a security team has that anything happened at all.
- **Kubernetes' native audit log and Falco cover genuinely non-overlapping layers** — the audit log sees every API-server request (who did what to which resource, at the control-plane layer) while Falco sees kernel syscalls inside running containers (what a process actually did, at the runtime layer); an attacker who never touches the API server directly (e.g., by exploiting a running application to spawn a shell inside an already-existing Pod) is invisible to the audit log entirely and only visible to Falco.

🔑 **Key Takeaway:** The audit log and Falco are complementary detection layers — the audit log sees API-server-layer activity, Falco sees kernel-syscall-layer activity inside running containers — and neither substitutes for the preventive controls (§113–§117, §119–§120) covered elsewhere in this Part; a mature CKS-aligned security posture requires prevention, detection, and a centralized pipeline correlating both into a single incident-response and compliance view.

## 3. Prerequisites and Dependencies

Synthesizes every section in this Part: §113 (CKS curriculum overview and CIS/kube-bench cluster setup hardening), §114 (system hardening — seccomp, AppArmor), §115 (SecurityContext hardening, gVisor/Kata Containers), §116 (supply chain security — Trivy, Cosign, SBOM), §117 (static manifest analysis — kube-linter, Kubesec), §118 (Falco runtime threat detection), §119 (mTLS and service mesh security), and §120 (encryption-at-rest and external secret stores deep dive). Back-references §89–§96 (Part 12, Observability — the general logging, metrics, and audit-log infrastructure this section's security-specific pipeline builds on) and §75 (RBAC, Part 10, which the audit log's identity fields directly report on). Forward-references §122 (Part 16), which begins service mesh concepts more broadly beyond this Part's security-focused mTLS coverage.

## 4. Architecture Diagram

```text
        THE FULL CKS DETECTION-AND-RESPONSE PIPELINE

  ┌────────────────────────────────────────────────────────────────────────┐
  │  PREVENTIVE LAYER (§113–§117, §119–§120 — this Part's earlier work)    │
  │  CIS/kube-bench │ seccomp/AppArmor │ SecurityContext/gVisor │          │
  │  image scanning/signing │ static manifest analysis │ mTLS │ encryption │
  └───────────────────────────────┬────────────────────────────────────────┘
                                  │  (attacks that get through anyway)
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  DETECTIVE LAYER (this section)                                                 │
  │                                                                                 │
  │  ┌──────────────────────────────┐        ┌──────────────────────────────────┐   │
  │  │ Audit Log (API layer)        │        │ Falco (kernel-syscall layer)     │   │
  │  │  - every kube-apiserver      │        │  - process spawns, file reads    │   │
  │  │    request, per Audit Policy │        │  - unexpected outbound conns     │   │
  │  │  - who/what/when/verb        │        │  - privilege escalation attempts │   │
  │  │  - sees: RBAC actions,       │        │  - sees: in-container behavior   │   │
  │  │    Secret reads, RBAC changes│        │    invisible to the API server   │   │
  │  └───────────┬──────────────────┘        └───────────┬──────────────────────┘   │
  │              │                                       │                          │
  │              └──────────────┬────────────────────────┘                          │
  │                             ▼                                                   │
  │              ┌───────────────────────────────────────────┐                      │
  │              │ Centralized aggregation pipeline          │                      │
  │              │ (Fluent Bit/Loki/SIEM, §94, Part 12)      │                      │
  │              │  - correlates audit + Falco events        │                      │
  │              │  - alerting, dashboards, retention        │                      │
  │              │  - the evidence trail for incident review │                      │
  │              └───────────────────────────────────────────┘                      │
  └─────────────────────────────────────────────────────────────────────────────────┘
```

- **An attack that never issues a `kube-apiserver` request — for example, exploiting an already-running application's own vulnerability to spawn a reverse shell inside its container — is completely invisible to the audit log**, since the audit log only records API-server activity; this exact gap is what makes Falco's kernel-syscall visibility a non-redundant, complementary layer rather than a nice-to-have duplicate.
- **Conversely, an attack conducted entirely through legitimate-looking API calls — an over-privileged ServiceAccount token being used to read every Secret in a namespace, say — produces no unusual syscall activity Falco would flag, but is fully visible in the audit log** as a sequence of `get`/`list` requests against the `secrets` resource.
- **Neither layer alone gives a complete incident-response picture** — reconstructing "how did the attacker get in, and what did they do once inside" typically requires correlating both audit-log entries (the entry point, if API-driven) and Falco alerts (in-container behavior after the fact), which is exactly why the centralized aggregation layer at the bottom of this diagram matters as much as either detection source individually.

## 5. Hands-On

### 5.1 Configuring an Audit Policy Targeting Security-Relevant Events

**Purpose:** Define which API requests the audit log actually records, and at what verbosity, focusing specifically on the security-relevant resource types (Secrets, RBAC objects, exec/attach requests) a CKS-aligned review cares about most.

**Syntax:**

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["secrets"]
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources: ["*"]
  - level: Request
    resources:
      - group: ""
        resources: ["pods/exec", "pods/attach"]
  - level: Metadata
```

```bash
# referenced by kube-apiserver flags:
kube-apiserver \
  --audit-policy-file=/etc/kubernetes/audit/audit-policy.yaml \
  --audit-log-path=/var/log/kubernetes/audit.log \
  --audit-log-maxage=30 \
  --audit-log-maxbackup=10
```

**Example usage:**

```bash
$ kubectl exec -it suspicious-pod -- /bin/sh
$ tail -f /var/log/kubernetes/audit.log | grep "pods/exec"
{"kind":"Event","verb":"create","objectRef":{"resource":"pods","subresource":"exec","name":"suspicious-pod","namespace":"default"},"user":{"username":"jane@example.com"},"requestReceivedTimestamp":"2026-07-31T10:02:11Z",...}
# a full record: who, exactly what action, on which Pod, at exactly what time
```

**Production usage example:** Auditing Secret reads at `RequestResponse` level (capturing both request and response bodies) is deliberately more verbose than the `Metadata`-only catch-all rule at the bottom of the policy, since a security review specifically needs to know not just that a Secret was read but by whom, when, and — critically — the response confirms the read actually succeeded rather than being denied by RBAC; this is the audit-log equivalent of the RBAC-and-Secret-exposure concern §75 and §80 both raised, made concretely traceable after the fact.

**Common errors:** Setting every rule to `RequestResponse` level indiscriminately, including for high-volume, low-security-value resources like Pod status updates — this generates enormous audit log volume, degrades API server performance, and buries the genuinely security-relevant events (Secret reads, RBAC changes, exec/attach) in noise; the policy's rule ordering and per-resource-type verbosity is itself a security design decision, not just a technical one.

### 5.2 Correlating a Falco Alert with the Audit Log During Incident Response

**Purpose:** Demonstrate the actual investigative workflow — using a Falco alert's contextual detail to locate the corresponding audit-log entries and reconstruct the full incident timeline.

**Syntax:**

```yaml
# example Falco alert output (from §118's rule engine)
{
  "time": "2026-07-31T10:02:09.412Z",
  "rule": "Terminal shell in container",
  "output": "A shell was spawned in a container (user=root container_id=8f3a...
    container_name=suspicious-pod image=my-registry/app:1.4)",
  "priority": "Warning",
}
```

```bash
# correlate against the audit log using the timestamp and Pod name:
grep "suspicious-pod" /var/log/kubernetes/audit.log | \
  jq -r 'select(.requestReceivedTimestamp > "2026-07-31T10:01:00Z") |
    "\(.requestReceivedTimestamp) \(.user.username) \(.verb) \(.objectRef.resource)"'
```

**Example usage:**

```bash
$ grep "suspicious-pod" /var/log/kubernetes/audit.log | jq -r '...'
2026-07-31T10:02:11Z jane@example.com create pods/exec
2026-07-31T10:02:09Z jane@example.com create pods/exec
# the audit log confirms the exec request that immediately preceded Falco's
# "Terminal shell in container" alert — the entry point (jane@example.com's
# credential, via kubectl exec) is now correlated with the runtime signal
```

**Production usage example:** In a real incident, this correlation step is what distinguishes "we know a shell was spawned in this container" (Falco alone) from "we know exactly whose credential, via what API action, caused it" (Falco correlated with the audit log) — the second is what actually drives remediation (revoke `jane@example.com`'s credential, review why that identity had `exec` permission on this Pod at all via RBAC, §75) rather than just containing the immediate runtime threat.

**Common errors:** Investigating a Falco alert in isolation without checking the audit log for the corresponding time window — this misses the actual entry vector entirely if the attack was API-driven (as in this example), leading a team to contain the symptom (kill the Pod) without addressing the root cause (an over-privileged identity that still has the same access afterward).

### 5.3 Enforcing a CIS-Benchmark Baseline as a Continuous Monitoring Check

**Purpose:** Run `kube-bench` (introduced in §113) not as a one-time cluster-setup check but as a recurring, scheduled compliance verification feeding into the same centralized monitoring pipeline as audit logs and Falco alerts.

**Syntax:**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: kube-bench-scheduled
  namespace: security
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          hostPID: true
          containers:
            - name: kube-bench
              image: aquasec/kube-bench:latest
              command: ["kube-bench", "run", "--json"]
              volumeMounts:
                - name: var-lib-etcd
                  mountPath: /var/lib/etcd
                  readOnly: true
          restartPolicy: Never
          volumes:
            - name: var-lib-etcd
              hostPath:
                path: /var/lib/etcd
```

**Example usage:**

```bash
$ kubectl create -f kube-bench-cronjob.yaml
cronjob.batch/kube-bench-scheduled created

$ kubectl logs job/kube-bench-scheduled-29384712 -n security | jq '.Totals'
{"total_pass": 58, "total_fail": 2, "total_warn": 3, "total_info": 0}
# fed into the same aggregation pipeline as audit logs and Falco alerts,
# so a drift from the CIS baseline (§113) is itself a monitored, alertable event
```

**Production usage example:** Treating CIS-benchmark compliance as a continuously monitored signal, rather than a one-time cluster-setup verification, catches configuration drift — a control-plane flag accidentally reverted during an upgrade (§109, Part 14), or a node rebuilt from an outdated image — as it happens, rather than discovering it only during the next scheduled security audit or, worse, during an actual incident's post-mortem.

**Common errors:** Running `kube-bench` only once during initial cluster setup and never again — CIS compliance is a point-in-time snapshot, not a permanent property of the cluster, and configuration drift over the cluster's operational lifetime (upgrades, manual `kubectl edit` interventions, node replacements) can silently regress a previously compliant baseline.

## 6. Production Usage Notes

- **The audit log's volume and verbosity settings are themselves a capacity-planning concern** — `RequestResponse`-level logging on high-traffic resource types can meaningfully impact API server performance and generate log volumes requiring real storage and retention planning; a well-designed `Audit Policy` is deliberately tiered, matching verbosity to actual security value per resource type, as shown in the policy above.
- **Falco alerts and audit-log entries should land in the same centralized pipeline as the rest of cluster observability (§89–§96, Part 12)**, not a separate, siloed security-only system — correlating a security event against ordinary application logs and metrics from the same time window is often what confirms or rules out a false positive.
- **A recurring, scheduled `kube-bench` run (as opposed to a one-time setup check) turns CIS-benchmark compliance from a point-in-time attestation into a continuously monitored signal**, catching configuration drift across upgrades and manual interventions over the cluster's operational lifetime.

## 7. Security Considerations

- **The audit log itself is a sensitive asset and a potential attacker target** — an attacker with sufficient access who can modify or delete audit log files (or disable audit logging outright before acting) can erase the evidence trail of their own activity; the audit log's storage should be shipped off-node immediately and access-restricted with the same rigor as any other security-critical asset.
- **Falco's detection is only as good as its rule set** — out-of-the-box rules cover common attack patterns, but a mature CKS-aligned posture requires custom rules tuned to the specific applications running in the cluster, since a generic rule set will miss application-specific anomalous behavior and may also generate excessive false positives on legitimate but unusual application activity.
- **None of the detective controls in this section (audit log, Falco, scheduled kube-bench) prevent an attack — they only make it visible after the fact (or, in Falco's case, in near-real-time during it)** — a security program that invests in detection without also maintaining the preventive controls from §113–§117 and §119–§120 is only ever finding out about compromises, never actually reducing how many occur.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Cause                                                                                                                  | Fix                                                                                                                                                 |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Audit log shows no entries for a suspected exec-based compromise         | `Audit Policy` doesn't include a rule matching `pods/exec`, or logs are filtered out at `None` level for that resource | Add an explicit `Request`-or-higher-level rule targeting `pods/exec` and `pods/attach`                                                              |
| Falco flags an alert but the audit log shows nothing corresponding to it | The attack never went through the API server (e.g., a shell spawned by exploiting the running application directly)    | This is expected — Falco is the only layer that would catch a non-API-driven attack; investigate via container/process forensics, not the audit log |
| API server performance degrades noticeably after enabling audit logging  | Audit Policy set to `RequestResponse` level indiscriminately across high-traffic resource types                        | Tier verbosity per resource type — high verbosity only for genuinely security-relevant resources (Secrets, RBAC, exec)                              |
| `kube-bench` shows a previously-passing control now failing              | Configuration drift — an upgrade, manual edit, or node rebuild reverted a hardening setting                            | Investigate the specific control's remediation from the CIS benchmark and re-apply; treat as a monitored, alertable event, not a one-time fix       |

## 9. Best Practices

- Tier `Audit Policy` verbosity deliberately by resource type — high verbosity (`RequestResponse`) for Secrets, RBAC objects, and exec/attach; lower verbosity (`Metadata`) as a catch-all for everything else.
- Ship audit logs and Falco alerts off-node to a centralized, access-restricted pipeline immediately, since an attacker with sufficient node access can otherwise erase or tamper with local evidence.
- Correlate Falco alerts against the audit log's corresponding time window during every incident investigation, rather than treating either signal in isolation.
- Run CIS-benchmark verification (`kube-bench`) on a recurring schedule, not just at initial cluster setup, to catch configuration drift.
- Tune Falco's rule set to the specific applications running in the cluster rather than relying solely on out-of-the-box rules, to reduce both false negatives and false positives.

## 10. Common Anti-Patterns / Mistakes

- **Enabling `RequestResponse`-level audit logging indiscriminately across every resource type**, degrading API server performance and burying genuinely security-relevant events in noise.
- **Investigating a Falco alert without checking the audit log for the corresponding time window**, missing the actual entry vector when an attack is API-driven.
- **Running `kube-bench` only once during initial cluster setup**, treating CIS compliance as a permanent property rather than something that drifts over the cluster's operational lifetime.
- **Relying on detection alone (audit log, Falco, scheduled compliance checks) without maintaining the preventive controls from earlier in this Part**, finding out about compromises without ever reducing how many occur.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between what the Kubernetes audit log sees and what Falco sees?"_
**Model answer:** The audit log records every request made to the kube-apiserver — who did what, to which resource, at what time — so it's an API-layer record. Falco, by contrast, monitors kernel syscalls happening inside running containers — process spawns, file reads, network connections — so it's a runtime layer record. An attacker interacting purely through the Kubernetes API (like reading Secrets with a stolen token) shows up in the audit log but generates no unusual syscall activity Falco would flag. An attacker who exploits a running application to spawn a shell inside its own container never touches the API server at all, so the audit log sees nothing, but Falco catches the anomalous process spawn immediately. They're complementary, not overlapping.
_What the interviewer is probing for:_ Clear understanding that these are two genuinely different layers of visibility, not redundant tools.

**🎯 Intermediate:** _"How would you design an Audit Policy that balances security visibility against API server performance overhead?"_
**Model answer:** I'd tier verbosity per resource type rather than applying one blanket level everywhere. Genuinely security-relevant resources — Secrets, RBAC objects (Roles, RoleBindings, ClusterRoles), and exec/attach subresources — get `RequestResponse` level, capturing both the request and the response body, since for these I need to know not just that an action was attempted but whether it actually succeeded. Everything else falls under a lower-verbosity catch-all, typically `Metadata` level, which still records who-did-what-when without the overhead of logging full request/response bodies for high-volume, lower-security-value traffic like routine Pod status updates. This keeps the log focused on what actually matters for a security review while avoiding the API server performance degradation and storage costs of logging everything at maximum verbosity.
_What the interviewer is probing for:_ Practical judgment about balancing thoroughness against operational cost, and correct prioritization of which resources actually warrant high-verbosity logging.

**🎯 Senior:** _"During an incident, Falco alerts on a 'terminal shell in container' event, but a quick audit-log check shows nothing unusual around that timestamp. How do you proceed?"_
**Model answer:** That combination is actually expected and informative on its own — it tells me the attacker likely never issued a request to the kube-apiserver at all, meaning the entry vector wasn't a stolen credential or an over-privileged ServiceAccount being used via `kubectl exec`. Instead, it points toward the shell being spawned from inside the container itself, most likely through an application-level vulnerability (a remote code execution bug in the running service, for instance) that let the attacker execute commands directly without ever touching the Kubernetes control plane. My investigation would pivot away from the audit log — which has genuinely nothing more to tell me here — toward container and application forensics: reviewing the application's own logs for the exploited request, checking the image (§116's supply-chain scanning) for a known vulnerability that matches, and using the SecurityContext and any seccomp/AppArmor profile (§114, §115) in place to understand what the resulting shell was actually capable of doing given the container's constraints. This is a good concrete example of why relying on the audit log alone for incident response would have completely missed this class of attack.
_What the interviewer is probing for:_ Ability to reason correctly about what an absence of audit-log evidence actually implies, and to pivot the investigation toward the correct detection layer rather than assuming the audit log should have caught everything.

**🎯 Architect:** _"You're building the complete security observability strategy for a CKS-aligned platform serving multiple regulated business units. Design the end-to-end pipeline from prevention through detection to compliance reporting."_
**Model answer:** I'd structure this as three explicit layers, matching this Part's overall arc. First, prevention: CIS-benchmarked cluster setup verified continuously via scheduled `kube-bench` runs (not just at initial setup), SecurityContext hardening and seccomp/AppArmor profiles enforced via Pod Security Admission (§78, Part 10) and OPA/Gatekeeper-style policy at admission time, supply-chain scanning and signing (§116) gating what images can even be deployed, static manifest analysis (§117) gating what configurations can be applied, mTLS (§119) enforced mesh-wide in `STRICT` mode, and KMS v2 envelope encryption (§120) for every Secret. Second, detection: a tiered `Audit Policy` capturing `RequestResponse`-level detail for Secrets, RBAC, and exec/attach with lower verbosity elsewhere, and Falco deployed cluster-wide with a custom rule set tuned to each business unit's actual application behavior, not just the default rules. Third, the pipeline itself: both audit logs and Falco alerts ship immediately, off-node, into a centralized aggregation and SIEM-style system alongside the general observability stack (§89–§96, Part 12) — with strict access control and immutability on that log store itself, since it's both an incident-response asset and a potential attacker target if tampering is possible. For compliance reporting across regulated business units, I'd build dashboards correlating kube-bench compliance trend lines, audit-log-derived RBAC-change history, and Falco alert volume/severity over time, giving each business unit's compliance team an evidence trail that satisfies audit requirements without needing direct cluster access themselves. Crucially, I'd treat this whole pipeline as validating the preventive layer's effectiveness over time — if Falco or the audit log routinely catches the same class of incident, that's a signal the corresponding preventive control (image scanning policy, admission policy, network policy) needs strengthening, closing the loop between detection and prevention rather than treating them as permanently separate concerns.
_What the interviewer is probing for:_ Ability to design a genuinely end-to-end security architecture spanning this entire Part's scope, correct layering of prevention and detection, and the mature insight that detection findings should feed back into strengthening prevention rather than being treated as a permanent, static cost of doing business.

## 12. Common Misconceptions

1. **"Falco and the audit log cover the same ground, just at different verbosity."** They cover genuinely different layers — API-server requests versus in-container kernel syscalls — and an attack visible to one is frequently invisible to the other entirely.
2. **"Enabling maximum audit-log verbosity everywhere is the most secure configuration."** It degrades API server performance, generates excessive log volume, and buries genuinely security-relevant events in noise from routine, low-value traffic.
3. **"A single kube-bench run at cluster setup is sufficient for ongoing CIS compliance."** Configuration drift from upgrades, manual interventions, and node rebuilds can silently regress a previously compliant baseline; compliance verification needs to be continuous, not a one-time check.
4. **"Detection tooling (audit log, Falco) is a substitute for the preventive controls covered earlier in this Part."** Detection only makes a compromise visible, during or after the fact — it does not reduce how often compromises occur; that requires the preventive controls from §113–§117 and §119–§120 to actually be maintained.

## 13. 🔑 Key Takeaways

- The audit log (API-server-layer visibility) and Falco (kernel-syscall-layer visibility inside running containers) are complementary, non-overlapping detection sources — an attack invisible to one is frequently fully visible to the other.
- `Audit Policy` verbosity should be deliberately tiered by resource type — high verbosity for Secrets, RBAC, and exec/attach; lower verbosity as a catch-all — to balance security visibility against API server performance and log volume.
- Effective incident response requires correlating Falco alerts against the audit log's corresponding time window, since neither source alone gives a complete picture of an attacker's entry vector and in-container actions.
- CIS-benchmark compliance (`kube-bench`) should be verified on a recurring, scheduled basis, not just at initial cluster setup, since configuration drift over the cluster's operational lifetime can silently regress a previously hardened baseline.
- This Part's entire arc — CIS-benchmarked setup (§113), host and container hardening (§114–§115), supply-chain security (§116), static analysis (§117), Falco runtime detection (§118), mTLS (§119), and encryption depth (§120) — is a layered defense where detection (this section) exists specifically to catch what prevention misses, and detection findings should feed back into strengthening the preventive layer over time.

## 14. Related Concepts & What's Next

This section, the capstone of Part 15, synthesized every mechanism covered across this Part's CKS-aligned deep dive — cluster setup hardening (§113), system and microservice hardening (§114–§115), supply chain security (§116), static manifest analysis (§117), Falco runtime detection (§118), mTLS and service mesh security (§119), and encryption-at-rest depth (§120) — into a single monitoring, logging, and runtime-threat-detection view, establishing that the audit log and Falco cover genuinely complementary layers of visibility and that neither substitutes for the preventive controls maintained elsewhere in this Part. With Part 15's CKS-focused security depth complete, Part 16 shifts to service mesh, multi-cluster, and enterprise patterns, beginning with the sidecar proxy pattern this Part's mTLS coverage (§119) already introduced in a security-specific context, now expanded into its full traffic-management and observability scope.

**Next Section:** §122 — `Section-122-Part16-Service-Mesh-Concepts-Sidecar-Proxy-Pattern.md`

# Section 118 (Part 15): Runtime Security and Threat Detection (Falco)

## 1. Definition

**Plain language:** [§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md) closed the loop on everything that can be checked before a workload runs — the image is scanned and signed, the manifest is linted and scored. But all of that is evaluation of a static artifact and its declared configuration. Nothing so far actually watches what a container does once it's live. A container that passed every scan, every signature check, and every manifest lint can still, once running, open a reverse shell, spawn an unexpected shell process, read `/etc/shadow`, or start making outbound connections to an unfamiliar host — behavior no static check could have predicted, because it only exists at runtime.

**Precise definition:** **Runtime security** is the practice of continuously observing a running workload's actual system-call and kernel-event behavior, and comparing that behavior against a ruleset of known-suspicious patterns, to detect a compromise (or a misconfiguration exploited in practice) that every prior static gate missed. **Falco**, a CNCF graduated project originally built by Sysdig, is the dominant open-source tool for this: it taps into kernel-level system-call activity (via an eBPF probe or a kernel module) across every container on a node, evaluates each event stream against a YAML-defined rules engine, and emits an alert the moment a rule matches — a shell spawned inside a container, a sensitive file read, an unexpected outbound network connection, a privilege escalation attempt — all in near real time, while the offending process is still running.

## 2. Why This Matters

- **Every control covered so far in Part 15 evaluates a workload before or at the instant it starts — none of them can see what happens five minutes, five hours, or five days into a container's lifetime**, and a sufficiently patient or sophisticated attacker specifically exploits that blind spot; runtime detection is the only layer in this entire sequence of sections that observes actual, ongoing behavior rather than a point-in-time declaration or artifact.
- **A compromise doesn't have to originate from a supply-chain failure or a manifest misconfiguration to happen — it can start from something entirely legitimate, like an exploited application-layer vulnerability in code that passed every scan**, at which point the attacker is now executing arbitrary commands inside an already-running, already-trusted container; only runtime observation of the resulting process activity (an unexpected shell, an unexpected outbound connection) has any chance of catching that.
- **Mean-time-to-detect is one of the most consequential metrics in real incident response, and static controls alone cannot move it** — a scan run at build time tells you nothing about a container that's been running in production for three months; Falco's real-time alerting is what turns "we discovered this breach during next quarter's audit" into "we were alerted within seconds of the anomalous shell being spawned."

🔑 **Key Takeaway:** Falco observes actual kernel-level behavior of running containers against a rules engine, catching the class of compromise that image scanning ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)), signing ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)), and manifest linting ([§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)) structurally cannot — because those controls evaluate artifacts and declarations, while Falco evaluates what a workload is actually doing, continuously, for as long as it runs.

## 3. Prerequisites and Dependencies

This section assumes the full progression of Part 15's prior layers — cluster hardening, host-kernel restriction (seccomp/AppArmor, [§114](./Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md)), SecurityContext and sandboxed runtimes ([§115](./Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)), supply chain trust ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)), and manifest static analysis ([§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)) — as the controls that narrow risk before and at deployment time; Falco is positioned explicitly as the layer that assumes all of those can still fail or be bypassed and watches for the resulting behavior anyway. It assumes basic familiarity with Linux system calls and kernel-level tracing concepts (eBPF, at a conceptual level) from the Linux knowledge base, since Falco's core mechanism is a kernel-event stream, not a Kubernetes-API-level observation. It also assumes familiarity with basic Kubernetes DaemonSet deployment (Part 4/5), since Falco runs as a DaemonSet with one instance per node to observe that node's local container activity. Forward-references [§119](./Section-119-Part15-Network-Security-Deep-Dive-mTLS-Service-Mesh-Security.md), which covers network-security-layer detection (mTLS, service mesh) as a complementary but distinct concern from the host/process-level detection this section addresses.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────┐
│  Node                                                                 │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ Container A  │  │ Container B  │  │ Container C  │   ... every     │
│  │ (workload)   │  │ (workload)   │  │ (workload)   │       container │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   on this node  │
│         │  syscalls       │  syscalls       │  syscalls               │
│         ▼                 ▼                 ▼                         │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │  Linux kernel                                                 │    │
│  │    eBPF probe (or kernel module) taps every syscall           │    │
│  └──────────────────────────┬────────────────────────────────────┘    │
│                             ▼                                         │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │  Falco DaemonSet pod (one per node)                           │    │
│  │    - receives syscall event stream                            │    │
│  │    - evaluates events against rules.yaml                      │    │
│  │      e.g. "Terminal shell in container"                       │    │
│  │           "Read sensitive file"                               │    │
│  │           "Unexpected outbound connection"                    │    │
│  │    - on match → emits alert (stdout, syslog, gRPC, webhook)   │    │
│  └──────────────────────────┬────────────────────────────────────┘    │
└─────────────────────────────┼─────────────────────────────────────────┘
                              ▼  alert (near real time, seconds not hours)
┌───────────────────────────────────────────────────────────────────────┐
│  Falcosidekick → routes alerts to Slack / SIEM / PagerDuty / webhook  │
└───────────────────────────────────────────────────────────────────────┘
```

- **Falco runs one instance per node, as a DaemonSet, because system-call observation is inherently node-local** — it taps kernel events on the node it runs on, so cluster-wide coverage requires an instance on every node, not a single centralized deployment.
- **The eBPF probe is now the standard collection mechanism over the older kernel module**, since eBPF runs in a sandboxed, verified execution context in-kernel without requiring a custom kernel module to be compiled and loaded for the exact running kernel version — a meaningfully lower operational and stability risk on production nodes.
- **Falco itself only detects and alerts — it does not, by default, block or kill the offending process.** Response actions (terminating a pod, network-isolating a node) require a separate response pipeline, commonly built with Falcosidekick routing alerts to an automation tool.

## 5. Hands-On

### 5.1 Writing and Deploying a Falco Rule

**Purpose:** Detect a specific suspicious behavior — an interactive shell spawned inside a container — by defining a rule that matches the relevant syscall pattern.

**Syntax:**

```yaml
# custom-rules.yaml
- rule: Terminal shell in container
  desc: A shell was spawned inside a container, which is unusual for most production workloads
  condition: >
    spawned_process and container and
    proc.name in (bash, sh, zsh) and
    not proc.pname in (expected_parent_procs)
  output: >
    Shell spawned in container (user=%user.name container=%container.name
    shell=%proc.name parent=%proc.pname cmdline=%proc.cmdline)
  priority: WARNING
  tags: [container, shell]
```

```bash
# Deploy Falco with the custom rule file mounted via Helm
helm install falco falcosecurity/falco \
  --namespace falco --create-namespace \
  --set customRules."custom-rules\.yaml"="$(cat custom-rules.yaml)"
```

**Example usage and expected output:**

```bash
$ kubectl exec -it myapp-pod -- /bin/sh
/ # whoami
root

# On the Falco DaemonSet pod's logs, near-instantly:
$ kubectl logs -n falco daemonset/falco --tail=5
12:04:31.221739034: Warning Shell spawned in container
(user=root container=myapp-pod shell=sh parent=containerd-shim cmdline=sh)
```

**Production usage example:** Production rule sets typically extend the built-in `Terminal shell in container` rule with an explicit allowlist of legitimate debug-tooling parent processes or namespaces (a sanctioned `kubectl debug` ephemeral container workflow, for instance), so the alert fires only for genuinely unexpected shell activity rather than every routine operational debugging session, which would otherwise drown the signal in noise.

**Common errors:** Deploying Falco's default rule set unmodified in a cluster with heavy legitimate debugging or exec-based tooling activity — teams commonly get flooded with WARNING-level alerts for routine, sanctioned `kubectl exec` sessions, and without tuning the rules to distinguish sanctioned from unsanctioned shell activity, the signal-to-noise ratio degrades until the team starts ignoring Falco alerts entirely.

### 5.2 Routing Alerts to a Response Pipeline with Falcosidekick

**Purpose:** Turn a raw Falco alert into an actionable notification or automated response, since Falco itself only detects and logs — it does not act.

**Syntax:**

```yaml
# falcosidekick values (Helm)
falcosidekick:
  enabled: true
  config:
    slack:
      webhookurl: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
      minimumpriority: "warning"
    webhook:
      address: "http://incident-response-svc.security.svc.cluster.local/falco-alert"
      minimumpriority: "critical"
```

```bash
helm upgrade falco falcosecurity/falco \
  --namespace falco \
  --set falcosidekick.enabled=true \
  -f falcosidekick-values.yaml
```

**Example usage and expected output:**

```text
# Slack channel #security-alerts receives:
[Falco] WARNING — Shell spawned in container
container=myapp-pod-7d9f8 namespace=production
shell=sh parent=containerd-shim cmdline=sh
node=worker-03
```

**Production usage example:** A common production pattern routes `WARNING`-priority alerts to a Slack channel for human triage, while `CRITICAL`-priority alerts (a rule specifically tuned to detect known attack-technique patterns, like a container attempting to read cloud-provider metadata service credentials) trigger a webhook into an automated response pipeline that can immediately cordon the affected node or isolate the pod's network policy, treating the highest-confidence alerts as actionable in seconds rather than waiting for a human to see a Slack message.

**Common errors:** Wiring every Falco alert, regardless of priority, into a single high-urgency paging channel — this reliably produces alert fatigue within days, since Falco's default rule set includes many legitimate-but-unusual events at lower severities; alerts should be routed and prioritized by severity, with only genuinely high-confidence, high-severity rules driving an urgent page.

## 6. Production Usage Notes

- **Tune the default rule set before relying on it, don't deploy it as-is** — Falco ships with a broad default rule set intended as a starting point, and production clusters almost always need to add allowlists for legitimate debug tooling, CI-driven exec sessions, and internal automation that would otherwise trigger constant false positives on rules like `Terminal shell in container`.
- **Falco detects; it does not remediate on its own** — a real runtime security posture requires a response pipeline (commonly Falcosidekick routing to Slack, a SIEM, or a webhook-triggered automation) layered on top, since an alert nobody sees or nobody has an automated response for provides limited practical value beyond a historical audit log.
- **Run Falco as a DaemonSet with resource requests/limits set deliberately** — since it observes every syscall on every container on a node, an under-provisioned Falco pod under high syscall volume can itself become a resource-contention or dropped-event-rate problem; monitor Falco's own dropped-events metric as a signal of whether the deployment is under-resourced for the node's actual workload density.

## 7. Security Considerations

- **Falco's own DaemonSet requires privileged access to observe kernel-level syscalls across the node** — this makes the Falco deployment itself a high-value target and a component that must be hardened and tightly access-controlled, since compromising the Falco pod would grant an attacker visibility into (and potential ability to blind) the cluster's own runtime detection layer.
- **An alert with no response action wired to it is a false sense of security** — logging a `CRITICAL` alert to a location nobody actively monitors provides the appearance of runtime security coverage without the substance; alert routing and an on-call or automated response process are not optional add-ons, they're what makes detection operationally meaningful.
- **Runtime detection is inherently reactive, not preventive** — by the time Falco fires an alert, the suspicious syscall has already executed; this doesn't replace preventive controls ([§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) through [§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)), it catches what got past them, and the response time between alert and remediation still determines the actual blast radius of a real compromise.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Cause                                                                                                            | Fix                                                                                                                                 |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Falco alert channel is flooded with routine noise, team starts ignoring it | Default rule set deployed unmodified, matching legitimate debug/exec/CI activity as suspicious                   | Tune rules with an explicit allowlist for sanctioned tooling and parent processes; route by severity, not everything to one channel |
| Falco pod reports dropped events under load                                | DaemonSet under-provisioned for the node's actual syscall volume                                                 | Increase Falco's resource requests/limits and monitor the dropped-events metric to confirm sufficient headroom                      |
| No alert fired for a known-bad test activity (a manual shell spawn)        | Rule was tuned too permissively, or the specific behavior isn't covered by any enabled rule                      | Review and test the rule set against deliberate known-bad activity in a non-production namespace to confirm coverage                |
| CRITICAL alerts generate a Slack message but no actual remediation happens | No automated or human response pipeline wired to the alert beyond the notification itself                        | Wire high-confidence CRITICAL alerts to an automated response (node cordon, NetworkPolicy isolation) or a defined on-call process   |
| Falco DaemonSet pod fails to start on a subset of nodes                    | Underlying kernel version incompatible with the loaded kernel module (older deployment mode) or eBPF unsupported | Use the modern eBPF probe driver, which has broader kernel compatibility than the legacy kernel module                              |

## 9. Best Practices

- Tune Falco's default rule set with an explicit allowlist for sanctioned debug tooling and automation before relying on it in production, to avoid alert fatigue from day one.
- Route alerts by severity through Falcosidekick — lower-priority findings to a monitored channel for triage, high-confidence critical findings to an automated or paged response path.
- Deploy Falco using the eBPF probe driver rather than the legacy kernel module, for broader kernel-version compatibility and lower operational risk on production nodes.
- Monitor Falco's own dropped-event rate as a signal of whether the DaemonSet is adequately resourced for the node's actual syscall volume.
- Periodically test the rule set against deliberate known-bad activity in a non-production namespace, the same fail-closed verification discipline already established for scanning and signing gates in [§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md), to confirm detection actually fires as designed.

## 10. Common Anti-Patterns / Mistakes

- **Deploying Falco's default rule set unmodified and being surprised by alert fatigue** within days as routine debug and CI activity triggers constant false positives.
- **Treating Falco alerts as sufficient without any wired response pipeline**, leaving even `CRITICAL`-priority findings as log lines nobody actively monitors.
- **Routing every alert regardless of severity into a single urgent-paging channel**, guaranteeing the team starts ignoring the channel entirely within a short time.
- **Never testing the rule set against known-bad activity**, discovering only during a real incident that a rule intended to catch a specific behavior was too narrowly or too permissively written.
- **Treating runtime detection as a substitute for preventive controls** rather than the reactive last layer that catches what got past image scanning, signing, and manifest linting.

## 11. Interview Questions

**🎯 Beginner:** _"What does Falco actually do, and how is it different from the image scanning covered in Trivy?"_
**Model answer:** Trivy is a static, point-in-time check — it scans an image's contents against known-vulnerability databases before the image is ever deployed, and its result doesn't change unless the image itself changes or is re-scanned. Falco is the opposite: it's a continuous, real-time observer of a container's actual behavior once it's already running, watching kernel-level system calls — process spawns, file reads, network connections — against a rules engine, and alerting the moment something matches a suspicious pattern. Trivy answers "does this image contain known vulnerabilities," a question with a fixed answer at scan time; Falco answers "what is this specific running container actually doing right now," a question that can change from one second to the next.
_What the interviewer is probing for:_ Clear understanding of static, point-in-time analysis versus continuous runtime observation as fundamentally different security control types.

**🎯 Intermediate:** _"Falco fired a WARNING alert for a shell spawned inside a production container. Walk through how you'd triage it."_
**Model answer:** First I'd check whether this matches a known, sanctioned activity pattern — did someone on the team run a legitimate `kubectl exec` or `kubectl debug` session around that timestamp, which the rule set may not yet have allowlisted. If it's not explainable by sanctioned activity, I'd pull the full alert context Falco provides — the parent process, the exact command line, the user, the container and namespace — to understand what was actually executed and whether it looks like reconnaissance (`whoami`, `cat /etc/passwd`) or something more advanced. I'd check whether other correlated alerts fired around the same time (an unexpected outbound connection from the same container, a sensitive file read), since a real compromise rarely trips exactly one isolated rule. Depending on severity, I'd consider isolating the pod's network access or cordoning the node while investigating further, rather than waiting for full certainty before taking any containment action. Afterward, regardless of whether it turns out to be a false positive or a real incident, I'd feed the finding back into the rule set — either adding an allowlist entry for a confirmed-legitimate pattern, or tightening a rule that should have caught more context if it turns out response was too slow.
_What the interviewer is probing for:_ A structured triage process — context-gathering, correlation with other signals, proportional containment action, and closing the loop by tuning the rule set based on the outcome — rather than either ignoring the alert or overreacting without investigation.

**🎯 Senior:** _"Your organization has deployed Falco cluster-wide, but a recent internal red-team exercise went undetected. How would you investigate why, and what would you change?"_
**Model answer:** I'd start by reconstructing exactly what the red team did at the syscall level — the specific commands, processes, and network activity their exercise generated — and check whether Falco's currently enabled rule set has any rule that should have matched that behavior at all; if no rule covers the technique used, that's a coverage gap, not a tuning problem, and needs a new rule written and tested against that exact technique. If a rule did exist and should have matched, I'd check whether it was disabled, tuned into an allowlist exception too broad to still catch the real activity, or set to a priority low enough that nobody was actually watching for it — a common failure mode where a rule technically exists but its output effectively goes nowhere. I'd also check the alert routing and response pipeline itself — even a correctly fired alert is undetected in practice if it went to a channel nobody monitors or a priority tier excluded from paging. Once I've identified the specific gap — missing rule coverage, an overly broad exception, or a broken response pipeline — I'd fix that specific gap, then re-run the same red-team technique in a controlled way to confirm detection now actually fires end-to-end, rather than assuming the fix works. Finally, I'd treat this as a signal to schedule recurring purple-team exercises specifically to validate Falco's coverage against evolving attack techniques, rather than treating the rule set as a one-time deployment.
_What the interviewer is probing for:_ A rigorous root-cause methodology distinguishing coverage gaps from tuning/routing failures, and the discipline of validating a fix by re-testing rather than assuming, plus recognition that rule-set coverage needs ongoing validation against real techniques, not a static one-time configuration.

**🎯 Architect:** _"Design the runtime security detection and response strategy for a large multi-tenant Kubernetes platform running workloads for many internal teams."_
**Model answer:** I'd deploy Falco as a DaemonSet cluster-wide with the eBPF probe driver for broad kernel compatibility, and maintain the rule set centrally rather than letting individual teams manage their own — consistency across a multi-tenant platform requires a shared baseline the platform team owns, layered with narrowly scoped, reviewed exceptions per team where genuinely needed (a team running specialized debug tooling that would otherwise trigger false positives), each exception tracked with an owner and periodic review rather than left as a permanent silent carve-out. Alert routing would tier by severity and by tenant: lower-priority findings route to a per-team-visible dashboard so teams can self-triage their own workloads' anomalies, while a curated set of high-confidence, high-severity rules (credential-exfiltration patterns, container-escape indicators, cloud-metadata-service access attempts) feed a centrally staffed security on-call rotation with an automated containment action — pod network isolation or node cordon — as the immediate first response, ahead of full human investigation. I'd build a recurring purple-team exercise program specifically to validate rule coverage against realistic attack techniques, treating the rule set as something that must be continuously proven to work rather than assumed correct once deployed. I'd also monitor Falco's own health (dropped-event rates per node, DaemonSet resource saturation) as a first-class platform SLO, since silent event loss under load defeats the entire detection layer without any visible alert indicating it happened. Finally, I'd ensure the Falco DaemonSet's own privileged access is itself tightly scoped and monitored, since it's a uniquely high-value target in a multi-tenant environment where compromising the detection layer would blind visibility across every tenant simultaneously, not just one.
_What the interviewer is probing for:_ Platform-scale design balancing centralized consistency with per-tenant flexibility, tiered severity-based response including automated containment, continuous validation of detection coverage rather than static deployment, and recognition that the detection tooling's own security and health are first-class platform concerns.

## 12. Common Misconceptions

1. **"Falco blocks malicious activity automatically."** Falco detects and alerts; it does not, by default, terminate a process or block an action — remediation requires a separate response pipeline built on top of its alerts.
2. **"Deploying Falco with default rules is sufficient out of the box."** The default rule set is a starting point that typically needs tuning against an organization's own legitimate debug and automation patterns, or it produces enough false positives to cause alert fatigue.
3. **"Runtime detection makes earlier static controls (scanning, signing, linting) unnecessary."** Runtime detection is reactive — it catches what already executed — and works precisely because those earlier controls already eliminated the large majority of preventable risk; it's the last layer, not a replacement for the earlier ones.
4. **"An alert being logged means the threat is handled."** A logged alert with no monitored routing or defined response action provides no real operational security benefit beyond a historical record after the fact.

## 13. 🔑 Key Takeaways

- Falco continuously observes kernel-level system-call behavior of running containers, catching the class of compromise that static controls ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md) scanning/signing, [§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md) manifest linting) structurally cannot see, because those controls evaluate artifacts and declarations rather than live behavior.
- Falco runs as a per-node DaemonSet using an eBPF probe (preferred over the legacy kernel module) to tap syscall activity, and evaluates that stream against a YAML rules engine.
- Falco detects and alerts only — a real runtime security posture requires a separate, deliberately tiered response pipeline (commonly via Falcosidekick) routing findings by severity to monitored channels or automated containment actions.
- The default rule set requires tuning against an organization's legitimate debug and automation activity before it's production-usable, or alert fatigue sets in quickly.
- Runtime detection is inherently reactive and complements, rather than replaces, every preventive control covered earlier in Part 15 — it is the layer that catches what got past all of them.

## 14. Related Concepts & What's Next

This section closed the final gap in the sequence of Part 15's workload-level controls: image trust ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)) and manifest correctness ([§117](./Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)) both evaluate a workload before or at the instant it starts, while Falco observes what it actually does for as long as it keeps running, using kernel-level syscall visibility no static check can replicate. Together, [§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) through [§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md) have built a defense-in-depth chain from cluster configuration hardening through host-kernel restriction, Pod-spec and runtime isolation, supply chain trust, manifest static analysis, and now continuous runtime threat detection — each layer catching what the previous one structurally cannot. [§119](./Section-119-Part15-Network-Security-Deep-Dive-mTLS-Service-Mesh-Security.md), next, shifts focus to the network layer specifically: mTLS and service mesh security, examining how encrypted, authenticated service-to-service communication forms its own distinct security boundary alongside the host- and process-level controls covered so far.

**Next Section:** [§119](./Section-119-Part15-Network-Security-Deep-Dive-mTLS-Service-Mesh-Security.md) — `Section-119-Part15-Network-Security-Deep-Dive-mTLS-Service-Mesh-Security.md`

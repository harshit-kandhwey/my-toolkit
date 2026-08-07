# Section 97 (Part 13): Structured Troubleshooting Methodology for Kubernetes

## 1. Definition

**Plain language:** Kubernetes fails in a lot of different ways — a Pod stuck in `CrashLoopBackOff`, a Node gone `NotReady`, an API server that stopped responding, a Service nobody can reach. Faced with any of these, the difference between an engineer who resolves the incident in minutes and one who thrashes for an hour isn't deeper Kubernetes trivia — it's having a fixed, repeatable method for narrowing down where the failure actually lives before touching anything.

**Precise definition:** A **structured troubleshooting methodology** is a repeatable, ordered process — **symptom → isolate → hypothesize → verify → fix** — applied to any Kubernetes failure regardless of category (Pod, Node, control plane, network, storage, or resource exhaustion). **Symptom** capture is the observable failure exactly as reported, without premature interpretation. **Isolate** narrows the failure to a layer (workload, node, control plane, network, storage) using the cheapest available signal first — object status, then Events, then logs, then deeper tools — mirroring the elimination order that Part 12's observability tools and [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)'s network-specific checklist already demonstrated. **Hypothesize** forms a specific, falsifiable explanation for the isolated layer, not a vague guess. **Verify** tests that hypothesis with a targeted command before acting on it. **Fix** applies the minimal change that resolves the verified cause, then confirms resolution rather than assuming it. This section formalizes what [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) already applied narrowly to networking and what [§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md) already applied narrowly to Events/audit correlation — the same five-step loop, generalized across every failure category the rest of Part 13 will cover.

## 2. Why This Matters

- **Troubleshooting is CKA's single largest exam domain at 30%** — larger than Cluster Architecture (25%), Services & Networking (20%), Workloads & Scheduling (15%), and Storage (10%) combined against any one of them — so a systematic method that reliably works under time pressure is not optional exam-prep polish, it is the highest-leverage skill in the entire certification.
- **Without a fixed method, engineers reliably debug the wrong layer first** — jumping straight to `tcpdump` or scheduler logs when the actual cause is a one-line label typo wastes exactly the kind of time an incident, or a 2-hour practical exam, doesn't have.
- **The same five-step loop generalizes across every failure category this Part covers** — Pod failures ([§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md)), Node issues ([§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md)), control-plane outages ([§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md)), and the networking/storage/application scenarios that follow all reduce to the identical symptom→isolate→hypothesize→verify→fix cycle, just applied to different layers with different tools.

🔑 **Key Takeaway:** Structured troubleshooting is not a collection of memorized fixes for memorized error messages — it is one repeatable five-step loop (symptom → isolate → hypothesize → verify → fix) applied consistently regardless of which layer of Kubernetes actually failed, and it is the single method every remaining section of Part 13 instantiates against a specific failure category.

## 3. Prerequisites and Dependencies

Synthesizes the entire Part 12 observability arc ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md)–[§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)), and directly generalizes the elimination-based approach [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) already applied specifically to in-cluster network troubleshooting. Back-references [§8](../Part2/Section-08-Part2-Control-Plane-Components.md) (Control Plane Components), [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) (Node Components), and [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod Spec Anatomy) as the structural knowledge this methodology is applied against. Sets up [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md), the first failure-category-specific application of this method (Pod failure states).

## 4. Architecture Diagram

```text
┌──────────────────────────────────────────────────────────────────────────┐
│              The Structured Troubleshooting Loop                         │
│                                                                          │
│   ┌────────────┐                                                         │
│   │  SYMPTOM   │  Capture the failure exactly as reported/observed.      │
│   │            │  "Pod X is Pending" — not yet "the scheduler is broken" │
│   └─────┬──────┘                                                         │
│         ▼                                                                │
│   ┌────────────┐                                                         │
│   │  ISOLATE   │  Narrow to a layer, cheapest signal first:              │
│   │            │  object status → Events → logs → describe → deeper tools│
│   └─────┬──────┘                                                         │
│         ▼                                                                │
│   ┌────────────┐                                                         │
│   │HYPOTHESIZE │  Form ONE specific, falsifiable explanation for         │
│   │            │  the isolated layer — not a vague "networking issue"    │
│   └─────┬──────┘                                                         │
│         ▼                                                                │
│   ┌────────────┐        No ───────────────┐                              │
│   │  VERIFY    │  Run a targeted command  │                              │
│   │            │  that would disprove it  │                              │
│   └─────┬──────┘                          │                              │
│         │ Yes                             │                              │
│         ▼                                 │                              │
│   ┌────────────┐                          │                              │
│   │    FIX     │  Apply minimal change,   │                              │
│   │            │  confirm resolution      │                              │
│   └─────┬──────┘                          │                              │
│         │                                 │                              │
│         └── still broken? ────────────────┘  (loop back to ISOLATE       │
│                                                with hypothesis ruled out)│
│                                                                          │
│   Applied per layer:  Pod (§98) → Node (§99) → Control Plane (§100)      │
│                        → Network (§101) → Storage → Application          │
└──────────────────────────────────────────────────────────────────────────┘
```

- **The loop is deliberately cyclical, not linear** — a disproven hypothesis sends you back to ISOLATE with one explanation eliminated, not back to square one; each failed verification is progress, not a dead end.
- **ISOLATE always starts with the cheapest signal**, exactly as [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) demonstrated for networking (object state before DNS before packet capture) — this section generalizes that specific ordering principle to every failure category.
- **VERIFY exists specifically to prevent acting on an unconfirmed hypothesis** — the single most common failure mode this methodology prevents is applying a "fix" for a guessed cause, which either does nothing or, worse, masks the real cause.

## 5. Hands-On

### 5.1 Symptom Capture and Layer Isolation

**Purpose:** Show how to record a symptom precisely and use the cheapest available signals to isolate which layer of the stack is actually implicated, before forming any theory about cause.

**Syntax:**

```bash
kubectl get pods,nodes -A -o wide
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
kubectl describe pod <pod> -n <namespace>
```

**Example usage and expected output:**

```bash
$ kubectl get pods -n production -o wide
NAME              READY   STATUS             RESTARTS   AGE   NODE
web-7d9f8-x2k1    0/1     CrashLoopBackOff   6          12m   node-3

$ kubectl get events -n production --sort-by='.lastTimestamp' | tail -3
Warning  BackOff   90s (x12 over 10m)  kubelet   Back-off restarting failed container
```

**Production usage example:** The symptom is recorded exactly as observed — `CrashLoopBackOff`, 6 restarts, on `node-3` — not prematurely reinterpreted as "the node is bad" or "the image is broken"; both `kubectl get pods` and the Event stream are checked before forming any hypothesis, isolating the failure to the workload layer (this specific Pod's container) rather than the node or control plane.

**Common errors:** Skipping straight to `kubectl logs` or `kubectl exec` before checking `kubectl get pods -o wide` and Events first — those two cheap commands alone frequently already show the restart count, the assigned node, and the kubelet's own explanation, making a deeper investigation unnecessary in many cases.

### 5.2 Forming and Verifying a Falsifiable Hypothesis

**Purpose:** Demonstrate the difference between a vague guess and a specific, testable hypothesis, and how VERIFY is used to confirm or rule it out before acting.

**Syntax:**

```bash
kubectl logs <pod> -n <namespace> --previous
kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[0].resources}'
```

**Example usage and expected output:**

```bash
$ kubectl logs web-7d9f8-x2k1 -n production --previous
Error: connection to database timed out after 30000ms

$ kubectl get pod web-7d9f8-x2k1 -n production -o jsonpath='{.spec.containers[0].resources}'
{"limits":{"memory":"128Mi"},"requests":{"memory":"64Mi"}}
```

**Production usage example:** The hypothesis here is specific and falsifiable — "the container exits because it cannot reach the database within its connection timeout" — not the vague "something's wrong with the app"; `--previous` logs directly confirm it (a database timeout, not an OOM kill, ruling out the resource-limit angle entirely), so the fix targets database reachability rather than adjusting memory limits based on an unverified guess.
**Anti-example (what NOT to do):** Restarting the Pod repeatedly, or bumping memory limits "just in case," without ever reading `--previous` logs — this "fix" would appear to work by coincidence at best (a transient network blip) and mask the real cause at worst, leaving the same failure to recur.

**Common errors:** Reading only the current (post-restart) container's logs instead of `--previous` — a crashed container's own explanation for its exit is almost always in the previous instance's log stream, not the fresh one that hasn't failed yet.

### 5.3 Applying the Minimal Fix and Confirming Resolution

**Purpose:** Show that FIX means the smallest verified change, followed by an explicit confirmation step — not "apply a change and assume it worked."

**Syntax:**

```bash
kubectl rollout restart deployment/<deployment> -n <namespace>
kubectl rollout status deployment/<deployment> -n <namespace>
kubectl get pods -n <namespace> -w
```

**Example usage and expected output:**

```bash
$ kubectl rollout status deployment/web -n production
Waiting for deployment "web" rollout to finish: 1 old replicas are pending termination...
deployment "web" successfully rolled out

$ kubectl get pods -n production
NAME              READY   STATUS    RESTARTS   AGE
web-8f9a2-p3m7    1/1     Running   0          2m
```

**Production usage example:** Once the database connectivity issue identified in 5.2 is actually resolved (a NetworkPolicy allow-rule added, per [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)'s own layer), the fix is a targeted `rollout restart` to pick up the corrected environment, followed by explicitly watching `kubectl get pods -w` and `rollout status` until the new replica reports `Running` with zero restarts — not just issuing the restart and moving on to the next ticket.
**Common errors:** Declaring an incident resolved the moment `STATUS` first shows `Running`, without waiting to see whether the container survives past its first liveness probe cycle ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md)) — a fix that only delays the next `CrashLoopBackOff` by one restart interval looks identical to a real fix for the first minute or two.

## 6. Production Usage Notes

- **This methodology scales down to a 2-minute check and up to a multi-hour incident** — the same five steps apply whether it's a single Pod misbehaving or a cluster-wide control-plane outage ([§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md)); only the tools invoked at ISOLATE change with the scope of the failure.
- **Teams that formalize this loop as a runbook get consistent incident-response quality regardless of who is on call** — exactly the operational point [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)'s Architect-tier interview answer made specifically for networking, generalized here to every category.
- **VERIFY is frequently the step under the most time pressure to skip**, especially in a live incident with stakeholders waiting — resisting that pressure is precisely what separates a fix that sticks from a "fix" that recurs an hour later.

## 7. Security Considerations

- **Isolating a failure sometimes surfaces a security-relevant misconfiguration as a side effect** — an overly permissive NetworkPolicy or a Pod running with excess privileges discovered mid-investigation should be flagged and tracked, not treated as noise irrelevant to the original ticket.
- **The methodology itself should never bypass access controls to move faster** — reaching for a cluster-admin kubeconfig "to rule things out quickly" during an incident is a common but risky shortcut; scoped, audited access should be used even under time pressure.
- **VERIFY commands run during an incident are themselves API requests the audit log ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)) will record** — in a security-sensitive investigation, this trail is often reviewed afterward, so commands run during troubleshooting should be deliberate and traceable, not exploratory noise.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                   | Cause                                                                        | Fix                                                                                                          |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Investigation stalls despite lots of activity                             | No fixed method — jumping between layers without isolating one at a time     | Restart from SYMPTOM, isolate one layer using the cheapest signal, and stick with that layer until ruled out |
| A "fix" is applied but the failure recurs shortly after                   | Hypothesis was never verified before the fix was applied                     | Return to VERIFY with a targeted command before reattempting any fix                                         |
| Same incident type recurs repeatedly across different engineers           | The method isn't documented as a runbook, so each on-call reinvents it       | Codify the symptom→isolate→hypothesize→verify→fix loop as a per-category runbook                             |
| Time pressure leads to skipping verification                              | Perceived urgency treated as license to skip the VERIFY step                 | Treat VERIFY as non-negotiable regardless of pressure — an unverified fix costs more time later              |
| Root cause found but incident marked resolved without checking recurrence | FIX applied without confirming resolution held past the first success signal | Explicitly watch for stability (probe cycles, restart counts) before closing the incident                    |

## 9. Best Practices

- Always state the symptom in observed terms before naming a suspected cause — "Pod is Pending" not "the scheduler must be broken," since the former is neutral and the latter has already (possibly wrongly) isolated a layer.
- Isolate using the cheapest signal available first — object status, then Events, then `describe`, then logs, then deeper tools — exactly the ordering [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) demonstrated for networking, generalized here to every category.
- Never skip VERIFY, even under incident-response time pressure — a fix applied against an unconfirmed hypothesis is a coin flip, not a resolution.

## 10. Common Anti-Patterns / Mistakes

- **Jumping to the most technically interesting tool first** (packet capture, control-plane logs) before ruling out cheaper, statistically more likely causes at the object-status or Events level.
- **Treating a vague guess as a hypothesis** ("networking's probably broken") instead of a specific, falsifiable statement that a single targeted command can confirm or refute.
- **Declaring victory the moment a Pod reports `Running` or a Node reports `Ready`**, without watching for stability past the first success signal, risking a recurrence being mistaken for resolution.

## 11. Interview Questions

**🎯 Beginner:** _"What steps would you follow when a Pod is reported as failing, before you start changing anything?"_
**Model answer:** I'd start by capturing the symptom exactly as it's observed — say, `kubectl get pods` showing `CrashLoopBackOff` with a specific restart count — without yet assuming why. Then I'd isolate using the cheapest signals first: `kubectl get events` for that namespace, then `kubectl describe pod` to see the full status and recent Events together. Only once I have a specific, testable explanation — for example, the previous container's logs showing a startup error — would I consider making any change, and even then I'd want to confirm that explanation with a targeted check before touching anything.
_What the interviewer is probing for:_ Discipline to observe and isolate before acting, rather than guessing and changing things reactively.

**🎯 Intermediate:** _"Explain the difference between 'isolating' a failure and 'hypothesizing' about its cause, and why the order matters."_
**Model answer:** Isolating narrows down which layer of the system is actually implicated — is this a workload-level problem, a node-level problem, a control-plane problem — using progressively deeper signals, cheapest first. Hypothesizing comes after that, and it's specific to whatever layer isolation pointed at — for instance, once I've isolated a failure to a specific Pod's container rather than the node or scheduler, my hypothesis should be about that container's behavior, like a missing environment variable or a downstream dependency timeout, not a vague restatement of the symptom. The order matters because forming a hypothesis before isolating means you're guessing across the entire system rather than reasoning about the one layer the evidence actually points to, which wastes time chasing explanations for layers that were never actually implicated.
_What the interviewer is probing for:_ Clear separation of these two steps as distinct cognitive moves, not synonyms for "figuring out what's wrong."

**🎯 Senior:** _"Walk me through why the VERIFY step is non-negotiable, even during a high-pressure production incident where stakeholders want an immediate fix."_
**Model answer:** Skipping VERIFY means acting on an unconfirmed hypothesis, and in practice that has two failure modes, both costly: the fix does nothing because the actual cause was something else, and the team has now lost time on a change that never addressed the real problem while stakeholders believe a fix is in progress; or worse, the fix appears to work by coincidence (a transient condition clearing on its own, a restart temporarily masking an underlying resource leak) and the incident recurs later, often at a worse time, having taught the team the wrong lesson about what caused it. A targeted verification command — reading `--previous` logs, checking a specific field, running one isolating request — usually costs seconds to a couple of minutes, which is nearly always cheaper than the compounding cost of an unverified fix that doesn't hold. Under real pressure, I'd rather spend those extra seconds and report a slightly later but confirmed resolution than a fast one I can't actually vouch for.
_What the interviewer is probing for:_ Ability to hold to a disciplined process under pressure and articulate the actual cost-benefit reasoning, not just recite "verification is important" as a slogan.

**🎯 Architect:** _"How would you operationalize this troubleshooting methodology across a large platform organization so incident quality doesn't depend on which individual engineer is on call?"_
**Model answer:** I'd codify the symptom→isolate→hypothesize→verify→fix loop as the mandatory shape of every incident runbook, with each failure category — Pod failures, Node issues, control-plane outages, networking, storage, application-level, resource exhaustion — getting its own runbook instance that fills in the category-specific isolation signals and common hypotheses, but never deviates from the five-step shape itself. I'd pre-provision the tooling each isolation step needs (debug images, dashboard links, log queries) so using them during a real incident doesn't require re-deriving anything under pressure, matching the same operational discipline [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) described for its own networking-specific toolkit. I'd build the VERIFY step into the culture explicitly — post-incident reviews would ask not just "what was the root cause" but "what command confirmed it, and when," making it visible when a fix was applied without that confirmation. And I'd treat every genuine incident as a chance to feed a new recurring pattern back into the runbooks — if a category of failure keeps requiring the same non-obvious hypothesis, that hypothesis should move earlier in that runbook's isolation order over time, so the methodology itself gets faster with organizational experience rather than staying static.
_What the interviewer is probing for:_ Ability to turn a personal troubleshooting discipline into a durable, teachable organizational process, including how the method itself should improve from accumulated incident history.

## 12. Common Misconceptions

1. **"Troubleshooting is mostly about knowing more error messages by heart."** Recognizing error text helps, but the actual skill this methodology builds is a repeatable process that works even against failures the engineer has never seen before.
2. **"Isolating and hypothesizing are the same step."** Isolating narrows down which layer is implicated; hypothesizing forms a specific explanation for that already-isolated layer — collapsing them leads to guessing across the whole system instead of reasoning within the evidence-supported layer.
3. **"A fix that appears to work doesn't need verification afterward."** A restart or reapplied manifest can appear to resolve an issue by coincidence; confirming stability past the first success signal is what actually distinguishes a real fix from a temporarily masked recurrence.
4. **"This methodology only applies to complex, multi-layer failures."** It scales down just as well to a two-minute single-Pod check as it does to a multi-hour control-plane incident — the loop doesn't change, only which tools are invoked at each step.

## 13. 🔑 Key Takeaways

- The structured troubleshooting loop — symptom → isolate → hypothesize → verify → fix — is one repeatable method applied across every Kubernetes failure category, not a separate set of tricks per category.
- ISOLATE always starts with the cheapest available signal (object status, then Events, then deeper tools), the same ordering principle [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) demonstrated specifically for networking.
- HYPOTHESIZE must produce a specific, falsifiable explanation for the already-isolated layer, not a vague restatement of the symptom.
- VERIFY is non-negotiable even under incident time pressure — an unverified fix is a coin flip that frequently costs more time later than the verification step itself would have.
- FIX means the minimal change plus explicit confirmation of resolution past the first success signal, not a change followed by an assumption that it worked.

## 14. Related Concepts & What's Next

This section generalizes the elimination-based investigation approach [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) already applied specifically to in-cluster network troubleshooting and [§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md) already applied to Events/audit-log correlation, turning it into the formal five-step loop every remaining section of Part 13 will instantiate against a specific failure category. [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md) begins that application immediately, walking through the most common Pod-level failure states — `CrashLoopBackOff`, `ImagePullBackOff`, `Pending`, and `Evicted` — using exactly this methodology.

**Next Section:** [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md) — `Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md`

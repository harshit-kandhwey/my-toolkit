# Section 138 (Part 18): Progressive Hands-On Labs (Beginner to Production-Style, Including Exam-Simulation Labs)

## 1. Definition

**Plain language:** This section is a set of labs, not a new concept — a ladder of hands-on exercises that starts with "deploy one app" and ends with a single scenario combining RBAC, NetworkPolicy, and live troubleshooting under time pressure, exactly like the CKA/CKAD/CKS exam environment.

**Precise definition:** This is the **capstone lab sequence** for the entire 141-section roadmap: four progressively harder, self-contained labs that require applying concepts from many earlier Parts simultaneously rather than in isolation, culminating in an exam-simulation scenario that mirrors the multi-domain, time-boxed nature of the real Linux Foundation certification exams. Each lab states an objective, a step-by-step task list, and an explicit note tying it back to the specific earlier sections it exercises — the goal is integration and retrieval practice, not first exposure to new material.

## 2. Why This Matters

- **Reading 137 sections of explanation does not, by itself, build exam or production readiness** — the skill being certified is doing the task under time pressure with only `kubectl` and the docs, and that skill only forms through repetition under similar constraints.
- **Real production incidents rarely respect Part boundaries** — a single incident might require reading a Deployment's rollout status, checking a ConfigMap, verifying an RBAC binding, and tracing a NetworkPolicy, all in one sitting; these labs are deliberately built to force that same cross-cutting practice.
- **The CKA/CKAD/CKS exams are 100% hands-on, with zero multiple-choice questions** — Part 17 covered exam strategy and question banks; this section is the last rehearsal before the real thing, or before a genuine production deployment.

🔑 **Key Takeaway:** These four labs are the roadmap's final retrieval-practice mechanism — each one deliberately spans multiple earlier Parts, because that is what both the certification exams and real production incidents actually demand, and no amount of reading substitutes for doing this under a clock.

## 3. Prerequisites and Dependencies

This section assumes the entire roadmap through §137 (Part 17's exam and interview preparation) has been read at least once, and specifically draws on: §24–§29 (Part 4, Pods/Deployments), §33 (Part 5, StatefulSets), §37 (Part 5, HPA), §41–§45 (Part 6, ConfigMaps/Secrets/probes), §57–§60 (Part 8, Volumes/PVC), §75 (Part 10, RBAC), §55 (Part 7, NetworkPolicy), and §97 (Part 13, structured troubleshooting methodology). A working cluster (kind, minikube, or a cloud sandbox) with `kubectl` configured is required to actually perform these labs; they are not theoretical.

## 4. Architecture Diagram

```text
                    PROGRESSIVE LAB DIFFICULTY CURVE (§138)

  Lab 1               Lab 2                  Lab 3                  Lab 4
  Beginner            Intermediate           Advanced               Exam Simulation
  ─────────           ─────────────         ──────────              ────────────────
  Deployment          + ConfigMap/Secret    StatefulSet +           RBAC + NetworkPolicy
  + Service           + liveness/readiness  PVC + HPA               + broken Deployment
  (§24–§29)           probes (§41–§45)      (§33, §57–§60, §37)     + troubleshooting
                                                                     under time limit
                                                                     (§75, §55, §97)

  single object    →   config + health    →  stateful + scale   →  multi-domain,
  correctness           correctness            correctness           timed, integrated

  ───────────────────────────────────────────────────────────────────────────────►
                         increasing scope, increasing realism, decreasing time budget
```

## 5. Hands-On

### Lab 1 — Beginner: Deploy a Basic App With a Service

**Objective:** Get a Deployment running and reachable via a ClusterIP Service — the smallest complete unit of "an app running on Kubernetes."

**Tasks:**

1. Create a namespace called `lab1`.
2. Write and apply a Deployment manifest running `nginx:1.27` with 3 replicas, labeled `app: web`.
3. Confirm all 3 Pods reach `Running` and `1/1 Ready` via `kubectl get pods -n lab1 -w`.
4. Create a `ClusterIP` Service named `web-svc` selecting `app: web` on port 80.
5. From a temporary debug Pod in the same namespace, `curl web-svc` and confirm you get an nginx response.
6. Scale the Deployment to 5 replicas with `kubectl scale` and confirm the Service load-balances across all 5 without any manifest change to the Service itself.

**What this exercises:** Pod/Deployment fundamentals and rolling updates (§24–§29), Service-to-Pod selector matching and ClusterIP routing (introduced in Part 7's Services coverage), and the basic `kubectl get`/`describe`/`logs` inspection loop from §1.

**Common errors:** Forgetting that a Service's `selector` must match the Deployment's Pod template labels exactly, not the Deployment's own labels — a mismatch here produces a Service with zero Endpoints while every Pod still reports `Running`, the single most common Lab 1 stumbling block.

### Lab 2 — Intermediate: Add ConfigMap, Secret, and Probes

**Objective:** Take Lab 1's app and make it production-shaped: externalized configuration, externalized credentials, and health checks that actually gate traffic.

**Tasks:**

1. Create a ConfigMap holding a `LOG_LEVEL=info` key and mount it as an environment variable in the Deployment from Lab 1.
2. Create a Secret holding a fake `API_KEY` value and mount it as a file via a volume mount, not an environment variable.
3. Add a `readinessProbe` (HTTP GET on `/`) and a `livenessProbe` (HTTP GET on `/`) to the container spec, with distinct `initialDelaySeconds` values.
4. Deliberately break the readiness probe's path (point it at `/nonexistent`) and observe the Pods leave the Service's Endpoints while remaining `Running`.
5. Fix the probe and confirm the Pods rejoin the Service automatically, with no manual intervention.
6. Update the ConfigMap value and confirm — without editing the Deployment — that pods do **not** pick up the change until they are recreated, and explain why in your own words.

**What this exercises:** ConfigMap/Secret creation and consumption patterns (§41–§45), the distinction between "container running" and "container ready to serve traffic" (§1's core misconception, revisited concretely), and the config-propagation behavior that trips up nearly everyone the first time they encounter it.

**Common errors:** Mounting the Secret as an environment variable "for consistency" with the ConfigMap, then wondering why `kubectl describe pod` shows the value in plaintext under `Environment:` — environment variables are visible to anything that can read the Pod spec or exec into the container, which is exactly why the task specifies a volume mount instead.

### Lab 3 — Advanced: StatefulSet + PVC + HPA

**Objective:** Run a stateful workload with per-replica persistent storage and autoscale a stateless tier based on load.

**Tasks:**

1. Deploy a 3-replica StatefulSet (e.g., a simple key-value store or `nginx` standing in for one) with a `volumeClaimTemplates` block requesting a small persistent volume per replica.
2. Confirm each Pod gets its own PVC (`data-<statefulset>-0`, `-1`, `-2`) and stable network identity (`<statefulset>-0.<service>`), and that deleting a Pod recreates it with the **same** PVC reattached, not a fresh one.
3. Separately, deploy a stateless Deployment with a resource `requests.cpu` set, and configure an HPA targeting 50% CPU utilization, min 2 / max 6 replicas.
4. Generate synthetic CPU load against the stateless Deployment (e.g., a busy-loop container or a load-generating Job) and watch the HPA scale replicas up via `kubectl get hpa -w`.
5. Stop the load and confirm the HPA scales back down after its stabilization window.
6. Intentionally delete one StatefulSet Pod's PVC directly and observe what happens to that replica on next restart — document the failure mode.

**What this exercises:** StatefulSet ordering, stable identity, and per-replica storage (§33), PersistentVolumeClaim lifecycle and binding (PVC coverage in Part 8), and HPA scaling behavior (§37) — three mechanisms that look similar on paper but fail very differently in practice.

**Common errors:** Assuming the HPA will react instantly to load — the metrics pipeline has real latency (metrics-server scrape interval plus HPA's own sync period), so expecting an immediate scale-up within seconds of generating load is a frequent, avoidable source of confusion during this lab.

### Lab 4 — Exam Simulation: RBAC + NetworkPolicy + Live Troubleshooting

**Objective:** A single, time-boxed (45-minute) scenario combining access control, network segmentation, and a deliberately broken cluster state — structured exactly like a CKA/CKS exam question cluster.

**Tasks:**

1. Given a `ServiceAccount` named `ci-deployer` in namespace `lab4`, create a Role and RoleBinding granting it `get`/`list`/`create` on Deployments and Services only — verify with `kubectl auth can-i --as=system:serviceaccount:lab4:ci-deployer create pods` (should be denied) and the equivalent for Deployments (should be allowed).
2. Apply a default-deny NetworkPolicy in `lab4`, then add a targeted policy allowing only the `frontend` app to reach the `backend` app on port 8080 — verify both the allowed path and the now-blocked path (e.g., `frontend` to some other Pod) with an in-cluster debug Pod.
3. You are handed a pre-broken Deployment (image tag typo, causing `ImagePullBackOff`) and a Pod stuck `Pending` (over-sized resource request the cluster can't schedule) — using only `kubectl describe`, `kubectl get events`, and `kubectl logs`, diagnose and fix both without being told what's wrong in advance.
4. Time yourself; stop at 45 minutes regardless of completion and review what remained undone as a gap-analysis input for further Part 17 review.

**What this exercises:** RBAC Role/RoleBinding scoping and verification via `auth can-i` (§75), NetworkPolicy default-deny posture and targeted allow rules (§55), and the structured troubleshooting methodology — describe, events, logs, then act — from §97, all under the same time pressure the real exams impose.

**Common errors:** Diagnosing the `ImagePullBackOff` and `Pending` Pod by guessing at a fix before running `kubectl describe`/`kubectl get events` — both failures have an explicit, immediately visible reason in the Events output, and skipping straight to trial-and-error edits wastes exactly the time budget this lab is designed to make scarce.

### Stretch Goal: Lab 5 — Multi-Namespace Incident Under Simulated On-Call Conditions

For teams wanting a fifth, harder rung: combine Labs 1–4 into one longer-running cluster with three namespaces, inject two simultaneous unrelated faults (e.g., a NetworkPolicy blocking a legitimate path in one namespace, and a ResourceQuota silently rejecting new Pods in another), and hand the scenario to someone who did not set it up. This mirrors an actual on-call page far more closely than any single-fault lab can, and is the natural bridge from "lab exercise" to "real incident response."

## 6. Production Usage Notes

- These labs are deliberately ordered so each one's "what could go wrong" step is the actual learning objective, not an afterthought — Lab 2's broken readiness probe and Lab 3's deleted PVC are the most instructive moments in each lab, not edge cases to skip.
- Re-running Lab 4 multiple times with different injected faults (a bad probe instead of a bad image tag, a missing RoleBinding instead of an over-broad one) is more valuable than running it once and moving on — the exam and production incidents both present novel combinations of the same small set of root causes.
- Treat the 45-minute cap in Lab 4 as non-negotiable practice discipline: the CKA/CKAD/CKS exams are strictly time-boxed, and the instinct to "just take a few more minutes" is exactly the habit these labs exist to correct before it costs real exam points.
- Consider pairing these labs with a partner or study group for Lab 4 specifically — one person injects the fault without telling the other, which more accurately simulates the "nobody warned you what broke" reality of both exam scenarios and real incidents than self-injected faults ever can.
- Log actual completion times for each lab across multiple attempts; a downward trend in Lab 4's completion time over several weeks is a far more reliable readiness signal than a single successful pass.

## 7. Security Considerations

- Lab 4's RBAC step should be verified with `kubectl auth can-i`, not assumed correct from reading the YAML — a Role that looks like it grants only Deployment access can still be undermined by an accompanying ClusterRoleBinding elsewhere in the cluster, and verification against the live API is the only reliable check.
- Running these labs in a shared or cloud sandbox cluster (rather than a disposable local `kind`/`minikube` cluster) risks leaving default-deny NetworkPolicies or broad RBAC grants behind — always tear down lab namespaces (`kubectl delete namespace lab1 lab2 lab3 lab4`) when finished.
- Never practice these labs against a production cluster, even a "spare" namespace in one — the deliberately broken states in Lab 4 and the destructive PVC deletion in Lab 3 are exactly the kind of action that must stay confined to disposable environments.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                   | Fix                                                                                                                           |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Lab 1 Service returns no response despite Pods being `Running` | Service selector doesn't match the Deployment's Pod labels                     | Compare `kubectl get svc -o yaml` selector against `kubectl get pods --show-labels` exactly                                   |
| Lab 2 Pods never leave `NotReady` after fixing the probe path  | Probe's `initialDelaySeconds`/`periodSeconds` hasn't elapsed yet since the fix | Wait a full probe interval or `kubectl rollout restart deployment` to force immediate re-evaluation                           |
| Lab 3 StatefulSet Pod stuck `Pending` after PVC deletion       | The underlying PV was reclaimed or the StorageClass can't re-bind a fresh PVC  | Check `kubectl get pv,pvc` reclaim policy and StorageClass; this is often the intended, instructive failure                   |
| Lab 4 `auth can-i` returns unexpected `yes` for a denied verb  | A separate, broader ClusterRoleBinding grants the ServiceAccount extra access  | `kubectl get clusterrolebinding -o wide` and search for the ServiceAccount across all bindings, not just the one just created |
| Lab 4 NetworkPolicy allows traffic it shouldn't                | CNI plugin in use doesn't enforce NetworkPolicy at all                         | Confirm the cluster's CNI plugin actually supports NetworkPolicy before debugging the policy YAML itself                      |

## 9. Best Practices

- Run every lab on a disposable cluster (`kind`/`minikube`) rather than a shared environment, so destructive steps (Lab 3's PVC deletion, Lab 4's broken states) carry no real risk.
- Do each lab cold first, without referring back to its source sections, then use a failed or incomplete attempt as the trigger to re-read the specific §N sections it exercises — this mirrors real retrieval practice rather than copy-along tutorial-following.
- Time-box Lab 4 strictly and log how far you got, then repeat it a week later with different injected faults to check whether the diagnostic instinct — not just the specific fix — has actually stuck.
- Tear down every lab's namespace when finished; leftover ResourceQuota, NetworkPolicy, or RBAC objects from earlier labs can silently interfere with later ones on the same cluster.

## 10. Common Anti-Patterns / Mistakes

- **Treating these labs as read-through exercises rather than actually typing every command** — the value is in the muscle memory of diagnosing `kubectl describe` output under time pressure, which reading alone does not build.
- **Skipping the "break it, then observe" steps** (Lab 2's probe break, Lab 3's PVC deletion) because they feel like extra work — these are the single most exam-relevant and production-relevant moments in the whole lab sequence.
- **Running Lab 4 once, succeeding, and considering RBAC/NetworkPolicy "done"** — a single successful pass proves the concept was understood once, not that it will be applied correctly under a novel combination of faults next time.
- **Practicing destructive steps against a shared or production-adjacent cluster** to save the setup time of a disposable one — the setup time is trivial compared to the cost of an actual incident.

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through how you'd verify a Deployment and Service you just created are actually working end-to-end."_
**Model answer:** First `kubectl get pods` to confirm all replicas are `Running` and `Ready`, then `kubectl get svc` to confirm the Service exists and has the expected selector, then `kubectl get endpoints <svc-name>` to confirm the Service actually has matching Pod IPs behind it — a Service with zero endpoints despite Pods running almost always means a label/selector mismatch. Finally, I'd curl the Service from an in-cluster debug Pod to confirm real traffic flows, not just that the objects exist.
_What the interviewer is probing for:_ A methodical, layered verification habit rather than assuming "kubectl apply succeeded" means "the app works."

**🎯 Intermediate:** _"You updated a ConfigMap that's mounted as an environment variable, but the running Pods aren't picking up the new value. Is this a bug?"_
**Model answer:** No — environment variables are injected once, at container start, from whatever the ConfigMap contained at that moment; Kubernetes does not re-inject environment variables into a running container when the source ConfigMap changes. To pick up the change, the Pods need to be recreated (a rollout restart), or the ConfigMap needs to be consumed as a mounted volume instead, which does update in place (with some kubelet sync delay) without a restart — though the application itself still needs to notice the file changed.
_What the interviewer is probing for:_ Accurate understanding of ConfigMap consumption mechanics, a very common practical gotcha.

**🎯 Senior:** _"In Lab 3's scenario, a StatefulSet Pod comes back Pending after you deleted its PVC directly. Diagnose this as if it happened in production."_
**Model answer:** I'd start with `kubectl describe pod` to see the scheduling failure reason, then check `kubectl get pvc` in that namespace — if the PVC shows `Pending` rather than `Bound`, I'd check the StorageClass's binding mode and reclaim policy, and check whether the original PV was deleted along with the PVC (a `Delete` reclaim policy would have destroyed the underlying volume, not just the claim object). If the PV was destroyed, the data is genuinely gone and this becomes a restore-from-backup conversation, not a scheduling fix — which is exactly why StatefulSet storage in production should default to a reclaim policy that doesn't destroy data on PVC deletion, and why this failure mode is deliberately part of the lab rather than a corner case to gloss over.
_What the interviewer is probing for:_ Whether the candidate treats storage destruction as a data-loss incident with real consequences, not just a scheduling puzzle to solve.

**🎯 Architect:** _"How would you turn these four labs into an onboarding program for new hires joining a platform team, and what would you change about them for that purpose?"_
**Model answer:** I'd keep the four-tier difficulty curve but extend each lab with a "why did we design it this way" retrospective discussion after completion, tying each lab's failure mode back to a real incident or design decision from the platform's own history — Lab 2's probe misconfiguration mapped to an actual past outage, for instance, makes the lesson concrete rather than abstract. I'd also add a fifth, org-specific lab exercising whatever the platform team's actual landing zone or GitOps workflow looks like, since these four labs are deliberately generic and exam-aligned rather than tied to any one organization's tooling. Finally, I'd track completion and time-to-fix metrics across new hires over successive cohorts, since a lab sequence that never gets measured for effectiveness tends to calcify into ritual rather than staying a genuine skill-building tool.
_What the interviewer is probing for:_ Ability to extend a generic exercise into an organizationally useful, measurable onboarding tool rather than treating it as a fixed artifact.

## 12. Common Misconceptions

1. **"Completing these labs once means the material is mastered."** Retrieval practice research is consistent on this: spaced repetition with varied fault injection (different broken states each time) builds durable skill far better than a single successful pass.
2. **"These labs are only useful for exam preparation."** The same diagnostic sequence — describe, events, logs, then act — used in Lab 4 is the exact sequence used in real production incidents; the exam-simulation framing is a forcing function for realism, not the sole purpose.
3. **"A ConfigMap change should propagate to running Pods immediately, like a live reload."** As Lab 2 demonstrates directly, environment-variable-sourced ConfigMap values are frozen at container start; only volume-mounted ConfigMaps update in place, and even then the application must notice the file change itself.
4. **"RBAC review is just reading the Role/RoleBinding YAML."** As Lab 4 demonstrates, a ServiceAccount's real effective permissions are the union of every Role/ClusterRoleBinding referencing it anywhere in the cluster — `kubectl auth can-i` against the live API is the only reliable verification, not a YAML read-through.

## 13. 🔑 Key Takeaways

- These four labs deliberately increase in both technical scope and time pressure, moving from single-object correctness (Lab 1) to a full exam-style, multi-domain, timed scenario (Lab 4).
- Each lab's deliberately broken or destructive step (a bad readiness probe, a deleted PVC, an over-broad RBAC binding) is the most instructive part of the lab, not an optional extra.
- Verification must happen against the live cluster state (`auth can-i`, `get endpoints`, in-cluster `curl`) rather than by reading manifests, since manifests describe intent, not necessarily the resulting effective behavior.
- Repetition with varied injected faults, not a single successful pass, is what builds the diagnostic instinct both the certification exams and real production incidents actually demand.
- Always run these labs on a disposable cluster, given the genuinely destructive steps built into Labs 3 and 4 by design.

## 14. Related Concepts & What's Next

These labs are the practical, hands-on complement to Part 17's exam-domain breakdowns and scenario question banks (§130–§137) — where Part 17 built exam-day strategy and question familiarity, this section builds the muscle memory of actually executing under the same conditions. Having now practiced the roadmap's concepts end-to-end rather than section-by-section, the next section consolidates every Part's single most important takeaway into one structured checklist, serving as a final compressed review artifact for exam day or a pre-deployment production review.

**Next Section:** §139 — `Section-139-Part18-Consolidated-Key-Takeaways-Checklist.md`

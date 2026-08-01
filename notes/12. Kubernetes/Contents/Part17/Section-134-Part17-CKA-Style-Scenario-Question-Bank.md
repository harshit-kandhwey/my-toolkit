# Section 134 (Part 17): CKA-Style Scenario Question Bank

## 1. Definition

**Plain language:** Everything so far in Part 17 has been strategy — how the exam is graded, how the domains are weighted, how to move fast in a terminal. This section is the drill itself: a bank of realistic, performance-based CKA task scenarios, each timed the way the real exam times them, each solved the way a proctor would expect it solved.

**Precise definition:** This section is a **scenario question bank** — a set of standalone, self-contained performance-based tasks (PBTs) modeled on the CKA's actual format: a short prompt describing a desired cluster state, a strict context switch (`kubectl config use-context ...`), and a single command or manifest that produces the required state, gradable by an automated checker. Each scenario below states the prompt as a candidate would see it, a worked solution, and a note on exactly which underlying skill it is testing.

## 2. Why This Matters

- **The CKA is not a knowledge exam — it is a skills exam**, scored purely on whether the live cluster matches the expected end state after your time runs out; reading about `kubectl taint` is not the same skill as applying the right taint under a 7-minute clock while your context is currently pointed at the wrong cluster.
- **Every real CKA task begins with a context switch you must not skip** — candidates who solve the task perfectly in the wrong context score zero for it, making "read the prompt, switch context, then act" a non-negotiable first habit this question bank drills repeatedly.
- **Partial credit rewards getting the cluster to the right state by any means** — the scenarios below sometimes show a faster imperative path and a slower declarative path side by side, because the exam grades the end state, not your command history.

🔑 **Key Takeaway:** Practicing scenarios under a visible countdown, with a required context switch at the start of each one, is the only way to convert kubectl familiarity into exam-passing speed — knowing the answer and producing it correctly within the time box are different skills, and this question bank trains the second one.

## 3. Prerequisites and Dependencies

Builds directly on §133 (kubectl speed techniques — aliases, editor config, imperative one-liners), which every solution below assumes is already in your muscle memory. Each scenario also draws on a specific earlier Part: Deployments and rollouts (§26–§29), Taints and Tolerations (§68), RBAC (§75), Services and NetworkPolicies (Part 7), Storage (Part 8), and etcd/cluster maintenance (Part 14) — this section does not re-teach those concepts, it tests them under exam conditions.

## 4. Architecture Diagram: Scenario Category Breakdown

```text
   CKA Exam Domain Weight → This Question Bank's Scenario Mix

   Troubleshooting (30%)        ████████████████████████████  Scenario 3, 6
   Cluster Architecture (25%)   ████████████████████████       Scenario 1, 7
   Services & Networking (20%)  ███████████████████             Scenario 4
   Workloads & Scheduling (15%) ██████████████                   Scenario 2, 5
   Storage (10%)                ██████████                        Scenario 5 (storage half)

   Per-scenario time-box discipline:
   ┌─────────────────────────────────────────────────────────┐
   │ 1. Read prompt fully — note namespace, context, names   │
   │ 2. kubectl config use-context <target>   (ALWAYS FIRST) │
   │ 3. Solve with fastest correct command (imperative first)│
   │ 4. Verify with a read-only command (get/describe)       │
   │ 5. Move on — do not re-verify a task you already passed │
   └─────────────────────────────────────────────────────────┘
```

- **Scenarios are weighted here roughly the way the real exam weights domains** — Troubleshooting and Cluster Architecture dominate both the real exam and this bank.
- **The context-switch step is deliberately drilled into every scenario below**, even where it feels redundant, because skipping it under real time pressure is the single most common reason a technically-correct answer scores zero.

## 5. Hands-On: The Scenario Question Bank

### Scenario 1 — Broken kubelet on a Worker Node (7 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. Node `node01` is reporting `NotReady`. SSH access to `node01` is available via `ssh node01`. Identify the root cause and restore the node to `Ready` without rebooting it. Do not modify any other node.

**Solution:**

```bash
kubectl config use-context k8s-c1
kubectl get nodes
kubectl describe node node01 | tail -30
ssh node01
systemctl status kubelet
# Example finding: kubelet crashed due to a bad flag in the drop-in config
journalctl -u kubelet -n 50 --no-pager
cat /var/lib/kubelet/config.yaml
# Fix the identified misconfiguration (e.g. wrong --container-runtime-endpoint)
systemctl restart kubelet
systemctl enable kubelet
exit
kubectl get nodes
```

**What it's testing:** Node-level troubleshooting (§97–§105 methodology), kubelet static configuration (§17), and the discipline of reading `journalctl` output rather than guessing — this is the single most common CKA "cluster architecture + troubleshooting" crossover task.

### Scenario 2 — Rolling Update With a Deliberate Rollback (6 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. Namespace `frontend`. Deployment `web` is currently running image `nginx:1.24`. Update it to `nginx:1.99` (a deliberately broken tag), observe the rollout fail, then roll it back to the previous working revision. Leave the Deployment healthy at the end.

**Solution:**

```bash
kubectl config use-context k8s-c1
kubectl -n frontend set image deployment/web nginx=nginx:1.99 --record
kubectl -n frontend rollout status deployment/web
# Rollout stalls — ImagePullBackOff
kubectl -n frontend rollout undo deployment/web
kubectl -n frontend rollout status deployment/web
kubectl -n frontend get pods -l app=web
```

**What it's testing:** Deployment rollout mechanics and revision history (§27–§28), and correctly reading `rollout status` to know when to intervene rather than waiting out a stuck rollout.

### Scenario 3 — CrashLoopBackOff Root-Cause and Fix (5 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. Namespace `payments`. Pod `ledger-0` is in `CrashLoopBackOff`. Fix the underlying issue so the Pod reaches `Running` and stays there. Do not delete the Pod's owning controller.

**Solution:**

```bash
kubectl config use-context k8s-c1
kubectl -n payments get pods
kubectl -n payments logs ledger-0 --previous
kubectl -n payments describe pod ledger-0 | tail -20
# Example finding: missing env var referenced from a Secret that doesn't exist
kubectl -n payments get secret
kubectl -n payments create secret generic ledger-db-creds --from-literal=password=changeme
kubectl -n payments delete pod ledger-0
kubectl -n payments get pods -w
```

**What it's testing:** Pod failure-state triage (§97–§99: CrashLoopBackOff specifically), reading `--previous` logs on a restarting container, and correctly distinguishing "fix the cause, let the controller recreate the Pod" from "the Pod itself is the problem."

### Scenario 4 — Service Not Reachable Across Namespaces (6 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. A Pod named `debug-client` in namespace `qa` cannot reach `Service` `catalog` in namespace `shop` on port 8080. Diagnose and fix the issue. Do not delete the NetworkPolicy that exists in namespace `shop`.

**Solution:**

```bash
kubectl config use-context k8s-c1
kubectl -n shop get svc catalog -o wide
kubectl -n shop get endpoints catalog
# Endpoints empty — selector mismatch
kubectl -n shop get pods --show-labels
kubectl -n shop get svc catalog -o yaml | grep -A3 selector
# Fix the Service selector to match the actual Pod labels
kubectl -n shop patch svc catalog -p '{"spec":{"selector":{"app":"catalog"}}}'
kubectl -n shop get endpoints catalog
# Then check whether the existing NetworkPolicy permits qa namespace ingress
kubectl -n shop get networkpolicy -o yaml
kubectl -n qa exec debug-client -- curl -s catalog.shop.svc.cluster.local:8080
```

**What it's testing:** Service-to-Pod selector matching and empty-Endpoints diagnosis (Part 7), plus reading a NetworkPolicy correctly rather than assuming it's the cause — a common exam trap where two separate faults (bad selector AND a restrictive policy) can be stacked in one scenario.

### Scenario 5 — PersistentVolumeClaim Stuck in Pending (6 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. Namespace `analytics`. PVC `data-claim` is stuck `Pending` and Pod `report-gen` depends on it. Get the Pod to `Running` state.

**Solution:**

```bash
kubectl config use-context k8s-c1
kubectl -n analytics get pvc data-claim
kubectl -n analytics describe pvc data-claim | tail -15
kubectl get storageclass
# Example finding: PVC requests a StorageClass that doesn't exist
kubectl -n analytics get pvc data-claim -o yaml | grep storageClassName
kubectl get sc
# Patch the PVC's StorageClass (or delete/recreate if immutable field blocks patch)
kubectl -n analytics delete pvc data-claim
kubectl -n analytics apply -f data-claim-fixed.yaml
kubectl -n analytics get pvc data-claim
kubectl -n analytics get pods report-gen -w
```

**What it's testing:** PVC-Pending root-cause analysis (Part 8), recognizing that `storageClassName` is immutable post-creation so a delete/recreate is required rather than a patch, and StorageClass/provisioner literacy.

### Scenario 6 — etcd Backup and Restore Under Time Pressure (8 minutes)

**Prompt as seen on exam:**

> Context: this is a static-pod-based cluster, `kubeadm` bootstrapped. Take a snapshot backup of etcd to `/opt/backups/etcd-snapshot.db`, then verify the snapshot is valid. Do not restore it — just prove the backup succeeded.

**Solution:**

```bash
ETCDCTL_API=3 etcdctl snapshot save /opt/backups/etcd-snapshot.db \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key

ETCDCTL_API=3 etcdctl snapshot status /opt/backups/etcd-snapshot.db --write-out=table
```

**What it's testing:** etcd backup procedure recall under zero notes allowed (§107 territory) — this is one of the highest-value single tasks on the real CKA because the certificate paths are always the same three files and memorizing them cold saves minutes versus hunting through `/etc/kubernetes/manifests/etcd.yaml` for the flags during the exam.

### Scenario 7 — Draining a Node for Maintenance Without Dropping Workloads (5 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. Node `node02` needs a kernel patch. Safely cordon and drain it, respecting any PodDisruptionBudgets, then bring it back into service once "maintenance" (simulated by you doing nothing) is complete.

**Solution:**

```bash
kubectl config use-context k8s-c1
kubectl cordon node02
kubectl get pods -o wide --field-selector spec.nodeName=node02
kubectl drain node02 --ignore-daemonsets --delete-emptydir-data
# ...simulated maintenance window...
kubectl uncordon node02
kubectl get nodes
```

**What it's testing:** Node maintenance lifecycle (§109: cordon/drain/uncordon), correct use of `--ignore-daemonsets` (drain fails without it if any DaemonSet Pods are present), and awareness that a PodDisruptionBudget violation will block eviction rather than silently ignore it — a candidate who doesn't know this can burn the whole time box waiting on a drain that will never complete without `--disable-eviction` (which should NOT be used against a real PDB in production).

## 6. Production Usage Notes: Practicing Under Real Exam Time Pressure

- **Set a visible countdown timer for every scenario you drill**, not a mental estimate — the actual exam UI shows remaining time per task, and training without that visual pressure builds false confidence.
- **Time-box each scenario at roughly 1.5x the stated exam time on your first pass**, then progressively tighten to the real time as you build muscle memory; jumping straight to real-exam timing before the commands are automatic just builds panic, not skill.
- **Always practice the context switch as the literal first keystroke**, even in a single-cluster practice environment — reflexively typing `kubectl config use-context` before reading further is what prevents solving the wrong cluster during the real exam, where several contexts are pre-loaded and swapped between tasks.
- **Practice on a real multi-node cluster (kind or kubeadm-provisioned VMs), not minikube alone** — several of these scenarios (etcd backup, node drain, kubelet troubleshooting) require genuine multi-node behavior that a single-node local cluster can't fully replicate.

## 7. Security Considerations

- Scenario 6 (etcd backup) touches the exact PKI material — `ca.crt`, `server.crt`, `server.key` — that an attacker with etcd snapshot access could use to reconstruct all cluster secrets in plaintext (etcd stores Secrets base64-encoded, not encrypted, unless EncryptionConfiguration is enabled per §43); treat any backup file you produce as equivalently sensitive to the cluster's Secrets and never leave it world-readable.
- Scenario 4's NetworkPolicy trap is a reminder that the real exam (and real production clusters) frequently combine a security control with an unrelated bug — don't assume a broken connection is "just the NetworkPolicy" without also checking Service/Endpoints wiring, and don't assume it's "just a selector bug" without also checking whether a policy is additionally restricting the path.
- RBAC-related node/PVC/Secret troubleshooting scenarios should always be diagnosed with `kubectl auth can-i` before assuming a permissions issue is a bug rather than an intentional restriction — accidentally loosening RBAC to "make a scenario work" during practice builds the wrong reflex for the real exam and for production incident response alike.

## 8. Common Troubleshooting Scenarios

| Symptom During Practice                                    | Cause                                                                                                  | Fix                                                                                                              |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Solved the task correctly but scored zero in a mock grader | Forgot the context switch; command ran against the wrong cluster                                       | Always run `kubectl config use-context` as the literal first command of every scenario                           |
| `kubectl drain` hangs indefinitely                         | A PodDisruptionBudget prevents eviction, or DaemonSet Pods block it                                    | Add `--ignore-daemonsets`; investigate the PDB rather than forcing eviction in production                        |
| etcd snapshot command fails with a TLS handshake error     | Wrong certificate paths copied from memory instead of the manifest                                     | Cross-check `/etc/kubernetes/manifests/etcd.yaml` for the exact `--cert-file`/`--key-file` flags actually in use |
| PVC patch to fix `storageClassName` fails                  | `storageClassName` is immutable after creation                                                         | Delete and recreate the PVC with the corrected manifest instead of patching                                      |
| Rollback lands on the same broken revision                 | `rollout undo` without `--to-revision` picked the immediately-prior revision, which was already broken | Inspect `kubectl rollout history` and target a specific known-good revision explicitly                           |

## 9. Best Practices

- Read the entire prompt once, fully, before typing anything — many CKA tasks bury a constraint ("do not delete the owning controller," "do not modify any other node") in the last sentence that changes the correct command.
- Prefer imperative one-liners for straightforward creates/patches and switch to a YAML manifest only when the object needs fields no generator flag covers — this is a direct application of the speed techniques from §133.
- Verify with a cheap read-only command (`get`, `describe`, `rollout status`) immediately after each fix, then move on — don't re-verify a task repeatedly at the cost of time on the remaining tasks.

## 10. Common Anti-Patterns / Mistakes

- **Skipping the context switch because "it's probably already right"** — the exam deliberately rotates contexts between tasks specifically to catch this habit.
- **Forcing a drain past a PodDisruptionBudget with `--disable-eviction` or `--force`** just to make the task complete faster, replicating a production-incident-causing habit instead of the intended maintenance discipline.
- **Memorizing exact answers to specific scenarios instead of the underlying diagnostic sequence** (`get` → `describe` → `logs` → fix → verify) — the real exam's scenarios are worded differently every sitting, and only the sequence transfers.

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through your diagnostic sequence when a Pod is stuck in `CrashLoopBackOff`."_
**Model answer:** Start with `kubectl get pods` to confirm the state and restart count, then `kubectl logs <pod> --previous` to see why the last attempt crashed (the current container may not have logs yet if it just restarted). Follow with `kubectl describe pod` for events and resource/probe context. Fix the underlying cause — often a bad command, missing ConfigMap/Secret key, or a failing liveness probe — and let the controller recreate the Pod rather than deleting it unless the manifest itself needed a change.
_What the interviewer is probing for:_ A repeatable sequence rather than guesswork, and the specific `--previous` flag detail that separates candidates who've actually debugged this in practice from those reciting theory.

**🎯 Intermediate:** _"A Service has no Endpoints. What are the three most common causes, and how do you check each in under a minute?"_
**Model answer:** First, selector/label mismatch — compare `kubectl get svc -o yaml`'s selector against `kubectl get pods --show-labels` in the same namespace. Second, the target Pods aren't actually `Ready` — Endpoints only include Pods passing their readiness probe, so `kubectl get pods` showing `0/1 Ready` explains empty Endpoints even with a correct selector. Third, wrong namespace or wrong `targetPort` versus the container's actual listening port. All three are checkable via `kubectl get svc,endpoints,pods -o wide` in one combined command.
_What the interviewer is probing for:_ Breadth across the real causes rather than fixating on just the selector case, and speed of diagnosis rather than just correctness.

**🎯 Senior:** _"You have 45 minutes left and 4 tasks remaining, one of which is an etcd backup/restore worth significant points but you're unsure of the exact certificate paths. What's your strategy?"_
**Model answer:** Triage by point value and confidence, not order presented. If the etcd task is high-value but I'm not fully certain of the flags, I'd first attempt the other three tasks I'm confident about to lock in guaranteed points, then return to etcd with remaining time — the certificate paths are always discoverable from `cat /etc/kubernetes/manifests/etcd.yaml`, which lists the exact `--cert-file`, `--key-file`, `--trusted-ca-file` flags the running etcd static pod uses, so "unsure" is recoverable within a couple of minutes without needing perfect memorization. I would not burn ten minutes second-guessing paths from memory when the manifest is sitting right there on the control-plane node.
_What the interviewer is probing for:_ Real exam-time triage judgment and the specific knowledge that the etcd manifest itself is the fastest source of truth for its own connection flags, rather than pure memorization.

**🎯 Architect:** _"How would you design a practice regimen that builds real exam-day speed rather than memorized muscle memory that breaks the moment a scenario is worded slightly differently?"_
**Model answer:** I'd build the regimen around varying the surface details while holding the diagnostic sequence constant — rotate namespace names, resource names, and the specific fault injected (bad selector one day, bad NetworkPolicy the next, both stacked together another day) so the candidate is forced to actually run `get`/`describe`/`logs` each time rather than pattern-matching a memorized fix. I'd also deliberately randomize which context points at which cluster between practice runs, specifically to keep the "read prompt, switch context" reflex sharp rather than assumed. Finally, I'd track time-per-task-category over successive sessions (troubleshooting, workloads, networking, storage) against the real domain weights from §130, so practice time is allocated toward the 30%-weighted Troubleshooting domain rather than evenly split — a candidate who's equally fast at all five domains but the exam is 30% one domain should spend disproportionate practice time there, not equal time everywhere.
_What the interviewer is probing for:_ Systems thinking about deliberate practice design, not just listing scenario types, and explicit awareness that domain weight should drive time allocation both on exam day and during preparation.

## 12. Common Misconceptions

1. **"If I know the command, I'll be fast enough on exam day."** Knowing the command and typing it correctly under a visible countdown with an unfamiliar context pre-loaded are different skills — only timed practice closes that gap.
2. **"The context is probably already right, I can skip switching it."** The exam is specifically designed to rotate contexts between tasks to catch candidates who assume this; treat the switch as mandatory, not optional.
3. **"Forcing a stuck `drain` past a PodDisruptionBudget is fine during the exam since it's not real production."** Building that reflex during practice risks it surfacing during a real incident later; practice the correct behavior (investigate the PDB) every time.
4. **"A stuck PVC can always be fixed with `kubectl patch`."** Several PVC fields, including `storageClassName`, are immutable after creation — some fixes genuinely require delete-and-recreate, and knowing which is which saves real exam minutes.

## 13. 🔑 Key Takeaways

- The CKA grades end state, not command history — imperative shortcuts and declarative YAML both score identically as long as the cluster ends up correct.
- Every scenario begins with a context switch; treat skipping it as an automatic zero regardless of how correct the rest of the solution is.
- The diagnostic sequence (`get` → `describe` → `logs`/`journalctl` → fix → verify) transfers across differently-worded scenarios; memorizing specific answers does not.
- Troubleshooting and Cluster Architecture dominate both the real exam's domain weights and this question bank's scenario mix — allocate practice time accordingly rather than evenly.
- etcd certificate paths are always recoverable from the running static pod's manifest file, removing the need to memorize them under pressure.

## 14. Related Concepts & What's Next

This section built directly on §133's speed techniques and drew scenario material from Deployments (§26–§29), Taints/Tolerations (§68), RBAC (§75), Services and NetworkPolicies (Part 7), Storage (Part 8), and cluster maintenance (Part 14) — treat every scenario above as a checkpoint on whether those sections' concepts are exam-ready, not just understood. §135 shifts from cluster-operator scenarios to application-developer scenarios: ConfigMaps, Secrets, probes, multi-container Pods, and the build/deploy lifecycle that the CKAD exam grades instead.

**Next Section:** §135 — `Section-135-Part17-CKAD-Style-Scenario-Question-Bank.md`

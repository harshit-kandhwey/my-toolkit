# Section 60 (Part 8): Container Storage Interface (CSI) Architecture

## 1. Definition

**Plain language:** Before CSI, every storage vendor's integration code had to live directly inside Kubernetes' own codebase, meaning a bug fix or new feature for one storage backend required waiting on a full Kubernetes release cycle. CSI fixes this by turning storage integration into an external, out-of-tree plugin — any vendor can now ship, version, and update their own storage driver independently of Kubernetes itself.

**Precise definition:** The **Container Storage Interface (CSI)** is a standardized gRPC-based API specification, developed jointly across the container orchestration ecosystem (not Kubernetes-specific), that decouples storage provisioning and lifecycle logic from the orchestrator's core codebase. A **CSI driver** implements this specification, typically split across three gRPC services — the **Identity service** (driver metadata/capabilities), the **Controller service** (volume provisioning, attaching, snapshotting — cluster-level operations), and the **Node service** (mounting a volume into a Pod's filesystem — node-local operations) — and is deployed into a Kubernetes cluster as a combination of a **Controller Plugin** (usually a Deployment or StatefulSet, one or a few replicas) and a **Node Plugin** (always a DaemonSet, one Pod per node). This section explains the mechanism that makes every `provisioner` field referenced by a StorageClass (§59) actually function.

## 2. Why This Matters

- **CSI replaced the legacy in-tree volume plugin model entirely, and understanding why matters for both exam and production reasoning.** In-tree plugins (`kubernetes.io/aws-ebs`, `kubernetes.io/gce-pd`, and similar) are deprecated and, as of recent Kubernetes versions, fully removed in favor of their CSI driver equivalents — any cluster still assuming in-tree behavior is working against a deprecated model.
- **CSI's Controller/Node split explains a class of storage failures that otherwise look mysterious.** A volume that provisions successfully (Controller service succeeded) but fails to mount into a Pod (Node service failed) are two entirely different failure domains, diagnosable by inspecting two entirely different sets of Pods — the CSI controller Deployment versus the CSI node DaemonSet.
- **Every cloud-managed Kubernetes offering, and most on-prem storage vendors, now ship storage integration exclusively as a CSI driver.** Recognizing the standard CSI deployment shape (Controller Deployment + Node DaemonSet, plus sidecar containers) is directly transferable across AWS EBS, Azure Disk, GCE PD, Ceph, Portworx, and dozens of other drivers — it's one architecture, not dozens of vendor-specific ones.

🔑 **Key Takeaway:** CSI is a standardized, out-of-tree API that any storage vendor implements as a driver split into Controller-service logic (provisioning, attaching) and Node-service logic (mounting into a Pod), deployed as a Controller Deployment plus a Node DaemonSet — this is the actual mechanism behind every StorageClass provisioner referenced in §59, replacing the deprecated in-tree plugin model entirely.

## 3. Prerequisites and Dependencies

Builds directly on §59 (StorageClasses and Dynamic Provisioning), where the `provisioner` field named a CSI driver without yet explaining its internal architecture. Assumes familiarity with DaemonSets (§34, Part 5) and Deployments (§28, Part 4), since a CSI driver's Kubernetes-side deployment uses both patterns together. Connects forward to §61 (Access Modes and Reclaim Policies), where CSI driver capability directly determines which access modes are actually usable.

## 4. Architecture Diagram: CSI Driver Deployment and Request Flow

```text
   Control plane                                             Every node
   ┌───────────────────────────────────────────┐             ┌──────────────────────────────────────────┐
   │  CSI Controller Plugin                    │             │  CSI Node Plugin (per node)              │
   │  (Deployment, 1-3 replicas)               │             │  (DaemonSet)                             │
   │  ┌────────────────────────────────────┐   │             │  ┌─────────────────────────────────┐     │
   │  │ external-provisioner (sidecar)     │   │             │  │ node-driver-registrar           │     │
   │  │ external-attacher (sidecar)        │   │             │  │ (sidecar, registers with        │     │
   │  │ external-resizer (sidecar)         │   │             │  │  kubelet via unix socket)       │     │
   │  │ external-snapshotter (sidecar)     │   │             │  │                                 │     │
   │  │ ────────────────────────────────── │   │             │  │ CSI driver container            │     │
   │  │  CSI driver container              │   │             │  │ (Node service: NodeStageVolume, │     │
   │  │  (Controller service: CreateVolume,│   │             │  │  NodePublishVolume)             │     │
   │  │   ControllerPublishVolume)         │   │             │  └────────────────┬────────────────┘     │
   │  └────────────────────────────────────┘   │             └───────────────────┼──────────────────────┘
   └─────────────────┬─────────────────────────┘                                 │
                     │ gRPC over unix socket                                     │ gRPC over unix socket
                     ▼                                                           ▼
              Cloud/storage backend API                                 kubelet ──► mounts volume
              (creates real disk/volume)                                into the Pod's filesystem

   Request flow for a new PVC:
   PVC created → external-provisioner watches PVC → calls CreateVolume (Controller)
             → cloud volume created → PV object created → PVC bound
             → Pod scheduled to Node X → kubelet calls Node Plugin on Node X
             → NodeStageVolume + NodePublishVolume → volume appears in container
```

- **Sidecar containers, not the CSI driver binary itself, handle most of the Kubernetes-specific plumbing** — `external-provisioner`, `external-attacher`, `external-resizer`, and `external-snapshotter` are shared, vendor-agnostic components maintained by the Kubernetes storage SIG that watch Kubernetes API objects (PVCs, VolumeAttachments) and translate them into CSI gRPC calls; the vendor only needs to implement the actual CSI gRPC service logic.
- **The Controller Plugin runs once (or a few replicas) cluster-wide, while the Node Plugin runs on every node** — this mirrors the conceptual split between "provisioning a cloud disk" (a cluster-level, infrequent operation) and "mounting a volume into a specific Pod on a specific node" (a per-node, per-Pod operation).
- **All communication between sidecars and the driver happens over a local Unix domain socket, not the network** — the CSI driver container and its sidecars in the same Pod share a volume containing this socket, which is why CSI driver Pods almost always show two or more containers.

## 5. Hands-On: Inspecting and Working with CSI Drivers

### 5.1 Inspecting Installed CSI Drivers

**Purpose:** Confirm which CSI drivers are actually registered in a cluster and what capabilities they advertise, before troubleshooting or designing a StorageClass around one.

**Syntax:**

```bash
kubectl get csidrivers
kubectl describe csidriver <driver-name>
kubectl get pods -n kube-system -l app=ebs-csi-controller
kubectl get pods -n kube-system -l app=ebs-csi-node
```

**Example usage and expected output:**

```bash
$ kubectl get csidrivers
NAME                  ATTACHREQUIRED   PODINFOONMOUNT   STORAGECAPACITY   TOKENREQUESTS   REQUIRESREPUBLISH   MODES        AGE
ebs.csi.aws.com       true             true             false             <unset>         false               Persistent   120d

$ kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver
NAME                                  READY   STATUS    RESTARTS   AGE
ebs-csi-controller-6d4f9c8b7d-abc12   6/6     Running   0          120d
ebs-csi-controller-6d4f9c8b7d-def34   6/6     Running   0          120d
ebs-csi-node-h7k2m                    3/3     Running   0          120d
ebs-csi-node-p9q1n                    3/3     Running   0          120d
```

**Production usage example:** The `6/6` container count on the controller Pod reflects the CSI driver container plus its five sidecars (`external-provisioner`, `external-attacher`, `external-resizer`, `external-snapshotter`, and a liveness-probe sidecar) — seeing fewer ready containers than expected here is the first sign of a provisioning-path problem, even before checking any PVC.

**Common errors:** Confusing the Node Plugin DaemonSet's Pod count with a health problem — it's expected to have exactly one Pod per eligible node, so a count that doesn't match `kubectl get nodes` warrants investigation, but a count that does match is entirely normal, not evidence of over- or under-provisioning.

### 5.2 Diagnosing a Controller-Service vs. Node-Service Failure

**Purpose:** Use the Controller/Node split to correctly localize a storage failure — a very different diagnostic path depending on which side actually failed.

**Syntax:**

```bash
kubectl describe pvc <name>            # provisioning (Controller) failures surface here
kubectl describe pod <pod-using-pvc>   # mount (Node) failures surface here
kubectl logs -n kube-system <csi-controller-pod> -c csi-provisioner
kubectl logs -n kube-system <csi-node-pod-on-that-node> -c <driver-container-name>
```

**Example usage and expected output:**

```bash
$ kubectl describe pvc db-storage -n production | tail -5
Events:
  Type    Reason                 Age   From                         Message
  ----    ------                 ----  ----                         -------
  Normal  ExternalProvisioning   30s   persistentvolume-controller  waiting for a volume to be created by ebs.csi.aws.com

$ kubectl describe pod db-pod -n production | tail -5
Events:
  Type     Reason       Age   From     Message
  ----     ------       ----  ----     -------
  Warning  FailedMount  10s   kubelet  MountVolume.MountDevice failed: rpc error: NodeStageVolume failed
```

**Production usage example:** In this example, the PVC bound successfully (Controller service succeeded, a real volume was created and attached), but the Pod fails to start with a `NodeStageVolume` error — this immediately localizes the problem to the Node Plugin on that specific node (a filesystem formatting issue, a stale device path, or a Node Plugin Pod that isn't running on that node), not to provisioning or the cloud API at all.

**Common errors:** Restarting or re-creating the PVC when the actual failure is in the Node service on one specific node — since provisioning already succeeded, deleting the PVC only destroys a working volume and requires re-provisioning, when the real fix is restarting or investigating the Node Plugin Pod on the affected node instead.

### 5.3 Understanding a Minimal CSI Driver Manifest Structure

**Purpose:** Recognize the standard shape of a CSI driver's own Kubernetes deployment, since nearly every vendor's installation manifest follows this same Controller Deployment + Node DaemonSet + CSIDriver object pattern.

**Syntax:**

```yaml
# Simplified: the CSIDriver object itself (one per driver, cluster-scoped)
apiVersion: storage.k8s.io/v1
kind: CSIDriver
metadata:
  name: ebs.csi.aws.com
spec:
  attachRequired: true
  podInfoOnMount: true
  volumeLifecycleModes:
    - Persistent
```

**Example usage and expected output:**

```bash
$ kubectl apply -f csidriver.yaml
csidriver.storage.k8s.io/ebs.csi.aws.com created

$ kubectl get csidriver ebs.csi.aws.com -o yaml | grep -A2 spec
spec:
  attachRequired: true
  podInfoOnMount: true
```

**Production usage example:** In practice, almost no one hand-writes this manifest — CSI drivers are installed via a vendor-published Helm chart or a static manifest bundle that includes the `CSIDriver` object, the Controller Deployment, the Node DaemonSet, and the necessary RBAC (ServiceAccounts, ClusterRoles) all together; understanding the pieces matters far more for troubleshooting than for hand-authoring them.

**Common errors:** Assuming `attachRequired: false` means a volume needs no Node-service work at all — it only means the Controller-service `ControllerPublishVolume` (attach) step is skipped, not that mounting (`NodeStageVolume`/`NodePublishVolume`) is skipped; the Node Plugin is still involved for essentially every CSI driver.

## 6. Production Usage Notes

- **CSI drivers are versioned and released entirely independently of the Kubernetes release cycle**, which is the direct practical benefit of the out-of-tree model — a storage vendor can ship a bug fix or new feature (like volume snapshots or expansion support) without waiting for or coordinating with a Kubernetes minor release.
- **Not every CSI driver implements every optional capability** — snapshot support, volume expansion, and `ReadWriteMany` access all depend on what the specific driver's Controller service actually implements; `kubectl describe csidriver` and the vendor's own documentation are the authoritative sources, not assumptions carried over from a different driver.
- **The Node Plugin DaemonSet must run with elevated privileges** (typically `privileged: true` and host mount propagation) since mounting a filesystem into a container genuinely requires host-level mount namespace operations — this is a structurally necessary exception to least-privilege, not an oversight.

## 7. Security Considerations

- **CSI Controller Plugin Pods typically hold cloud-provider IAM credentials or equivalent permissions** (to create/delete/attach real cloud volumes) via their ServiceAccount — this is one of the higher-privilege workloads in most clusters and warrants the same RBAC and audit scrutiny as any component with direct cloud API write access.
- **CSI Node Plugin Pods running `privileged: true` are a deliberate, structurally necessary exception to Pod Security Standards** (§78, Part 10) — these DaemonSets should live in a trusted, platform-owned namespace with tightly scoped RBAC, since a compromised Node Plugin Pod has effectively host-level filesystem access on every node it runs on.
- **CSI driver secrets (backend credentials, encryption keys for volume-level encryption) are frequently passed via StorageClass `parameters` referencing a Secret** — auditing which Secrets a StorageClass references, and who can read them, is a meaningful and often-overlooked part of storage security review.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Cause                                                                                                | Fix                                                                                                               |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| PVC stuck `Pending` with `ExternalProvisioning` event repeating     | CSI Controller Plugin Pod unhealthy, crashed, or lacks cloud API permissions                         | Check controller Pod status/logs (`kubectl logs -n kube-system <controller-pod> -c csi-provisioner`)              |
| PVC bound, but Pod fails with `FailedMount`/`NodeStageVolume` error | CSI Node Plugin Pod on that specific node unhealthy, or a stale/conflicting device mount             | Check the Node Plugin Pod on that exact node; a Node Plugin restart or node reboot often clears stale state       |
| `kubectl get csidrivers` shows no entry for the expected driver     | CSI driver not installed, or installed into a namespace/cluster the current context doesn't see      | Confirm the driver's installation manifests were applied; check `kubectl get pods -n kube-system` for its Pods    |
| Volume expansion request silently has no effect                     | The specific CSI driver doesn't implement the resize capability, regardless of StorageClass settings | Check `kubectl describe csidriver` and the driver's documentation for expansion support before assuming a bug     |
| New nodes joining the cluster can't mount existing CSI volumes      | Node Plugin DaemonSet Pod hasn't yet scheduled/started on the new node                               | Confirm DaemonSet Pod count matches node count; check for taints preventing the Node Plugin from scheduling there |

## 9. Best Practices

- Always check `kubectl describe csidriver <name>` before assuming a capability (snapshots, expansion, `ReadWriteMany`) is supported — driver capability, not Kubernetes version, is the limiting factor.
- Localize storage failures immediately to Controller (provisioning) or Node (mounting) service by comparing PVC events against Pod events, rather than restarting components at random.
- Treat CSI Node Plugin DaemonSets as trusted, platform-owned infrastructure requiring the same change-control discipline as kube-proxy or the CNI plugin — not as an application-team-managed component.

## 10. Common Anti-Patterns / Mistakes

- **Deleting and recreating a PVC to "fix" a mount failure that's actually a Node-service problem on one specific node**, destroying a successfully provisioned volume for no benefit and requiring full re-provisioning.
- **Assuming every CSI driver supports the same feature set** (expansion, snapshots, `ReadWriteMany`), copying a StorageClass definition from a different driver's documentation without verifying actual capability via `kubectl describe csidriver`.
- **Under-provisioning RBAC or cloud IAM permissions for the CSI Controller Plugin's ServiceAccount** and only discovering the gap when a provisioning call fails in production, rather than validating it during driver installation.

## 11. Interview Questions

**🎯 Beginner:** _"What is CSI, and why did Kubernetes move away from having storage plugins built directly into its own codebase?"_
**Model answer:** CSI, the Container Storage Interface, is a standardized API that lets storage vendors write their own drivers completely outside the Kubernetes codebase, communicating with the cluster through a well-defined gRPC interface instead of vendor-specific code baked into Kubernetes itself. Before CSI, storage integrations lived "in-tree," meaning any bug fix or new feature for a specific cloud disk type required waiting on a full Kubernetes release; CSI decouples that entirely, letting vendors ship, version, and update their drivers independently, which is also why in-tree volume plugins have since been deprecated and removed in favor of their CSI equivalents.
_What the interviewer is probing for:_ Understanding the motivation behind CSI, not just that it exists.

**🎯 Intermediate:** _"Explain the difference between the Controller service and the Node service in a CSI driver, and why that split matters for troubleshooting."_
**Model answer:** The Controller service handles cluster-level, infrequent operations — creating a volume, attaching it to a node, expanding or snapshotting it — and typically runs as a small Deployment somewhere in the cluster. The Node service handles per-node, per-Pod operations — actually staging and mounting the volume into a specific Pod's filesystem — and runs as a DaemonSet, one Pod per node, since mounting genuinely has to happen on the node where the Pod is running. This split matters directly for troubleshooting: if a PVC is stuck `Pending`, the problem is almost certainly on the Controller side (check the controller Deployment's Pods and logs); if a PVC is `Bound` but the Pod fails to start with a mount error, the problem is on the Node side, specifically the Node Plugin Pod on that one node — two completely different components to investigate depending on which failure you're seeing.
_What the interviewer is probing for:_ Practical, diagnostic understanding of the architecture, not just textbook definitions of the two services.

**🎯 Senior:** _"A specific node in your cluster can't mount any CSI-backed volumes, while every other node works fine. How would you investigate?"_
**Model answer:** Since other nodes work fine, I'd rule out the Controller service and StorageClass configuration entirely — this is node-scoped, so it's a Node Plugin problem specific to that one node. I'd first check whether the Node Plugin DaemonSet even has a healthy, running Pod on that node (`kubectl get pods -n kube-system -o wide | grep <node-name>`), since a scheduling issue, taint, or crash loop on just that Pod would explain it cleanly. If the Node Plugin Pod looks healthy, I'd check its logs for the specific `NodeStageVolume`/`NodePublishVolume` errors, which often point at something node-local — a stale device path from a previous volume, a kernel module or filesystem tool missing on that specific node's OS image, or a host-level mount namespace issue. I'd also compare that node's OS/kernel version against the rest of the fleet, since node-specific CSI mount failures are sometimes traced back to a node that drifted from the standard image rather than anything storage-specific at all.
_What the interviewer is probing for:_ Ability to use the Controller/Node architectural split to immediately scope down a wide investigation to the right component, plus awareness that node drift is a real, non-obvious root cause.

**🎯 Architect:** _"How would you evaluate and select a CSI driver when designing storage architecture for a new platform, beyond just 'it's the cloud provider's official one'?"_
**Model answer:** I'd start with the actual capability matrix needed by the platform's workloads — whether `ReadWriteMany` is genuinely required (which immediately narrows the field, since many block-storage CSI drivers only support `ReadWriteOnce`), whether volume snapshotting and cross-region/cross-account cloning matter for backup and DR strategy, and whether online volume expansion is supported without a Pod restart. I'd evaluate the driver's release cadence and CNCF/vendor support maturity, since CSI drivers vary widely in how actively they're maintained, and I'd specifically check the permission model required by the Controller Plugin's ServiceAccount against the platform's existing IAM/security posture, since that's often the component with the broadest blast radius if compromised. Finally, I'd pilot the driver against realistic failure-injection scenarios — node failure during an active mount, Controller Plugin restart during provisioning — before committing it as the platform default, since CSI driver bugs under failure conditions are far more consequential and harder to work around than a missing convenience feature.
_What the interviewer is probing for:_ Ability to evaluate infrastructure choices against real operational requirements (capability, security posture, failure behavior) rather than defaulting to "whatever the cloud provider ships."

## 12. Common Misconceptions

1. **"CSI is a Kubernetes-specific technology."** CSI is a cross-orchestrator standard (also usable by other container platforms); Kubernetes was an early and major adopter, but the specification itself isn't Kubernetes-only.
2. **"A CSI driver is a single container/process."** In practice it's split into a Controller Plugin (Deployment, with several sidecars) and a Node Plugin (DaemonSet, with its own sidecars) — recognizing this split is essential for troubleshooting.
3. **"All CSI drivers support the same features (snapshots, expansion, ReadWriteMany)."** Feature support is entirely driver-specific — `kubectl describe csidriver` and the vendor's documentation are the only reliable sources, not assumptions carried over from a different driver or cloud provider.

## 13. 🔑 Key Takeaways

- CSI standardizes storage integration as an out-of-tree, gRPC-based API, letting vendors ship and update drivers independently of the Kubernetes release cycle — replacing the now-deprecated in-tree plugin model.
- Every CSI driver splits into a Controller service (provisioning, attaching — cluster-level, Deployment-based) and a Node service (mounting — per-node, DaemonSet-based), and this split is the key to correctly localizing storage failures.
- Sidecar containers (`external-provisioner`, `external-attacher`, `external-resizer`, `external-snapshotter`) handle the shared Kubernetes-integration plumbing, so vendors only need to implement the CSI gRPC service logic itself.
- A PVC stuck `Pending` points to the Controller side; a bound PVC whose Pod fails to mount points to the Node side on that specific node — two different diagnostic paths entirely.
- Driver capability (snapshots, expansion, access modes) is never universal — always confirm via `kubectl describe csidriver` and vendor documentation rather than assuming parity across drivers.

## 14. Related Concepts & What's Next

This section explained the mechanism behind every `provisioner` field referenced by a StorageClass in §59 — the CSI driver architecture, split into Controller and Node services, that actually performs dynamic provisioning and volume mounting. Combined with §57 (ephemeral volumes) and §58 (the PV/PVC binding model), this completes the foundational storage stack: how storage is attached to a Pod, how it's requested and bound, how it's automatically provisioned, and now how that provisioning is actually implemented under the hood. The next section moves from architecture into the semantics of what a bound volume can actually guarantee about concurrent access and post-deletion behavior.

**Next Section:** §61 — `Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md`

# Section 31 (Part 4): GKE Networking & Storage

## 31.1 Definition

**Plain language:** Every Pod in a GKE cluster needs its own network address, a way for other Pods and outside users to reach it reliably even as Pods come and go, and — for workloads that need to keep data — a way to attach durable storage that survives a Pod restart. This section covers how GKE wires all three together on top of GCP's underlying VPC network.

**Precise:** GKE networking is built on **VPC-native clusters**, which assign Pod and Service IP ranges from secondary IP ranges (alias IP ranges) of a VPC subnet rather than an overlay network, giving Pods routable identities within the VPC. Traffic reaches workloads via Kubernetes **Services** and, for HTTP(S) traffic, **Ingress** or the newer **Gateway API**. Durable storage is provided via the **Container Storage Interface (CSI)**, backed by Compute Engine Persistent Disks (block storage) or Filestore (managed NFS).

## 31.2 Why It Exists / Problem It Solves

Kubernetes networking has a few hard requirements: every Pod must be able to reach every other Pod without NAT, every node must reach every Pod, and a Pod's own view of its IP must match what other Pods see. Historically, many Kubernetes networking implementations satisfied this with an **overlay network** — encapsulating Pod traffic inside an additional network layer on top of the underlying infrastructure network — which works but adds encapsulation overhead and makes Pod IPs invisible to the underlying network's own tooling (firewall rules, VPC flow logs, routing).

GKE's **VPC-native** model solves this differently: Pod IPs are allocated directly from the VPC's own address space (via secondary/alias IP ranges), so Pods are first-class citizens of the VPC network itself — visible to VPC firewall rules, flow logs, and routable without any encapsulation overhead. This is a major reason GKE networking integrates more deeply with the rest of GCP's networking stack (Section 19–27) than a bolt-on overlay would.

Storage has a related but different problem: containers are ephemeral by design (Section 28), but many real workloads (databases, stateful services) need data that survives a Pod restart or rescheduling to a different node. The CSI-based storage integration exists to let Kubernetes-native storage requests (`PersistentVolumeClaim`) transparently provision and attach real GCP storage (Persistent Disks, Filestore) behind the scenes.

## 31.3 VPC-Native Clusters and Alias IP Ranges

A **VPC-native cluster** (the GKE default and strongly recommended mode) provisions three distinct IP ranges within the chosen VPC subnet:

| Range                       | Purpose                                                                    |
| --------------------------- | -------------------------------------------------------------------------- |
| **Primary range**           | Node IP addresses (the underlying Compute Engine VMs).                     |
| **Pod secondary range**     | Alias IP range for Pod IPs — every Pod gets a routable IP from this range. |
| **Service secondary range** | Alias IP range for ClusterIP Service virtual IPs.                          |

Because Pod and Service ranges are genuine VPC secondary ranges (not an overlay), Pod-to-Pod traffic across nodes routes natively through the VPC without additional encapsulation, and VPC-level constructs — firewall rules, VPC Flow Logs, Private Service Connect, Shared VPC (Section 25) — can see and act on Pod IPs directly.

> ⚠️ **Interview-relevant nuance:** The older alternative, a **routes-based cluster**, used a custom route per node and did not give Pods first-class VPC IP identities in the same way. Routes-based clusters are legacy and effectively deprecated for new clusters — VPC-native is the default and the answer to "which should I use" in virtually every current scenario.

## 31.4 Pod and Service Networking

- **Pod networking:** each Pod gets its own IP from the Pod secondary range, shared by all containers within that Pod (containers in the same Pod communicate via `localhost`). Pod IPs are ephemeral — a rescheduled Pod gets a new IP — which is why workloads should never be addressed directly by Pod IP.
- **Services:** a Kubernetes **Service** provides a stable virtual IP (from the Service secondary range) and DNS name that load-balances traffic across a dynamic set of matching Pods, decoupling clients from any individual Pod's lifecycle. Common Service types:
  - **ClusterIP** (default): reachable only within the cluster.
  - **NodePort**: exposes the Service on a static port on every node's IP, mainly used as a building block for other exposure methods rather than directly in production.
  - **LoadBalancer**: provisions a GCP external (or internal) Network Load Balancer automatically, giving the Service a real external/internal IP.

## 31.5 Ingress and the Gateway API

For HTTP(S) traffic specifically, exposing each Service behind its own load balancer doesn't scale well once an application has many services needing host/path-based routing, TLS termination, and shared certificates. Kubernetes solves this with higher-level HTTP routing resources:

- **GKE Ingress:** implements the Kubernetes `Ingress` resource by automatically provisioning and configuring a GCP HTTP(S) Load Balancer (Section 22) based on host/path routing rules declared in the `Ingress` manifest — one declarative Kubernetes object drives real GCP load-balancing infrastructure.
- **Gateway API:** the newer, more expressive Kubernetes-native API for traffic routing (`Gateway`, `HTTPRoute`, and related resources), designed as the long-term successor to `Ingress` with richer capabilities (traffic splitting/weighting, more granular header/path matching, cleaner separation between infrastructure operators and application teams). GKE supports the Gateway API via its own managed Gateway controller, also backed by GCP's load balancing infrastructure.

> 💡 **Tip:** New GKE workloads needing advanced HTTP routing (traffic splitting for canary deploys, cross-namespace routing) should generally default to the Gateway API rather than `Ingress`, since `Ingress` is functionally frozen while the Gateway API is where new routing capability is actively developed across the Kubernetes ecosystem, not just on GKE.

## 31.6 Persistent Storage: CSI Drivers, Persistent Disks, and Filestore

Kubernetes' native storage abstraction is the **PersistentVolumeClaim (PVC)** — an application declares "I need N GB of storage with these access characteristics," and a **StorageClass** determines what kind of real storage actually gets provisioned to satisfy it, via a **CSI driver**.

| Backing Storage                         | CSI Driver                     | Access Mode                                                                         | Typical Fit                                                                                                                     |
| --------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Compute Engine Persistent Disk (PD)** | `pd.csi.storage.gke.io`        | `ReadWriteOnce` (single node) by default; regional PDs support limited multi-attach | Block storage for a single Pod replica — databases, stateful workloads with one writer.                                         |
| **Filestore**                           | `filestore.csi.storage.gke.io` | `ReadWriteMany` (many nodes/Pods simultaneously)                                    | Shared file storage across many Pods at once — shared config, content repositories, workloads needing a real shared filesystem. |

- A **regional Persistent Disk** synchronously replicates across two zones, letting a Pod using it survive a single-zone failure with the disk attached to a replacement Pod in the surviving zone, at the cost of write latency versus a zonal PD.
- Filestore integration is the go-to answer whenever multiple Pods need genuinely simultaneous read/write access to the same files, since standard Persistent Disks fundamentally support only one attached writer (with narrow multi-writer exceptions).

## 31.7 Architecture Diagram

```
                         VPC SUBNET (us-central1)
   ┌────────────────────────────────────────────────────────────────────┐
   │ Primary range: 10.0.0.0/24        (Node IPs)                       │
   │ Pod secondary range: 10.4.0.0/14  (alias IPs — Pod IPs)            │
   │ Svc secondary range: 10.8.0.0/20  (alias IPs — Service ClusterIPs) │
   │                                                                    │
   │   ┌───────────────Node A (10.0.0.5)────────────────┐               │
   │   │  Pod X (10.4.1.2) ── Pod Y (10.4.1.3)          │               │
   │   └────────────────────────────────────────────────┘               │
   │                          ▲                                         │
   │            ClusterIP Service (10.8.0.10) load-balances to Pods     │
   │                          │                                         │
   │   ┌──────────Gateway / Ingress─────────────┐                       │
   │   │   backed by GCP HTTP(S) Load Balancer  │◄── external users     │
   │   └────────────────────────────────────────┘                       │
   │                                                                    │
   │   ┌── PersistentVolumeClaim ──┐   ┌── PersistentVolumeClaim ──┐    │
   │   │  ► Persistent Disk (CSI)  │   │  ► Filestore (CSI)        │    │
   │   │  ReadWriteOnce, one Pod   │   │  ReadWriteMany, many Pods │    │
   │   └───────────────────────────┘   └───────────────────────────┘    │
   └────────────────────────────────────────────────────────────────────┘
```

## 31.8 Hands-On Example: Exposing a Deployment and Attaching Storage

**Beginner example — expose a Deployment via a LoadBalancer Service:**

```bash
kubectl expose deployment my-app --type=LoadBalancer --port=80 --target-port=8080
kubectl get service my-app
```

**Purpose:** Creates a Service of type `LoadBalancer`, which GKE automatically provisions as a real GCP external Network Load Balancer with a public IP routing to the Deployment's Pods.

**Expected output (abbreviated):**

```
NAME     TYPE           CLUSTER-IP     EXTERNAL-IP     PORT(S)        AGE
my-app   LoadBalancer   10.8.0.15      34.123.45.67    80:31234/TCP   45s
```

**Intermediate example — request a Persistent Disk-backed volume via a StorageClass:**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-rwo
  resources:
    requests:
      storage: 50Gi
```

```bash
kubectl apply -f my-app-data-pvc.yaml
kubectl get pvc my-app-data
```

**Purpose:** Declares a 50 GB storage request; the `standard-rwo` StorageClass (GKE's default Persistent Disk-backed class) triggers the CSI driver to provision a real Compute Engine Persistent Disk and bind it to this claim, ready for a Pod to mount.

**Expected output:**

```
NAME          STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS
my-app-data   Bound    pvc-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx   50Gi       RWO            standard-rwo
```

## 31.9 Production & Enterprise Usage

- Enterprises always use **VPC-native clusters**; sizing the Pod and Service secondary ranges generously up front matters because these ranges are difficult to resize after cluster creation, and undersized ranges cause Pod-scheduling failures once a cluster/node pool scales up.
- **Gateway API** is increasingly the enterprise default for new HTTP routing, particularly where multiple teams share a cluster and need namespace-scoped routing control without a platform team manually editing a single shared `Ingress` resource.
- Stateful workloads needing multi-zone resilience use **regional Persistent Disks**; workloads needing genuinely shared file access across many replicas (e.g., a CMS's shared media directory) use **Filestore** rather than trying to work around a Persistent Disk's single-writer limitation.

## 31.10 Common Misconceptions

- **Misconception:** "GKE networking is an overlay network like some other Kubernetes distributions." VPC-native GKE clusters assign Pods real, routable VPC IPs via alias IP ranges — there is no encapsulation overlay in the default and recommended configuration.
- **Misconception:** "A Persistent Disk can be attached to multiple Pods for shared read/write access the same way Filestore can." Standard Persistent Disks are fundamentally single-writer (`ReadWriteOnce`); genuine simultaneous multi-Pod read/write access requires Filestore (`ReadWriteMany`) or an application-level distributed storage solution, not a Persistent Disk.

## 31.11 Interview Questions

**🎯 Beginner:** _What does it mean for a GKE cluster to be "VPC-native," and why does it matter?_
**Model answer:** VPC-native means Pod and Service IPs are allocated from secondary (alias) IP ranges of the cluster's VPC subnet rather than a separate overlay network, giving Pods real, routable addresses within the VPC. This matters because it lets standard VPC constructs — firewall rules, Flow Logs, Shared VPC, Private Service Connect — see and act on Pod traffic directly, and avoids the performance overhead of overlay encapsulation.

**🎯 Intermediate:** _When would you choose Filestore over a Persistent Disk for a GKE workload's storage?_
**Model answer:** Persistent Disks are block storage, fundamentally `ReadWriteOnce` (attachable as read-write to only one node/Pod at a time, with narrow exceptions), making them a good fit for a single-writer workload like a database's data directory. Filestore is managed NFS, natively `ReadWriteMany`, so any workload where multiple Pod replicas need genuinely simultaneous read-write access to the same files — shared uploads directories, shared configuration, multi-replica content management systems — needs Filestore, since a Persistent Disk cannot satisfy that access pattern.

**🎯 Senior/Architect:** _Design the networking approach for a GKE cluster that needs to expose 15 microservices over HTTPS with path-based routing, integrate with existing VPC firewall rules, and support canary traffic splitting for new releases._
**Model answer:** I'd provision a VPC-native cluster with generously sized Pod and Service secondary ranges up front (accounting for expected scale, since resizing later is constrained), so all 15 microservices' Pods get real VPC IPs that existing VPC firewall rules can reference directly without cluster-specific exceptions. For exposure, I'd use the Gateway API rather than legacy Ingress specifically because of the traffic-splitting requirement — `HTTPRoute` resources support weighted traffic splitting natively, letting a canary release route, say, 5% of traffic to a new version's Service without a separate load balancer or manual DNS trickery. Path-based routing across the 15 services maps cleanly to multiple `HTTPRoute` rules attached to one shared `Gateway`, which provisions a single GCP HTTP(S) Load Balancer with a shared external IP and certificate, rather than 15 separate load balancers. I'd also default new stateful services in this architecture to regional Persistent Disks or Filestore depending on their single- vs multi-writer needs, consistent with the storage guidance above.

## 31.12 Key Takeaways

- 🔑 VPC-native clusters assign Pods and Services real, routable VPC IPs via alias IP ranges, avoiding overlay-network overhead and integrating natively with VPC firewall rules, Flow Logs, and Shared VPC.
- 🔑 Services provide a stable virtual IP and DNS name decoupling clients from individual Pods' ephemeral IPs; `LoadBalancer`-type Services provision real GCP load balancers automatically.
- 🔑 GKE Ingress and the newer Gateway API both provision GCP HTTP(S) Load Balancers from Kubernetes-native manifests; Gateway API is the actively developed, more capable long-term path, especially for traffic-splitting scenarios.
- 🔑 Persistent Disks (via CSI) are single-writer block storage; Filestore (via CSI) is multi-writer shared file storage — choosing correctly between them depends entirely on whether a workload needs simultaneous multi-Pod write access.

## 31.13 Related Concepts

GKE architecture and node pools (Section 30), VPC subnets and alias IP ranges (Section 20), Cloud Load Balancing internals (Section 22), Persistent Disks and Filestore as standalone GCP services (Section 12), and Shared VPC/Private Service Connect (Section 25) all build directly on the networking and storage model introduced here.

# Part 3 · Section 4 — EC2 Storage, Networking & Security Integration

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** An EC2 instance alone is just compute — it needs disks to store data, a network identity to talk to other things, and permissions to act on your behalf.

**Precise:** This section covers EC2's integration points with **EBS** (block storage), **VPC networking** (ENIs, security groups, subnets), and **IAM** (instance profiles) — the mechanisms making a compute instance addressable, persistent, and securely authorized.

---

## 2. EBS Integration (preview; full depth Part 5)

### 2.1 What EBS Provides

- **EBS** volumes are network-attached block storage — independent of any specific instance (unlike instance store), connecting over the network while behaving like a local disk.
- This independence enables stop/start persistence (Section 1 §4.1) — the volume can reattach after the underlying hardware changes.

### 2.2 Volume Types — Quick Orientation

- **gp2/gp3 (General Purpose SSD)** — balanced, default choice.
- **io1/io2 (Provisioned IOPS SSD)** — I/O-intensive workloads needing consistent guaranteed performance.
- **st1 (Throughput Optimized HDD) / sc1 (Cold HDD)** — lower-cost, higher-latency for large sequential/infrequent workloads.

### 2.3 EBS Snapshots — The AMI Connection

- **Incremental, point-in-time backups** stored in S3 (not directly browsable) — exactly the mechanism behind AMI creation (Section 2 §4.1).
- Each snapshot after the first stores only **changed blocks** — relevant to cost hygiene (unused snapshots accumulate charges).

### 2.4 Multi-Attach and Instance Store Interaction

- Most EBS types attach to one instance at a time; some Provisioned IOPS volumes support **Multi-Attach** across multiple instances in the same AZ — application must manage concurrent access itself (no file-locking provided).
- An instance can have both EBS (persistent) and instance store (ephemeral, high-speed scratch) simultaneously — not mutually exclusive.

---

## 3. Elastic Network Interfaces (ENIs) (preview; full depth Part 4)

### 3.1 Definition

An **ENI** is a virtual network card — gives an instance its IP address(es), MAC address, and security group associations. Every instance has at least one primary ENI, created automatically.

### 3.2 Why ENIs Are Distinct and Detachable

- An ENI can be **detached from one instance and attached to another** (same AZ) — enables failover: move the ENI (and its private/Elastic IP) to a standby, preserving network identity without DNS changes.
- **Multiple ENIs per instance** (larger types) — each potentially in a different subnet (same AZ) — used for network-tier separation or appliance/firewall architectures bridging subnets.

### 3.3 Security Groups — Instance-Level Firewall (full depth Part 4)

- Attach to **ENIs** (thus instances), not subnets — the key distinction from NACLs.
- **Stateful** — return traffic auto-allowed regardless of outbound rules.
- **Allow-only** — no explicit Deny rules (unlike IAM); anything not allowed is implicitly denied. Deny rules live in NACLs (Part 4).
- **Multiple SGs per ENI** — effective rules are the **union** of all attached groups, parallel to IAM group-based composition.

---

## 4. IAM Integration — Instance Profiles (reiterated from §11.8)

- An instance holds an **instance profile** wrapping exactly one IAM role; the app retrieves temp credentials via IMDS.
- **Attached at launch** or changeable on a running instance — **changing the role doesn't require a stop/start**; the instance just starts receiving different IMDS credentials.
- **IMDSv2 enforcement** should be a launch-time setting (in launch templates, §6); retrofitting on running instances requires explicit modification.

---

## 5. Enhanced Networking and Instance Network Performance

- **Enhanced Networking (ENA)** — higher bandwidth, higher PPS, lower inter-instance latency than older virtualized networking, enabled by Nitro offloading.
- **Network performance scales with instance size** within a family — matters for right-sizing network-throughput-sensitive workloads too, not just CPU/memory.
- **Placement groups + enhanced networking work together** — cluster group's low-latency benefit is realized _through_ enhanced networking.

---

## 6. Launch Templates — Bringing It Together

### 6.1 Definition

A **Launch Template** is a saved, versioned configuration specifying everything to launch an instance — AMI, instance type, key pair, security groups, storage, IAM instance profile, user data, placement group.

### 6.2 Why They Matter Beyond Convenience

- **Auto Scaling Groups (Section 5) require a Launch Template** to know what to launch — the direct bridge from Sections 1–4 into automated scaling.
- **Versioning** — update the "current" AMI/instance type for future launches without touching running instances — connects to Section 2 §10's golden-image rollout pattern.

---

## 7. Production & Enterprise Usage

- **Multi-ENI architectures** common in network-appliance deployments (firewalls, VPN appliances on EC2) bridging subnets.
- **EBS + instance store combined** — standard for self-managed databases: instance store for temp/cache, EBS for durable data files.
- **Launch Templates as the IaC bridge** — Terraform/CloudFormation-managed fleets define Launch Templates as code (Part 9), version-controlling instance config like application code.
- **Security group sprawl management** — standardize a small library of reusable, purpose-scoped groups ("web-tier-sg," "db-tier-sg") rather than ad hoc per-team groups — parallel to §9's group-based IAM principle.

---

## 8. Security Considerations

- **Scope security groups as tightly as IAM policies** — an all-ports-all-sources SG is the network equivalent of an overbroad IAM policy.
- **EBS encryption** should be enabled by default, enforceable account-wide via an encryption-by-default setting.
- **Detaching an ENI doesn't delete it** — useful for failover, but a forgotten unused ENI with an Elastic IP still incurs the idle-IP charge (Section 1 §7).

---

## 9. Performance Considerations

- **EBS performance can be bottlenecked by the instance's own EBS bandwidth ceiling**, not just the volume's provisioned IOPS — a common real-world mismatch worth checking explicitly.
- **Enhanced networking and placement groups compound** — neither alone delivers full benefit where extreme low latency is genuinely required.

---

## 10. Troubleshooting

| Symptom                                          | Cause                                                                             | Fix                                                                  |
| ------------------------------------------------ | --------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Instance can't reach internet despite correct SG | Subnet's route table lacks a route to an internet gateway (routing issue, not SG) | Check subnet routing (Part 4) — SGs are necessary but not sufficient |
| App gets AccessDenied calling AWS APIs           | No instance profile attached, or role lacks permission                            | Verify instance profile attached and role permissions correct        |
| EBS volume underperforms vs provisioned IOPS     | Instance type's own EBS bandwidth limit is the bottleneck                         | Choose an instance type/size with sufficient EBS-optimized bandwidth |
| Failover doesn't preserve original IP            | Relying on default IP instead of a movable ENI/Elastic IP                         | Use a detachable ENI (with/without Elastic IP) for this pattern      |

---

## 11. Best Practices & Anti-Patterns

**Best practices:** use EBS for anything needing persistence, instance store only for ephemeral/reproducible data; enable EBS encryption by default account-wide; scope security groups tightly with reusable purpose-named groups; use Launch Templates (not manual launches/deprecated Launch Configurations), version-controlled via IaC; attach instance profiles at launch, never static credentials.

**Anti-patterns:** critical data on instance store; overly broad security groups "to avoid headaches"; manual one-off production launches causing drift; forgotten detached ENIs with associated Elastic IPs.

---

## 12. Common Misconceptions

- "Security groups can have Deny rules." → False — allow-only; Deny lives in NACLs.
- "Storage and network identity are tied to the instance together." → False — both EBS volumes and ENIs are independently detachable/reattachable, enabling persistence and failover.
- "Changing an instance's IAM role requires a stop." → False — takes effect on a running instance.
- "High-IOPS EBS guarantees high performance regardless of instance type." → False — instance-side EBS bandwidth can bottleneck it.

---

## 13. Interview Questions (with model answers)

**🟢 EBS vs instance store?** EBS: network-attached, independent of the instance, persists through stop/start and can move between instances. Instance store: physically attached local disk, higher raw I/O, but data lost on stop/hardware failure since tied to that one host.

**🟢 Are security groups stateful or stateless?** Stateful — allowing inbound traffic auto-allows the corresponding outbound return traffic regardless of outbound rules. Different from NACLs, which are stateless and need explicit rules both directions.

**🟡 Architect failover preserving network identity without DNS change?** Use a detachable ENI, possibly with an associated Elastic IP. On failure, detach from the failed instance, attach to the standby — the standby inherits the private IP/MAC/Elastic IP immediately, no DNS propagation wait.

**🟡 High-IOPS EBS volume underperforming — what to check?** The instance type's own EBS bandwidth limit, not just the volume's provisioned IOPS — every instance type has a throughput ceiling to EBS; a high-IOPS volume on an insufficiently-provisioned instance bottlenecks at the instance level. Fix: larger/EBS-optimized instance type.

**🔴 Design storage/networking for a self-managed DB cluster needing high write throughput and fast failover?** Provisioned IOPS EBS sized to actual DB needs, paired with an instance type whose EBS-optimized bandwidth can deliver that throughput (check both sides). Instance store for ephemeral scratch (temp tablespaces) on a supporting instance type, understanding data loss risk. Detachable ENI (+Elastic IP) for standby to inherit primary's identity within seconds, not DNS TTL-dependent. Tightly scoped security groups (specific ports/source SGs, not broad CIDRs). EBS encryption enabled account-wide by default.

**🔴 Prevent configuration drift across a large EC2 fleet built by different teams over years?** Root cause: manual one-off launches and ad hoc per-team SGs instead of a shared source of truth. Standardize Launch Templates as code (CloudFormation/Terraform) — AMI, instance type, instance profile, SGs all declared/version-controlled. Standardize a reusable security group library, parallel to IAM groups. Use Config rules checking running instances match expected Launch Template versions/approved AMIs, flagging out-of-pipeline launches — turns drift into a continuously detected, not just launch-time-prevented, concern.

---

## 🔑 Key Takeaways

1. EBS and instance store are a genuine persistence-vs-performance trade-off — EBS's network-attached independence enables stop/start and reattachment; instance store delivers higher raw I/O but is ephemeral.
2. ENIs, not instances, carry network identity — detachable/reattachable, enabling fast DNS-free failover.
3. Security groups are stateful, allow-only, instance-level, additive across multiple groups — the network parallel to IAM's group-based least-privilege philosophy.
4. Instance profiles deliver IAM roles via IMDS, changeable on a running instance without a stop/start.
5. Launch Templates are the versioned, IaC-friendly bridge between Sections 1–4 and Section 5's Auto Scaling — the "recipe" enabling automated, consistent, driftless provisioning.

## 🌐 Related Concepts (forward links)

- EBS volume types, snapshots, lifecycle in full depth → Part 5
- VPC, subnets, route tables, NACLs, ENIs in full networking depth → Part 4
- Auto Scaling Groups consuming Launch Templates → §23

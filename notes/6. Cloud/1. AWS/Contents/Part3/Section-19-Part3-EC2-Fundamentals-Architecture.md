# Part 3 · Section 1 — EC2 Fundamentals & Architecture

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** EC2 lets you rent a virtual computer in an AWS data center, turn it on, use it like a normal server, and turn it off when done — paying only for the time it ran.

**Precise:** **Amazon EC2** is AWS's **IaaS compute service** providing resizable, on-demand virtual servers (instances), giving you control over the OS and everything above it, while AWS manages the underlying hardware and virtualization layer (§3's IaaS split, made concrete).

---

## 2. Why It Exists

- The literal mechanism behind "trade capital expense for variable expense" (§1) — provision a virtual server in seconds, pay per time unit.
- Embodies elasticity (§4) — launch more on demand, terminate when done, rather than owning fixed peak capacity.
- As IaaS (§5), EC2 gives maximum control (OS choice, installed software, config) in exchange for maximum responsibility (§3) — you patch/secure the guest OS and everything above the hypervisor.

---

## 3. What "Instance" Means

- A **virtual machine** — AWS physical hosts run a **hypervisor** partitioning one machine into multiple isolated VMs (instances).
- **AWS's current hypervisor: the Nitro System** — offloads virtualization overhead (networking, storage) to dedicated Nitro cards, freeing the main CPU, delivering near-bare-metal performance despite virtualization.
- **Multi-tenancy in action:** multiple customers can share a physical host, isolated by the hypervisor — AWS is responsible for that isolation boundary ("security of the cloud," §3).

---

## 4. EC2 Instance Lifecycle — States

| State         | Meaning                     | Billed compute? | Billed EBS storage?               |
| ------------- | --------------------------- | --------------- | --------------------------------- |
| Pending       | Launching                   | No              | N/A                               |
| Running       | Active                      | **Yes**         | Yes                               |
| Stopping      | Transitioning to stopped    | No              | Yes                               |
| Stopped       | Off (EBS-backed only)       | **No**          | **Yes**                           |
| Shutting-down | Transitioning to terminated | No              | N/A                               |
| Terminated    | Permanently deleted         | No              | No (unless volume set to persist) |

### 4.1 Stop vs Terminate

- **Stop** — shuts down but not deleted; EBS root volume persists; can restart later (same instance ID, typically different physical host, same AZ). No compute billing, but EBS storage still billed.
- **Terminate** — permanently destroyed; root EBS volume deleted by default (configurable via "Delete on Termination"); instance ID never reused.
- **Instance store-backed instances can only be terminated**, not stopped — their storage is physically tied to the host; stopping would lose it anyway.

> 🎯 "Why can't some instances be stopped?" — the storage-type dependency (§4.2) is the real reasoning, not just a memorized rule.

### 4.2 Root Volume Types

- **EBS-backed** (majority of usage) — network-attached storage (Part 5), persists independently of the host, enables stop/start.
- **Instance store-backed** — physically attached local disk, very high I/O, **ephemeral** (lost on stop or hardware failure). Used for temp data, caches, buffers where persistence doesn't matter.

---

## 5. Instance Metadata and User Data

- **IMDS** — provides an instance info about itself (instance ID, AMI ID, security groups, network config, IAM role's temp credentials) via a local non-routable address, queryable only from within.
- **User Data** — script executed automatically **once, on first boot** by default — the standard bootstrapping mechanism (install software, apply config, join a cluster).
- **IMDSv2** (§11.8) — hardened, session-token-based; a modern security baseline against SSRF-based credential theft.

---

## 6. Placement and Tenancy

### 6.1 Placement Groups

- **Cluster** — packs instances close together in one AZ, high-bandwidth low-latency networking. Best for tightly-coupled HPC/big-data workloads. Trade-off: correlated failure risk.
- **Spread** — each instance on distinct hardware, minimizing correlated failure. Best for a small number of individually critical instances (hard limit per AZ per group).
- **Partition** — logical partitions on distinct hardware; instances within a partition may share hardware. Best for partition-aware distributed systems (Hadoop, Cassandra, Kafka).

> 🔑 A genuine performance-vs-availability trade-off: cluster = performance at availability cost, spread = availability at performance cost, partition = structured middle ground for partition-aware software.

### 6.2 Tenancy Options

- **Shared (default)** — hardware potentially shared with other customers, isolated by hypervisor.
- **Dedicated Instance** — hardware dedicated to your account (may still run other instances of yours at different times).
- **Dedicated Host** — entire physical server allocated to you, visibility/control over sockets/cores — for licensing tied to physical cores, or strict compliance requiring physical isolation.

---

## 7. Elastic IP Addresses (preview; full depth Part 4)

- Static public IPv4 address, remains constant across stop/start (unlike default public IPs), remappable to a different instance for failover.
- **Cost nuance:** charged when allocated but **not associated with a running instance** — discourages hoarding scarce public IPv4 addresses (§6 cost governance).

---

## 8. AMIs — First Look (full depth Section 2)

- An **AMI (Amazon Machine Image)** is the template an instance launches from — packages OS, pre-installed software, config. AMI = blueprint, instance = the running thing built from it.

---

## 9. Production & Enterprise Usage

- **EC2 underlies higher-level services** — Elastic Beanstalk, ECS-on-EC2, and some managed services ultimately run on EC2 (§27).
- **Right-sizing** — continuous review of instance size vs actual CloudWatch utilization, not a one-time launch decision (§6 cost discipline).
- **Nitro's security relevance:** offloading virtualization to dedicated hardware means AWS states even AWS operators have no mechanism to access customer instance memory on Nitro-based instances — a concrete technical detail strengthening the Shared Responsibility Model's infrastructure commitment.

---

## 10. Security Considerations

- Guest OS patching remains entirely customer responsibility regardless of instance type/generation (§3, §16 Inspector).
- IMDSv2 enforcement should be default for every new instance.
- Security groups (full depth Part 4) are the primary instance-level network access control — scope as tightly as IAM least privilege demands.

---

## 11. Performance Considerations

- Instance family/size (full depth Section 2) is the primary lever; placement groups matter for latency-sensitive, tightly-coupled workloads specifically.
- EBS-backed vs instance-store is a genuine trade-off (persistence vs raw local I/O), not strictly-better-or-worse.

---

## 12. Troubleshooting

| Symptom                                     | Cause                                                             | Fix                                                                                   |
| ------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Instance won't stop, only terminate offered | Instance store-backed root volume                                 | Expected — plan for data loss or use EBS-backed if persistence needed                 |
| Data lost after stop/restart                | Data was on instance store, or a misconfigured EBS delete setting | Use EBS-backed persistent volumes; verify Delete on Termination settings              |
| Public IP changed after stop/start          | Default public IPs aren't static — expected                       | Use an Elastic IP if a constant address is required                                   |
| User data script didn't run as expected     | Runs on first boot only by default                                | Understand the default; use cloud-init directives if re-execution is genuinely needed |

---

## 13. Best Practices & Anti-Patterns

**Best practices:** use EBS-backed instances for stop/start persistence needs; enforce IMDSv2 on every instance; use Elastic IPs only when genuinely needed and release unused ones; choose placement groups deliberately per workload; right-size continuously using CloudWatch data.

**Anti-patterns:** assuming all instances can be stopped; storing important non-reproducible data on instance store; leaving Elastic IPs allocated but unassociated; using cluster placement groups for workloads that don't need low inter-instance latency.

---

## 14. Common Misconceptions

- "Stopping is basically the same as terminating, just reversible." → Not precisely — stopping preserves the instance/EBS root volume; terminating destroys both permanently by default.
- "Public IP stays the same across stop/start." → False by default — changes unless an Elastic IP is used.
- "User data re-runs every boot." → False — runs once on first boot by default.
- "EC2 instances run on dedicated hardware by default." → False — shared tenancy is default; dedicated hardware is an explicit, pricier choice.

---

## 15. Interview Questions (with model answers)

**🟢 What is Amazon EC2?** AWS's IaaS compute service providing resizable, on-demand virtual servers (instances). Full control over guest OS and above; AWS manages hardware and virtualization — a direct IaaS example of the Shared Responsibility Model.

**🟢 Stop vs terminate?** Stop shuts down but keeps the instance and EBS root volume intact — restartable later (same ID, typically different hardware); no compute billing, storage still billed. Terminate permanently deletes the instance and (by default) root volume; ID never reused. Instance store-backed instances can only be terminated — storage is physically tied to the host.

**🟡 Cluster vs spread placement group — when to choose which?** Cluster: close together, high-bandwidth low-latency, ideal for tightly-coupled HPC/big-data — but correlated failure risk. Spread: distinct hardware, minimizes correlated failure — for a small number of individually critical instances where isolation matters more than inter-instance network performance. A genuine trade-off, not strictly better/worse.

**🟡 Why can't instance store-backed instances be stopped?** Instance store is physically attached to the specific host. Stopping releases the host back to AWS's pool for potential relaunch elsewhere — but the data can't travel with it. Since stopping would lose the data anyway, AWS only offers terminate, making the ephemeral nature explicit.

**🔴 Architect placement for a short HPC burst + a small set of business-critical control-plane instances?** HPC burst: cluster placement group in one AZ, accepting correlated-failure trade-off since short-lived and performance genuinely matters. Control-plane instances: spread placement group, prioritizing hardware isolation since few in number and individually critical without HPC's tight-coupling pattern. Don't mix the two — the goals are in tension, need separate strategies matched to requirements.

**🔴 How does the Nitro System change the EC2 security conversation?** Traditional virtualization runs hypervisor functions on the same general-purpose CPU as customer workloads — larger attack surface, performance overhead. Nitro offloads those functions to dedicated cards separate from the main system board: near-bare-metal performance despite virtualization, and (security-relevant) AWS states not even AWS operators have a mechanism to access customer instance memory on Nitro-based instances. Substantiates "AWS secures the infrastructure" with actual hardware architecture, not just policy statement.

---

## 🔑 Key Takeaways

1. EC2 is AWS's IaaS compute service — maximum control (and responsibility) over the guest OS and above; AWS manages hardware/virtualization via the Nitro System.
2. Stop vs terminate is critical: stop preserves the instance/EBS volume for restart; terminate permanently destroys it. Instance store-backed instances can only be terminated.
3. User data bootstraps on first boot only by default; IMDS/IMDSv2 delivers metadata and temp role credentials from within the instance.
4. Placement groups are a genuine performance-vs-isolation trade-off: cluster (performance, correlated risk), spread (isolation), partition (structured middle ground).
5. Elastic IPs are static/remappable but cost money when idle — discourages wasted public IPv4 allocation.

## 🌐 Related Concepts (forward links)

- AMIs, instance types/families, instance lifecycle in full depth → §20
- EC2 storage (EBS types), networking (security groups, ENIs), IAM integration → §22
- CloudWatch-based right-sizing and monitoring → Part 8

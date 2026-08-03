# Part 3 · Section 6 — Elastic Load Balancing (ELB)

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** A load balancer sits in front of your fleet, receiving all traffic and distributing it across healthy, available instances — users never talk to a specific instance directly, and instances can come and go via Auto Scaling transparently.

**Precise:** **Elastic Load Balancing (ELB)** is AWS's managed service for automatically distributing incoming traffic across multiple targets (EC2, containers, IPs, Lambda) in one or more AZs, performing continuous health checks and routing only to healthy targets.

---

## 2. Why It Exists

- ASGs constantly launch/terminate instances — direct client connections to a specific instance would break on every scaling event. ELB provides a stable entry point abstracting the changing fleet.
- Multi-AZ traffic distribution actively delivers §2's HA architecture — spans AZs, routes only to healthy targets, so a single AZ failure doesn't take down the app.
- Application-aware health checking is what makes self-healing meaningful — ELB performs the checks ASG acts on.

---

## 3. Load Balancer Types

### 3.1 Application Load Balancer (ALB) — Layer 7

- Understands HTTP/HTTPS — routes on URL path, hostname, headers, query strings, method.
- **Content-based routing** — the defining capability: `/api/*` -> one target group, `/images/*` -> another, or host-based multi-app routing.
- Best for: modern web apps, microservices needing path/host routing, any HTTP/HTTPS workload.

### 3.2 Network Load Balancer (NLB) — Layer 4

- Routes on TCP/UDP/TLS without inspecting content — extremely high-performance, low-latency.
- **Static IP support** per AZ (unlike ALB's DNS-only) — relevant for firewall allowlisting.
- Best for: extreme performance, non-HTTP TCP/UDP, static IP requirements.

### 3.3 Gateway Load Balancer (GWLB) — Layer 3

- Deploys/scales/manages third-party network appliances (firewalls, IDS/IPS); inserts traffic through them for inspection via GENEVE encapsulation.
- Best for: centralizing traffic inspection through security appliances (connects to §17's Network Firewall).

### 3.4 Classic Load Balancer (CLB) — Legacy

- Original offering, Layer 4 + limited Layer 7 — AWS's current guidance: use ALB or NLB for new workloads.

> 🎯 ALB when routing depends on HTTP content; NLB for extreme performance/static IP/non-HTTP; GWLB for appliance insertion; CLB legacy.

---

## 4. Core Components

### 4.1 Listeners

Check for connections on a specific protocol/port; a load balancer can have multiple listeners.

### 4.2 Target Groups

Named collection of targets that traffic routes to; the group's own health check config determines eligibility.

- **Instance** — by EC2 instance ID, integrates with ASGs.
- **IP** — direct IP targeting, including on-prem resources via VPN/Direct Connect.
- **Lambda** — ALB routes directly to a Lambda function (Section 7).

### 4.3 Rules (ALB-specific)

Ordered condition-to-action rules (forward, redirect, fixed response), evaluated in priority order with a default catch-all rule — the mechanism implementing content-based routing.

---

## 5. Health Checks

- Each target group defines protocol, port, path, interval, timeout, healthy/unhealthy threshold.
- A failing target is **removed from traffic rotation** — the LB just stops routing to it; instance termination is a separate ASG decision (Section 5 §6).
- **Handoff:** ELB detects the application-level failure; ASG acts on that detection by replacing the instance.

---

## 6. Connection Draining / Deregistration Delay

- When a target is removed (health failure, scale-in, manual deregistration), the LB can keep routing already-established connections for a configurable **deregistration delay** while sending no new requests — the mechanism behind Section 5 §9's graceful termination.
- Without it, abrupt removal cuts off in-flight requests, causing user-facing errors.

---

## 7. Cross-Zone Load Balancing

- Controls whether traffic distributes evenly across **all targets in all AZs**, or only evenly within the AZ that received the request.
- Without it, an AZ with fewer targets gets a disproportionate traffic share relative to its target count.
- **Cost nuance:** can introduce cross-AZ data transfer charges in some ALB configurations (§6 §4).

---

## 8. SSL/TLS Termination

- LB can terminate TLS, decrypting at the load balancer, then communicating with backends over HTTP or re-encrypted TLS.
- Centralizes certificate management via **AWS Certificate Manager** rather than every backend instance managing its own cert.
- **WAF connection:** WAF attaches to ALB precisely because the ALB is where HTTP/HTTPS requests are processed/terminated (§17).

---

## 9. Sticky Sessions (Session Affinity)

- Default: requests distributed without regard to prior requests — appropriate for stateless apps.
- **Sticky sessions** (cookie-based) force a client's requests to the same target — needed only when session state is stored locally on the instance.
- **Trade-off:** works against even load distribution, complicates scaling (can't gracefully remove a target with active sticky sessions). Better fix: externalize session state (ElastiCache/DynamoDB, Part 6) so stickiness isn't needed.

---

## 10. Production & Enterprise Usage

- **ALB standard for modern web/microservices** — path-based routing supports multiple services behind one LB, reducing LB count/cert management overhead.
- **NLB for extreme performance/non-HTTP** — gaming backends, IoT ingestion, any TCP protocol, or static IP requirements.
- **Multi-tier load balancing:** internet-facing ALB in public subnets -> internal ALB/NLB in private subnets for service-to-service traffic (Part 4 preview).
- **Blue/green and canary via weighted target groups** (Part 9) — ALB rule splits traffic by percentage across two target groups for gradual, low-risk rollouts.

---

## 11. Security Considerations

- LB's own security group controls external access; **target security groups should only allow traffic from the load balancer**, pushing internet exposure entirely to the LB layer.
- TLS termination centralizes security policy enforcement (ciphers/TLS versions) at one point.
- WAF integration happens at the ALB layer — the natural centralized inspection point for all inbound traffic.

---

## 12. Performance Considerations

- NLB's Layer 4 simplicity (no content inspection) is precisely why it outperforms ALB — a deliberate trade-off, not "just a faster ALB."
- Cross-zone load balancing's even-distribution benefit matters for consistency when AZ target counts are temporarily uneven (e.g., rolling deployments).

---

## 13. Troubleshooting

| Symptom                                             | Cause                                                                       | Fix                                                                    |
| --------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Targets unhealthy despite working directly          | Health check path/port misconfigured, or target SG doesn't allow LB traffic | Verify health check config; confirm target SG allows LB's SG           |
| Errors during deployment/scale-in                   | No deregistration delay, or uncoordinated ASG lifecycle hook                | Configure deregistration delay; ensure in-flight requests can complete |
| Uneven AZ traffic despite equal target counts       | Cross-zone load balancing disabled                                          | Enable it (aware of possible cross-AZ transfer cost)                   |
| A client always lands on the same overloaded target | Sticky sessions enabled unnecessarily                                       | Disable if app doesn't need it; consider externalizing session state   |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** choose LB type by actual requirement (ALB/NLB/GWLB), not habit; restrict target SGs to LB-only traffic; configure deregistration delay coordinated with ASG lifecycle hooks; terminate TLS at the LB with centralized ACM certs; externalize session state instead of relying on sticky sessions.

**Anti-patterns:** using CLB for new architectures without a migration-blocking reason; leaving target SGs open to the internet in addition to the LB; ignoring deregistration delay; treating sticky sessions as permanent architecture.

---

## 15. Common Misconceptions

- "LB terminating traffic to an unhealthy target also terminates the instance." → False — LB just stops routing; ASG (or a human) decides replacement.
- "NLB is just a faster ALB." → False — a genuinely different layer/capability set; performance is a consequence of no content inspection.
- "Cross-zone load balancing has no trade-off." → False — can introduce cross-AZ data transfer charges.
- "Sticky sessions are required for any app with logins." → False — only needed if session state is stored locally on the instance.

---

## 16. Interview Questions (with model answers)

**🟢 ALB vs NLB?** ALB: Layer 7, HTTP/HTTPS content-aware, routes by path/host/headers — ideal for web apps/microservices. NLB: Layer 4, TCP/UDP without content inspection, extremely high-performance, static IP per AZ — better for extreme performance, non-HTTP, or static-IP needs.

**🟢 How does a load balancer know which targets are healthy?** Each target group has its own health check config (protocol/port/path/interval/timeout/threshold). LB continuously checks; a target crossing the unhealthy threshold is removed from routing — without necessarily being terminated, which is a separate ASG decision.

**🟡 Why use sticky sessions, and what's the downside?** Needed when session state is stored locally on the instance rather than externalized. Downside: works against even load distribution, complicates graceful target removal. Better long-term fix: externalize session state (e.g., ElastiCache) so the app is genuinely stateless.

**🟡 How do deregistration delay and an ASG lifecycle hook work together on scale-in?** Deregistration delay keeps routing established connections to a removed target for a window while sending no new requests, letting in-flight requests finish. The ASG lifecycle hook pauses actual termination for custom cleanup (draining, log shipping). Together: LB-side graceful removal + instance-side cleanup, nothing abruptly cut off.

**🔴 Design LB architecture for a microservices app with a public frontend, internal backends, and WAF inspection requirement?** Internet-facing ALB in public subnets as the single entry point, path/host-based rules to different target groups. WAF attached directly to this ALB (natural centralized inspection point). Internal backends: internal ALB (if content routing needed) or NLB (raw internal performance) in private subnets. Each target group has a tailored health check; target SGs only allow traffic from their respective LB's SG. TLS terminated at the public ALB via ACM; internal hops HTTP or re-encrypted TLS per internal trust requirements.

**🔴 Implement a gradual canary rollout with instant rollback via ELB?** New version as a separate target group behind the same ALB; weighted target group rule splits traffic by percentage (start 95/5). Monitor new group's health checks and CloudWatch error-rate metrics, gradually shift weight as confidence builds. Rollback = shift weight back to 100% on the original group instantly — pure routing-weight change, no redeploy/instance replacement, making it fast and low-risk. Target group health checks still auto-pull genuinely broken instances regardless of weight split.

---

## 🔑 Key Takeaways

1. ELB provides a stable entry point abstracting a constantly-changing fleet — directly enabling Auto Scaling without breaking client connections.
2. ALB (L7, content routing), NLB (L4, performance/static IP), GWLB (appliance insertion) serve distinct purposes by actual requirement; CLB is legacy.
3. ELB health checks are the detection mechanism; the ASG's decision is the action — this handoff matters more than knowing either feature alone.
4. Deregistration delay + ASG lifecycle hooks work together for graceful scale-in — LB-side and instance-side of avoiding abrupt cutoffs.
5. TLS termination and WAF integration both centralize at the load balancer layer — a single point for cert management and inbound inspection.

## 🌐 Related Concepts (forward links)

- VPC subnets, public/private architecture, Route 53 integration with ELB → Part 4
- AWS Certificate Manager for TLS → Part 4
- Blue/green and canary deployment strategies in full depth → Part 9
- AWS Lambda as an ALB target → §25 (next)

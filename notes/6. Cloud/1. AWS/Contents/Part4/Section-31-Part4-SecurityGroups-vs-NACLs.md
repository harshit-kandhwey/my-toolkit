# Part 4 - Section 3 - Security Groups vs NACLs - Full Depth

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: Security Groups are firewalls attached to individual resources, remembering connection state so return traffic is automatically allowed. Network ACLs are firewalls attached to entire subnets, evaluated per-packet with no memory, and can explicitly deny specific traffic.

Precise: A Security Group is a stateful, instance/ENI-level virtual firewall supporting allow-only rules. A Network ACL (NACL) is a stateless, subnet-level virtual firewall supporting both allow and explicit deny rules, evaluated in numbered order.

---

## 2. Why Two Layers Exist

- Defense in depth at the network layer - a Security Group misconfiguration is caught by NACL rules and vice versa, rather than relying on one perfectly-correct firewall.
- Different scopes solve different problems - a Security Group protects a specific resource regardless of subnet; a NACL protects an entire subnet regardless of specific resources. Genuinely complementary, not redundant.

---

## 3. Security Groups - Full Mechanics

### 3.1 Stateful Behavior

- Automatically tracks connection state: allowed inbound traffic auto-allows the corresponding outbound response regardless of outbound rules, and vice versa.
- Practically: you typically only write inbound rules for a web server; no matching outbound rule needed for responses.

### 3.2 Allow-Only, No Explicit Deny

- Cannot contain a Deny rule - every rule is Allow; anything not explicitly allowed is implicitly denied (default-deny, Part 2 Section 2, at the network layer).
- This is precisely why NACLs exist as a complement - explicit blocking of a specific source requires a NACL.

### 3.3 Rule Structure

- Each rule specifies type (protocol/port), source/destination (a CIDR block OR another Security Group ID), and direction (inbound/outbound).
- Referencing a Security Group as the source is a powerful pattern: a database's SG allows inbound from the app tier's SG ID rather than an IP range - automatically stays correct as Auto Scaling changes actual instances/IPs.

### 3.4 Default Security Group Behavior

- A new Security Group denies all inbound by default, allows all outbound by default.

### 3.5 Multiple Security Groups - Union of Rules

- An ENI can have multiple Security Groups attached; the effective rule set is the union of all attached groups' rules - no override concept since there's no Deny to override.

---

## 4. Network ACLs - Full Mechanics

### 4.1 Stateless Behavior

- Evaluates every packet independently, no memory of prior traffic - an allowed inbound request does NOT auto-permit its outbound response; both directions need explicit rules.
- The most common NACL mistake: allowing inbound on a port but forgetting the outbound rule for the ephemeral port range the response uses.

### 4.2 Allow AND Explicit Deny

- Unlike Security Groups, NACLs support both Allow and explicit Deny - useful for blocking a specific known-bad source while allowing broader traffic.

### 4.3 Numbered Rule Evaluation Order

- Rules evaluated in numerical order (lowest first); the first matching rule applies, no further rules evaluated - fundamentally different from Security Groups' "union of all matching Allows."
- The default catch-all rule (highest number) denies everything not matched earlier - an explicit final rule expressing default-deny.
- Rule numbering strategy: space rules (100, 200, 300) to allow inserting new rules later without renumbering.

### 4.4 Subnet-Level Scope

- Associated with one or more subnets; rules apply to every resource in those subnets regardless of individual Security Group config - a NACL Deny cannot be overridden by any Security Group Allow.
- Every subnet has exactly one NACL at a time. Every VPC has a Default NACL, allowing all traffic by default (contrast to Security Groups' default-deny-inbound).

---

## 5. How Security Groups and NACLs Interact

Inbound traffic: Subnet's NACL evaluated first (stateless, rule-number order) - explicit/default Deny blocks it entirely. If allowed, the instance's Security Group(s) evaluated next (stateful, union of Allow rules) - no matching Allow means implicit deny. Only passing both reaches the instance.

For return traffic: the Security Group auto-allows the response (stateful) without a matching outbound rule. But the NACL is stateless and needs its own explicit outbound rule for that same response traffic, or the response is blocked at the NACL layer despite the Security Group having no issue with it.

Key summary: traffic must pass the NACL and Security Group on the way in. On the way out, the Security Group auto-allows the response (stateful), but the NACL needs its own explicit outbound rule - this asymmetry is exactly why "inbound works but responses don't" is a common NACL misconfiguration.

---

## 6. Comparison Table

|                  | Security Group                               | Network ACL                                                      |
| ---------------- | -------------------------------------------- | ---------------------------------------------------------------- |
| Scope            | Instance/ENI level                           | Subnet level                                                     |
| State            | Stateful (return traffic auto-allowed)       | Stateless (must allow both directions explicitly)                |
| Rule types       | Allow only                                   | Allow and explicit Deny                                          |
| Evaluation       | All matching Allow rules apply (union)       | Rules evaluated in number order; first match wins                |
| Default behavior | Deny all inbound, allow all outbound         | Default NACL allows all; custom NACLs deny all until rules added |
| Association      | One or more SGs per ENI                      | Exactly one NACL per subnet                                      |
| Can reference    | Another Security Group as source/destination | CIDR blocks only (no SG reference)                               |

---

## 7. When to Use NACLs Beyond the Default

- Explicit IP-based blocking - blocking a known-malicious IP/range at the subnet level, affecting every resource regardless of individual Security Groups - the one thing Security Groups structurally cannot do.
- A coarse-grained safety net - a subnet-wide backstop rule against a Security Group misconfiguration on any individual instance - defense in depth literally.
- Compliance/audit requirements - some frameworks expect demonstrable network-layer (not just instance-layer) access controls.

Key idea: most real architectures rely primarily on Security Groups for day-to-day access control (stateful, easier to reason about), using NACLs sparingly for their unique capabilities - not as the primary everyday firewall mechanism.

---

## 8. Production & Enterprise Usage

- Security-Group-referencing-Security-Group is the standard tiered-architecture pattern - a chain (DB SG allows from app-tier SG, app-tier SG allows from ALB SG) that automatically adapts as instances scale, without IP-based rules.
- NACLs as a compliance/defense-in-depth backstop - regulated enterprises apply a coarse NACL rule denying traffic between tiers that should never communicate directly, independent of Security Group config.
- Security Group limits at scale - account/region limits on SGs per ENI and rules per SG; large orgs track these deliberately rather than discovering them mid-incident.

---

## 9. Security Considerations

- Least privilege applies to both layers - scope SG rules to the narrowest source (ideally another SG, not 0.0.0.0/0) and port.
- NACLs are the only network-layer explicit-deny mechanism - for "block this specific bad actor," use a NACL rule (or WAF, Part 2 Section 9).
- "Both layers must pass" is itself a security feature - a single misconfigured layer doesn't automatically mean full exposure if the other layer still restricts.

---

## 10. Troubleshooting - The Definitive Checklist

1. Route table (Section 2) - is there a route to the destination at all?
2. NACL, inbound - does the subnet's NACL allow it?
3. Security Group, inbound - does the instance's SG allow it?
4. Security Group, outbound - usually a non-issue (default allow-all), but check if restricted.
5. NACL, outbound - does the subnet's NACL allow the response, including the correct ephemeral port range? (Most commonly missed step.)

| Symptom                                                                 | Cause                                                  | Fix                                                               |
| ----------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------- |
| Inbound works, response never arrives                                   | NACL missing outbound rule for ephemeral port range    | Add outbound NACL rule for the ephemeral range back to the source |
| Traffic blocked despite correct SG rule                                 | A NACL Deny (explicit or default) blocking it upstream | Check subnet's NACL rules in number order for an earlier Deny     |
| DB reachable only via specific IPs, breaks after ASG replaces instances | SG rule referenced a CIDR instead of the app tier's SG | Change rule to reference the app tier's Security Group            |
| Need to block one malicious IP while allowing everything else           | SG can't express explicit deny                         | Use a NACL Deny rule (numbered before broader Allows)             |

---

## 11. Best Practices & Anti-Patterns

Best practices: reference Security Groups as sources/destinations, not CIDR blocks, for intra-VPC tiers; use SGs as the primary everyday mechanism, NACLs sparingly; always configure both inbound and outbound NACL rules including ephemeral ports; leave numbering gaps in NACL rules; walk the full five-step troubleshooting checklist.

Anti-patterns: relying on NACLs as the primary firewall; forgetting outbound NACL rules causing silent one-way failures; hardcoding IP-based SG rules for scaling intra-VPC tiers; assuming an SG Allow guarantees connectivity without checking the NACL.

---

## 12. Common Misconceptions

- "Security Groups can have Deny rules." False - allow-only; explicit Deny is exclusively NACL.
- "Allowing inbound on a NACL auto-allows the response." False - NACLs are stateless; response needs its own explicit outbound rule.
- "A Security Group can only reference IP ranges." False - referencing another Security Group is a powerful, commonly-used capability.
- "NACLs and Security Groups are redundant." False - different scopes and rule capabilities; real architectures often use both deliberately.

---

## 13. Interview Questions (with model answers)

Beginner - Fundamental difference between a Security Group and a NACL? SG: stateful, instance/ENI level, allow-only, implicit deny for anything unmatched, return traffic auto-permitted. NACL: stateless, subnet level, allow AND explicit deny, evaluated in numbered order, no memory - both directions need explicit rules.

Beginner - Can a Security Group block a specific IP? No - allow-only, no explicit Deny capability. Use a NACL instead, which supports explicit Deny rules evaluated before broader Allow rules.

Intermediate - Why reference a Security Group as the source instead of a CIDR block? The rule automatically stays correct as actual instances in that group change - a database SG allowing inbound only from the app tier's SG ID keeps working as Auto Scaling launches/terminates instances with different IPs. CIDR-based rules need constant manual updates or must be overly broad.

Intermediate - NACL allows inbound 443 but the connection still fails - likely cause? NACLs are stateless - allowing inbound doesn't auto-allow the outbound response, which needs its own explicit rule, typically for the client's ephemeral port range, not port 443. If missing, the response never makes it back out despite the inbound request being correctly allowed - a failure mode Security Groups don't have.

Senior - Design SG/NACL strategy for a three-tier app (ALB, app tier, database tier)? Three Security Groups: ALB SG allows inbound 443 from internet; app-tier SG allows inbound only from ALB's SG; database SG allows inbound only from app-tier's SG - a fully chained, scaling-resilient model with no CIDR rules between internal tiers. Leave default NACL allow-all for most subnets, relying on the SG chain. Add an explicit NACL Deny on the database subnet blocking traffic sourced directly from the public subnet's CIDR - a coarse backstop ensuring even an SG misconfiguration on the database can't accidentally expose it, since the NACL blocks it regardless.

Architect - Walk through precisely what happens to an inbound HTTPS request and its response crossing both a NACL and a Security Group? Inbound request hits the subnet's NACL first, rule-number order - any rule up to the default deny-all blocks it entirely regardless of the SG. If NACL allows it, hits the instance's SG next - union of Allow rules across attached groups, any match allows it. Both passing, instance processes and responds. On the way out, the SG auto-permits the response (stateful, recognizes established connection) - no explicit outbound SG rule needed. The NACL has no such memory, so the response must independently satisfy an explicit outbound NACL rule, typically covering the ephemeral port range used. This means NACL rules must always be written as complete two-directional pairs, while SG rules only need the initiating direction - conflating the two models is exactly how "should work but doesn't" connectivity issues happen.

---

## Key Takeaways

1. Security Groups are stateful, instance-level, allow-only - return traffic automatic, no explicit deny capability.
2. NACLs are stateless, subnet-level, support explicit Deny - every direction needs its own rule, source of the most common NACL misconfiguration (missing outbound rules).
3. Traffic must pass BOTH layers inbound, and the asymmetry outbound (SG auto-allows, NACL does not) is the single most important interaction to understand precisely.
4. Referencing a Security Group as a rule's source/destination, not a CIDR block, is the standard pattern for scaling-resilient tiered architectures.
5. Most real architectures use Security Groups as the primary mechanism and NACLs sparingly, for explicit-deny needs and coarse independently-enforced backstops - not two equally-weighted redundant layers.

## Related Concepts (forward links)

- VPC Peering, Transit Gateway, PrivateLink for cross-VPC traffic (still passing through these firewall layers) -> Part 4, Section 4
- WAF as the application-layer complement to these network-layer firewalls -> Part 2, Section 9 (already covered)
- VPC Flow Logs for observing exactly what these layers allowed/denied -> Part 4, Section 9

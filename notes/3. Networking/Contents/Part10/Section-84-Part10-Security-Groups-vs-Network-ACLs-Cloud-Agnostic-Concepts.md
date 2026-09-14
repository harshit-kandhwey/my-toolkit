# Section 84 (Part 10): Security Groups vs. Network ACLs (Cloud-Agnostic Concepts)

## 1. Definition

**Plain language:** In every major cloud, you get two layers of network filtering that look similar but behave very differently. Security groups attach to individual resources (instances, load balancers, database endpoints) and are stateful — allow a request out, and the reply is let back in automatically. Network ACLs attach to a whole subnet and are stateless — every direction of every flow needs its own explicit rule, and rules are evaluated in numbered order until one matches. Mixing up which one you're editing, or forgetting NACLs need both directions, is one of the most common cloud networking mistakes.

**Precise definition:** A **security group** is a **stateful**, resource-attached (instance, ENI, load balancer, managed database endpoint) virtual firewall that evaluates only **allow** rules — there is no explicit deny, only "not matched, therefore implicitly denied" — and automatically permits return traffic for any connection matched by an allow rule, using the same connection-tracking model described conceptually in [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md). A **network ACL** (NACL) is a **stateless**, subnet-attached firewall evaluated as an **ordered list of numbered rules** (both allow and explicit deny), where the first matching rule (by ascending rule number) wins and evaluation stops — and because it's stateless, a NACL requires separate, explicit rules for both the request and its corresponding reply (typically an ephemeral-port-range rule for the reply direction). The two layers are not redundant: a security group is default-deny per-resource and evaluates all matching rules (there's no ordering to reason about), while a NACL is default-deny-until-configured per-subnet and evaluates order-sensitively — different enough in behavior that a common early-career mistake is treating them as interchangeable or applying identical rule logic to both.

> 💡 **Tip:** Memorize this single contrast table: security groups = stateful, allow-only, resource-level, all rules evaluated (no order); NACLs = stateless, allow-and-deny, subnet-level, ordered and first-match-wins. Every practical confusion between the two traces back to forgetting one of these four contrasts.

## 2. Why This Matters

- **This is the single most common source of "why can't my instance talk to X" cloud networking incidents** — an engineer adds an inbound security-group rule expecting it to behave like a NACL rule (or vice versa) and gets unexpected blocking or unexpected access.
- **NACLs are the direct cloud-native embodiment of the stateless filtering concept from [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)**, and security groups are the direct embodiment of stateful filtering — this section is where those two abstract concepts become concrete, everyday tools.
- **The two layers provide genuine defense in depth when used correctly** — a compromised or overly permissive security group is still constrained by the subnet's NACL, and vice versa, which is exactly the layered-defense principle from [§83](Section-83-Part10-Firewall-Placement-Perimeter-Host-Based-and-Segmentation-Patterns.md) applied at the cloud-network level.
- **Rule ordering matters for NACLs in a way it fundamentally doesn't for security groups** — this trips up engineers moving from security-group-only thinking to NACL configuration, where an earlier explicit DENY can silently shadow a later, intended ALLOW.
- **Interview and certification relevance is extremely high** — nearly every cloud networking certification (and every cloud infrastructure interview) tests this exact distinction directly, because it's foundational to reasoning about cloud network security correctly.

## 3. Prerequisites and Dependencies

This section is the direct, concrete cloud application of [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) (stateless vs. stateful filtering) and assumes that distinction is already solid. It also builds on [§83](Section-83-Part10-Firewall-Placement-Perimeter-Host-Based-and-Segmentation-Patterns.md)'s placement patterns, since security groups implement the host-based layer and NACLs implement a stateless segmentation layer at the subnet boundary — the same two of the three placement patterns discussed conceptually there. Some familiarity with cloud VPC/VNet subnet structure is useful background, though the full treatment of that topic is deferred to Part 12 (cloud networking, VPC/VNet concepts), which this section deliberately does not depend on for its core content. [§85](Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md) (Linux firewalling) and [§90](Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md) (network ACLs and micro-segmentation) both extend this section's concepts further, the former into host-OS-level tooling and the latter into finer-grained segmentation patterns.

## 4. Architecture / Conceptual Diagram

```text
                         VPC / VNet
   ┌────────────────────────────────────────────────────────────┐
   │                       SUBNET                                │
   │   ┌──────────────────────────────────────────────────┐     │
   │   │           NETWORK ACL (stateless, ordered)         │     │
   │   │   Rule 100: ALLOW  tcp 443  from 0.0.0.0/0          │     │
   │   │   Rule 110: ALLOW  tcp 1024-65535 (ephemeral reply) │     │
   │   │   Rule *  : DENY   all (implicit final rule)        │     │
   │   │   ◄── evaluated top-to-bottom, first match wins ──►│     │
   │   └──────────────────────┬───────────────────────────┘     │
   │                          │  traffic that passes the NACL     │
   │                          ▼  reaches the instance level        │
   │   ┌──────────────────────────────────────────────────┐     │
   │   │      SECURITY GROUP (stateful, allow-only)         │     │
   │   │   Inbound:  ALLOW tcp 443 from 0.0.0.0/0            │     │
   │   │   Outbound: ALLOW all (default)                     │     │
   │   │   ◄── all rules evaluated, no order, no deny ──►   │     │
   │   └──────────────────────┬───────────────────────────┘     │
   │                          ▼                                    │
   │                    ┌──────────┐                               │
   │                    │ Instance │  reply traffic auto-permitted │
   │                    └──────────┘  by security-group state       │
   └────────────────────────────────────────────────────────────┘

   A packet must pass BOTH layers to reach the instance, and BOTH
   layers again (in reverse) for a reply to leave — but only the NACL
   layer requires you to have written an explicit reply-permitting rule.
```

- **Traffic entering a subnet is evaluated by the NACL first**, then by the security group of the specific resource it's destined for — both must permit the traffic for it to arrive.
- **A security group's implicit-deny is effectively invisible in the console/CLI** (there's no explicit "deny" rule to see) — it manifests simply as "no rule matched, so it's blocked," while a NACL's explicit or implicit final DENY rule is directly visible in the rule list.
- **Because NACLs are stateless, they see and must separately permit both the request and the ephemeral-port reply** — this is the ordered-rule-list structure that most directly reflects [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)'s stateless filtering model in a real cloud tool.

## 5. Hands-On

### 5.1 Creating a Stateful Security Group Rule (AWS CLI Example)

**Purpose:** Demonstrate the stateful, allow-only, resource-attached model in a concrete cloud CLI, showing that only the inbound direction needs to be specified.

**Syntax:**

```bash
aws ec2 authorize-security-group-ingress \
  --group-id <sg-id> --protocol tcp --port <port> --cidr <cidr>
```

**Example usage and expected output:**

```bash
$ aws ec2 authorize-security-group-ingress \
    --group-id sg-0a1b2c3d4e5f6g7h8 \
    --protocol tcp --port 443 --cidr 0.0.0.0/0

{
    "Return": true,
    "SecurityGroupRules": [
        {
            "SecurityGroupRuleId": "sgr-0123456789abcdef0",
            "GroupId": "sg-0a1b2c3d4e5f6g7h8",
            "IsEgress": false,
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "CidrIpv4": "0.0.0.0/0"
        }
    ]
}
```

**Production usage example:** This single inbound rule is sufficient for a public-facing web server's security group — no matching outbound/reply rule is needed because the security group is stateful; the default outbound-allow-all rule (or a scoped equivalent) handles the response automatically.

**Common errors:** Adding a second "outbound 443" rule out of habit from NACL experience — it's harmless but unnecessary noise in a stateful security group, and its presence often signals the author doesn't fully trust (or understand) the stateful model.

### 5.2 Creating a Stateless Network ACL Rule Pair (AWS CLI Example)

**Purpose:** Demonstrate that a NACL requires an explicit, separately numbered rule for the ephemeral-port reply traffic — the direct practical consequence of statelessness.

**Syntax:**

```bash
aws ec2 create-network-acl-entry \
  --network-acl-id <acl-id> --rule-number <n> --protocol <proto> \
  --port-range From=<start>,To=<end> --cidr-block <cidr> \
  --rule-action allow --egress|--ingress
```

**Example usage and expected output:**

```bash
# Inbound: allow HTTPS requests
$ aws ec2 create-network-acl-entry --network-acl-id acl-0123456789abcdef0 \
    --rule-number 100 --protocol tcp --port-range From=443,To=443 \
    --cidr-block 0.0.0.0/0 --rule-action allow --ingress

# Outbound: allow the corresponding ephemeral-port replies
$ aws ec2 create-network-acl-entry --network-acl-id acl-0123456789abcdef0 \
    --rule-number 100 --protocol tcp --port-range From=1024,To=65535 \
    --cidr-block 0.0.0.0/0 --rule-action allow --egress
```

**Production usage example:** This exact rule pair (a specific inbound port, and an outbound ephemeral-range rule) is the standard NACL pattern for any subnet hosting public-facing services — forgetting the second, outbound rule results in connections that appear to reach the instance (security group permits it, application even logs the request) but whose responses silently never leave the subnet.

**Common errors:** Using an overly narrow ephemeral port range for the reply rule (client operating systems vary in their ephemeral port range defaults) — a too-narrow range causes intermittent, hard-to-reproduce connectivity failures that only affect a subset of client connections.

### 5.3 Diagnosing Which Layer Is Blocking Traffic

**Purpose:** Provide a systematic method for determining whether a security group or a NACL (or both) is responsible for unexpected blocked traffic — the most common real troubleshooting task involving both tools.

**Syntax:**

```bash
aws ec2 describe-security-groups --group-ids <sg-id>
aws ec2 describe-network-acls --network-acl-ids <acl-id>
```

**Example usage and expected output:**

```bash
$ aws ec2 describe-security-groups --group-ids sg-0a1b2c3d4e5f6g7h8 \
    --query 'SecurityGroups[0].IpPermissions'
[
    {
        "FromPort": 443, "ToPort": 443, "IpProtocol": "tcp",
        "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
    }
]
# Security group permits it — check the NACL next

$ aws ec2 describe-network-acls --network-acl-ids acl-0123456789abcdef0 \
    --query 'NetworkAcls[0].Entries'
[
    {"RuleNumber": 90,  "Protocol": "-1", "RuleAction": "deny",  "CidrBlock": "203.0.113.0/24", "Egress": false},
    {"RuleNumber": 100, "Protocol": "6",  "RuleAction": "allow", "PortRange": {"From":443,"To":443}, "CidrBlock": "0.0.0.0/0", "Egress": false}
]
# Rule 90 (a lower rule number) denies the specific source range BEFORE
# rule 100 would have allowed it — this is the actual block.
```

**Production usage example:** This layered check (security group first, since it's simpler and order-independent, then the NACL, checking rule-number order specifically) is the standard first move whenever a cloud connectivity ticket says "should be allowed but isn't" — it isolates which of the two independently-evaluated layers is responsible before any rule changes are made.

**Common errors:** Only checking the security group and concluding "it should work" without checking the NACL (or checking the NACL's rules but ignoring their numeric order) — a NACL's behavior is entirely order-dependent, and reading the rules without sorting by rule number is a very easy way to miss the actual blocking rule.

## 6. Production Usage Notes

- **Security groups are the primary, day-to-day tool for most application-level access control** in cloud environments — most engineers spend the overwhelming majority of their firewall-configuration time here, not on NACLs.
- **NACLs are typically configured once per subnet as a coarse, defense-in-depth backstop** (e.g., explicitly denying known-bad IP ranges, or enforcing a subnet-wide policy independent of any individual instance's security group) rather than adjusted per-application — frequent NACL changes are a signal the tool may be misapplied for a task security groups would handle more naturally.
- **Rule limits are a real constraint** — both security groups and NACLs have provider-enforced limits on the number of rules (and, for security groups, the number that can be attached per resource), which matters at scale and is a legitimate input into segmentation design, not just an inconvenience.

## 7. Security Considerations

- **An overly permissive security group (`0.0.0.0/0` on a sensitive port) is one of the most common real-world cloud misconfigurations** found in security audits and breach post-mortems — automated scanning tools specifically hunt for exactly this pattern across the public internet.
- **NACLs provide a genuine independent security boundary** precisely because they're evaluated separately from security groups — a security-group misconfiguration on one instance doesn't automatically expose the whole subnet if the NACL is correctly scoped, which is real defense-in-depth value, not redundancy.
- **The lack of an explicit "deny" concept in security groups means audits must reason about what's absent, not just what's present** — reviewing a security group means confirming no rule matches unwanted traffic, which is a fundamentally different (and easier to get wrong) review process than scanning a NACL's explicit deny rules.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                   | Resolution Path                                                                                                    |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Connection reaches the instance (logged by the application) but the client never sees a response | NACL is missing the outbound ephemeral-port-range rule for the reply traffic                      | Add an explicit outbound NACL rule covering the client's ephemeral port range (typically 1024-65535)                     |
| Traffic works from most clients but intermittently fails for others      | NACL's ephemeral port range for reply traffic is narrower than some clients' actual ephemeral range | Widen the NACL's ephemeral-port-range rule to cover the full standard range                                              |
| A security-group rule was added but traffic is still blocked             | A NACL rule with a lower rule number is denying the traffic before a later NACL rule would allow it, or the security group's rule direction (inbound/outbound) doesn't match the actual traffic flow | Check NACL rules in ascending rule-number order for an earlier DENY; confirm the security-group rule direction matches the flow |

## 9. Best Practices

- Use security groups as the primary, fine-grained access-control tool per resource, and reserve NACLs for coarse, subnet-wide backstops (explicit deny of known-bad ranges, a defense-in-depth default-deny posture) rather than per-application rules.
- Always add both directions when writing a NACL rule pair (a specific port inbound, the ephemeral range outbound, or vice versa for outbound-initiated flows) — never write a NACL rule assuming stateful reply handling.
- When troubleshooting blocked cloud traffic, check both layers systematically (security group, then NACL in rule-number order) rather than assuming either layer alone explains the behavior.

## 10. Common Anti-Patterns / Mistakes

- **Treating NACLs like security groups and forgetting the reply-direction rule.** This produces the specific and confusing "request arrives, response never comes back" symptom that's disproportionately time-consuming to diagnose the first few times an engineer encounters it.
- **Using `0.0.0.0/0` in a security group out of expedience during development and never tightening it before production.** This is consistently one of the top findings in cloud security audits and a direct, well-understood attack surface.
- **Adding redundant explicit-allow NACL rules that duplicate what the security group already handles, while leaving the actual coarse subnet-level backstop (deny known-bad ranges, deny unused protocols) unconfigured.** This misses the actual value NACLs provide as an independent layer.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a security group and a network ACL?"_
**Model answer:** A security group is a stateful firewall attached to an individual resource (like an instance) — it only has allow rules, and once it allows a connection, the reply is automatically permitted. A network ACL is a stateless firewall attached to an entire subnet — it can have both allow and deny rules, evaluated in numbered order, and because it's stateless, both the request and reply directions need their own explicit rules.
_What the interviewer is probing for:_ Whether the candidate has the four core contrasts (stateful/stateless, resource/subnet, allow-only/allow-and-deny, unordered/ordered) memorized accurately, not just vaguely aware two tools exist.

**🎯 Intermediate:** _"A teammate adds a security-group rule allowing outbound port 443 and a matching inbound NACL rule for port 443, but the connection still fails intermittently. What's the likely gap?"_
**Model answer:** The NACL is stateless, so permitting the outbound request on port 443 doesn't automatically permit the inbound reply — the reply arrives on an ephemeral port (something in the 1024-65535 range, from the server's perspective as the responder to the outbound request), not port 443. The NACL needs a second, explicit rule permitting inbound traffic on the ephemeral port range corresponding to the reply, separate from the port-443 rule for the original request. Intermittent failure specifically suggests the ephemeral range configured is too narrow rather than completely missing, since some client connections happen to land in the allowed range and others don't.
_What the interviewer is probing for:_ Practical debugging fluency with the exact failure mode statelessness produces, and whether the candidate connects "intermittent" to a range-width issue rather than an all-or-nothing missing rule.

**🎯 Senior:** _"Given that security groups already provide stateful, resource-level filtering, what's the actual architectural justification for also configuring network ACLs, rather than treating them as legacy overhead?"_
**Model answer:** The justification is genuine defense in depth, not redundancy: security groups and NACLs are evaluated independently, by different mechanisms, at different layers (resource vs. subnet). A security-group misconfiguration on a single instance (an overly broad `0.0.0.0/0` rule added by mistake) is still constrained by the subnet's NACL if it's correctly scoped — meaning a single mistake at one layer doesn't fully expose the resource. NACLs are also useful for coarse, blast-radius-independent controls that don't belong on any single resource's security group — for example, explicitly denying a known-malicious IP range at the subnet level protects every resource in that subnet uniformly, without having to update every individual security group. The two tools aren't interchangeable in capability either: NACLs can explicitly deny, which security groups cannot express at all (only "no matching allow rule"), which matters for certain compliance and audit requirements that want an explicit, visible deny statement rather than an absence of a rule.
_What the interviewer is probing for:_ Whether the candidate can articulate defense-in-depth value concretely (independent evaluation, blast-radius-independent controls, explicit-deny capability) rather than reciting "more layers is more secure" without specifics.

**🎯 Architect:** _"You're designing network security for a multi-account cloud landing zone with dozens of teams provisioning their own resources. How do you use security groups and NACLs differently at the platform level versus the team level?"_
**Model answer:** At the platform level, I'd standardize NACLs as a centrally managed, subnet-level backstop applied consistently across every account/VPC — coarse rules like denying traffic to/from known-bad ranges, enforcing that certain subnets (database tiers, management/bastion subnets) never accept unsolicited inbound traffic from application subnets directly, and any organization-wide compliance-driven explicit denies. This layer is deliberately kept out of individual teams' hands, since its value is consistency and its risk is that a team's well-intentioned NACL edit could silently reintroduce blast-radius exposure across an entire subnet. At the team level, I'd delegate security-group configuration fully to each team for their own resources, since fine-grained, application-specific access control genuinely needs to be owned by the team that understands the application's actual traffic patterns — trying to centralize security-group management for dozens of teams creates an operational bottleneck without a meaningful security benefit, since security groups are already resource-scoped and don't have the same subnet-wide blast-radius risk NACL misconfiguration carries. I'd pair this delegation with automated guardrails (policy-as-code checks that flag or block `0.0.0.0/0` on sensitive ports) rather than manual review, since manual review doesn't scale to dozens of teams self-provisioning.
_What the interviewer is probing for:_ Whether the candidate can design an ownership model that matches each tool's actual blast radius and who has the right context to configure it safely, rather than proposing a single centralized or single fully-delegated model for both.

## 12. Common Misconceptions

1. **"Security groups and network ACLs are basically the same thing, just at different levels."** They differ in state model, rule direction, and rule action capability (allow-only vs. allow-and-deny) — the differences are behavioral, not just scope-of-attachment.
2. **"NACL rules, like security-group rules, don't need to worry about order."** NACL evaluation is explicitly order-sensitive (ascending rule number, first match wins) — this is one of the most consequential differences and a common source of "I added a rule but it's still being blocked" confusion.
3. **"If a security group allows a connection, that's sufficient — I don't need to think about the NACL."** Both layers must independently permit the traffic; a correctly configured security group with a misconfigured or overly restrictive NACL still results in blocked traffic.
4. **"You can express an explicit deny in a security group the same way you can in a NACL."** Security groups have no deny rule concept at all — only "matched by an allow rule" or "not matched, implicitly blocked" — which matters for certain audit and compliance requirements that expect a visible deny statement.

## 13. 🔑 Key Takeaways

- Security groups are stateful, allow-only, and attached to individual resources; NACLs are stateless, support both allow and deny, and are attached to entire subnets with order-sensitive evaluation.
- NACL statelessness means both directions of a flow need explicit rules, typically an application port in one direction and an ephemeral-port range in the other — forgetting this is the most common real-world NACL mistake.
- Both layers must independently permit traffic for it to succeed — troubleshooting blocked cloud traffic means checking both, in NACL rule-number order specifically.
- The two tools provide genuine defense in depth (independent evaluation mechanisms) rather than redundant coverage, and are typically owned at different organizational levels (NACLs centrally, security groups per-team/per-application).
- Overly permissive security-group rules (`0.0.0.0/0` on sensitive ports) remain one of the most common and most actively exploited real-world cloud misconfigurations.

## 14. Related Concepts & What's Next

[§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) is this section's direct conceptual foundation — everything here is the cloud-native application of the stateless-vs-stateful distinction. [§83](Section-83-Part10-Firewall-Placement-Perimeter-Host-Based-and-Segmentation-Patterns.md) supplies the placement reasoning (host-based versus segmentation) that explains why security groups and NACLs exist as two separate tools rather than one. [§85](Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md) goes deeper into the Linux-native equivalent tooling (`iptables`/`nftables`/`firewalld`) that a self-managed instance's own OS-level firewall would use, layered beneath the security group. [§90](Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md) returns to network ACLs specifically in the context of finer-grained micro-segmentation patterns.

**Next Section:** [§85](Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md) — `Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md`

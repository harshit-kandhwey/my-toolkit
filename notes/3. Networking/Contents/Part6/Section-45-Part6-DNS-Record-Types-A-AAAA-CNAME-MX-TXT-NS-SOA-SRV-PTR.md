# Section 45 (Part 6): DNS Record Types: A, AAAA, CNAME, MX, TXT, NS, SOA, SRV, PTR

## 1. Definition

**Plain language:** A DNS zone isn't just one giant name-to-IP lookup table — it stores several different *kinds* of records, each answering a different question about a name: "what IPv4 address does this have," "where should email for this domain go," "what other name is this an alias for," and so on. Knowing the record types is knowing the actual vocabulary of DNS.

**Precise definition:** A **resource record (RR)** is the atomic unit of data stored in a DNS zone, consisting of a **name**, a **record type**, a **TTL** ([§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)), a **class** (almost always `IN`, for Internet), and **type-specific data (RDATA)**. The **record type** determines what the RDATA means and how resolvers are expected to use it — an `A` record's RDATA is an IPv4 address to connect to directly, while an `MX` record's RDATA is a mail-server hostname (plus a priority) used only by mail transfer agents. A zone is, structurally, nothing more than a collection of these typed records under a shared name hierarchy.

> 💡 **Tip:** When you see an unfamiliar record type in a zone file, ask two questions: *who consumes this record* (a web browser? a mail server? a certificate authority?) and *what does its RDATA actually point to* (an IP, another name, arbitrary text)? Nearly every record type's behavior falls out of answering those two questions correctly.

## 2. Why This Matters

- **Choosing the wrong record type for a given use case is one of the most common DNS misconfigurations** — pointing an apex domain at a `CNAME` (which is structurally disallowed at the zone apex in most implementations) or using an `A` record where a `CNAME` was intended are everyday production mistakes.
- **Modern infrastructure automation (Terraform, cloud consoles, CI/CD pipelines) all express DNS changes in terms of these record types directly** — a Terraform `aws_route53_record` resource, for instance, requires specifying the record type explicitly, so fluency here is required to read or write that configuration correctly.
- **Email deliverability depends entirely on correctly configured `MX`, `TXT` (SPF/DKIM/DMARC), and sometimes `PTR` records** — a single misconfigured record type in this set can silently route legitimate mail into spam folders or cause outbound mail to be rejected entirely.
- **Service discovery and load balancing ([§52](Section-52-Part6-DNS-Based-Load-Balancing-and-Failover-Patterns.md)) are built directly on record-type semantics** — round-robin `A` records, weighted routing, and `SRV`-based service discovery are different techniques that only make sense once the underlying record types are understood.
- **Troubleshooting tools (`dig`, `nslookup`, [§53](Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)) report answers per record type**, so reading their output correctly requires knowing what each type means and what a normal vs. broken answer looks like for it.

## 3. Prerequisites and Dependencies

This section assumes the namespace and hierarchy concepts from [§44](Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md), since every record type discussed here is scoped to a specific name within that hierarchy, and the `NS` record specifically implements the delegation mechanism [§44](Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md) described only conceptually. It also assumes basic IPv4 ([§15](../Part3/Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md)) and IPv6 ([§21](../Part3/Section-21-Part3-IPv6-Addressing-Structure-Notation-and-Address-Types.md)) addressing, since `A` and `AAAA` records store exactly those address formats. [§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md) (DNS Caching, TTLs, and Negative Caching) extends this section directly, since every record type carries a TTL field that governs how long resolvers may cache it — a field this section touches only briefly. [§48](Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) (Zone Files and Zone Transfers) shows these record types in their actual on-disk zone-file syntax.

## 4. Architecture / Conceptual Diagram

```text
                     A Zone Is a Typed Collection of Records Under One Name Tree

  example.com.        SOA   ns1.example.com. admin.example.com. (serial ...)  ◄── zone metadata
  example.com.        NS    ns1.example.com.
  example.com.        NS    ns2.example.com.                                  ◄── delegation
  example.com.        MX    10 mail.example.com.                              ◄── mail routing
  example.com.        TXT   "v=spf1 include:_spf.example.com ~all"            ◄── arbitrary text
  example.com.        A     93.184.216.34                                     ◄── IPv4 address
  example.com.        AAAA  2606:2800:220:1:248:1893:25c8:1946                ◄── IPv6 address
  www.example.com.    CNAME example.com.                                      ◄── alias
  api.example.com.    A     93.184.216.35
  _sip._tcp.example.com. SRV 10 60 5060 sipserver.example.com.                ◄── service location
  34.216.184.93.in-addr.arpa. PTR example.com.                                ◄── reverse lookup

  Every line above is a separate RESOURCE RECORD: same underlying storage
  format (name, type, TTL, class, RDATA), different type-specific meaning.
```

- **`SOA` and `NS` are zone-level infrastructure records**, not "content" in the way `A` or `MX` are — they describe how the zone itself is administered and delegated, and every zone must have exactly one `SOA` record at its apex.
- **`CNAME` is structurally special: it redirects the *entire* query to another name**, and a name with a `CNAME` cannot simultaneously hold most other record types (with narrow exceptions like `DNSSEC` records) — this is a frequent source of "why can't I add this record" confusion.
- **`PTR` records live in a completely separate, IP-address-keyed namespace (`in-addr.arpa` for IPv4, `ip6.arpa` for IPv6)** rather than the forward domain-name tree — reverse DNS is architecturally its own delegated hierarchy, just inverted around IP address octets instead of name labels.

## 5. Hands-On

### 5.1 Querying Specific Record Types Directly

**Purpose:** Retrieve exactly one record type for a name, rather than the default `A` lookup — essential when troubleshooting a specific class of problem (mail routing, delegation, IPv6 reachability).

**Syntax:**

```bash
dig <TYPE> <domain> +short
```

**Example usage and expected output:**

```bash
$ dig MX example.com +short
10 mail.example.com.

$ dig TXT example.com +short
"v=spf1 include:_spf.example.com ~all"

$ dig AAAA example.com +short
2606:2800:220:1:248:1893:25c8:1946
```

**Production usage example:** When a mail deliverability issue is reported, the very first diagnostic step is `dig MX <domain>` followed by `dig TXT <domain>` to confirm the SPF record is present and correctly formatted — this narrows the problem to DNS configuration versus the mail server's own sending behavior in seconds.

**Common errors:** An empty response for a record type that should exist (e.g., no `MX` output at all) usually means the record was never created, not that the domain has "no mail" — an explicit `NXDOMAIN` or empty answer with a `NOERROR` status (visible via `dig +noall +answer +comments`) distinguishes "no such name" from "name exists, no record of this type."

### 5.2 Resolving a `CNAME` Chain

**Purpose:** Follow an alias record to its ultimate target, and understand why `CNAME` lookups can involve multiple hops.

**Syntax:**

```bash
dig CNAME <domain> +short
dig <domain>          # follow the full chain, including the final A/AAAA answer
```

**Example usage and expected output:**

```bash
$ dig www.example.com
;; ANSWER SECTION:
www.example.com.       3600    IN      CNAME   example.com.
example.com.           86400   IN      A       93.184.216.34
```

**Production usage example:** Cloud load balancer front-ends are almost always referenced via `CNAME` (e.g., `myapp.example.com CNAME myapp-1234.us-east-1.elb.amazonaws.com.`) precisely because the load balancer's underlying IP addresses are not stable — the `CNAME` layer of indirection is what lets the cloud provider change those IPs freely without breaking the customer-facing name.

**Common errors:** A `CNAME` chain that's too long or that loops back on itself (`a CNAME b`, `b CNAME a`) causes resolution failures in strict resolvers — keep alias chains short and acyclic, and never place a `CNAME` at a zone's apex alongside required `SOA`/`NS` records.

### 5.3 Reverse DNS Lookups with `PTR`

**Purpose:** Resolve an IP address back to a hostname — used for mail server reputation checks, logging, and some authentication schemes.

**Syntax:**

```bash
dig -x <ip-address> +short
```

**Example usage and expected output:**

```bash
$ dig -x 93.184.216.34 +short
example.com.
```

**Production usage example:** Many receiving mail servers perform a reverse-DNS check on the connecting IP and reject or flag mail if no `PTR` record exists, or if it doesn't roughly match the sending domain — cloud providers typically require a support ticket or console setting to configure `PTR` records for outbound mail servers precisely because of this widespread check.

**Common errors:** Expecting a `PTR` record to exist automatically just because an `A` record does is a common mistake — forward and reverse DNS are separate, independently maintained record sets, and having one does not imply the other.

## 6. Production Usage Notes

- **`ALIAS`/`ANAME`-style records (a cloud-provider-specific, non-standard extension available in Route 53 as an "Alias" record, and similarly in other providers) exist specifically to work around `CNAME`'s apex restriction** — they let a zone apex point at a cloud load balancer or CDN endpoint the way a `CNAME` would elsewhere, while still legally coexisting with the zone's required `SOA`/`NS`/`MX` records.
- **`TXT` records have become a general-purpose extension mechanism for DNS-based verification** far beyond their original free-text purpose — domain ownership verification (for TLS certificates, SaaS platforms), SPF/DKIM/DMARC email authentication, and ACME DNS-01 challenges ([§66](../Part8/Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)) all repurpose `TXT` rather than inventing new record types, since `TXT` support is universal across every DNS provider.
- **`SRV` records encode both a priority and a weight**, following the same load-distribution logic as `MX`'s priority field, and are the standard mechanism for service discovery in protocols like SIP and XMPP, and inside some service-mesh and directory-service (e.g., Active Directory) deployments.

## 7. Security Considerations

- **`TXT`-based verification records are a common social-engineering and typosquatting target** — an attacker who can add a `TXT` record to a domain they don't legitimately own (via a compromised DNS provider account) can pass domain-ownership checks for services they shouldn't control.
- **A dangling `CNAME` — one pointing at a resource that no longer exists (a deleted cloud storage bucket or decommissioned service)** — is a well-known subdomain-takeover vector: an attacker who claims the now-unclaimed target resource effectively takes over the subdomain that still points at it.
- **`PTR` and forward (`A`)/reverse consistency is sometimes used as a weak trust signal** by mail systems and some access-control logic — but it should never be treated as a strong authentication mechanism on its own, since DNS records (absent DNSSEC, [§49](Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md)) are not cryptographically verified.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                 | Resolution Path                                                                                         |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Cannot add a new record type to a name that already has a `CNAME`     | `CNAME` records cannot coexist with most other record types at the same name | Remove the `CNAME` or move the conflicting record to a different name; use a provider-specific `ALIAS` at the apex if needed |
| Outbound email is marked as spam or rejected                        | Missing or misconfigured `SPF`/`DKIM`/`DMARC` `TXT` records, or missing `PTR`   | `dig TXT <domain>` to verify SPF/DMARC; confirm `PTR` is set for the sending mail server's IP               |
| A decommissioned cloud resource's `CNAME` still resolves and is claimable by an attacker | Dangling `CNAME` left pointing at a deleted/deallocated resource               | Audit and remove `CNAME` records pointing at deprovisioned resources as part of the decommissioning process |

## 9. Best Practices

- Use the most specific record type available for the job (`AAAA` for IPv6, `SRV` for service discovery, `ALIAS`/`ANAME` for apex CDN/load-balancer targets) rather than working around a type's limitations with a less appropriate one.
- Maintain an inventory of every `CNAME` pointing at externally managed or ephemeral resources (cloud load balancers, CDNs, SaaS platforms), and remove them promptly when the target resource is decommissioned to prevent subdomain takeover.
- Validate `TXT`-based email authentication records (SPF, DKIM, DMARC) with dedicated syntax-checking tools, not just visual inspection — subtle syntax errors in SPF strings are a very common, hard-to-spot cause of deliverability problems.

## 10. Common Anti-Patterns / Mistakes

- **Placing a `CNAME` at a zone apex.** Most authoritative DNS implementations reject this outright because the apex must also hold the zone's `SOA` and `NS` records, which cannot coexist with a `CNAME` — use a provider's `ALIAS`/`ANAME` feature instead.
- **Leaving stale `CNAME`, `A`, or `MX` records pointing at decommissioned infrastructure "just in case."** Beyond the subdomain-takeover risk, stale records actively mislead the next engineer troubleshooting the zone into believing infrastructure still exists.
- **Treating `PTR` records as optional for anything sending outbound mail.** Many receiving mail servers hard-reject connections lacking valid reverse DNS, making this a routine, avoidable deliverability failure.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between an `A` record and a `CNAME` record?"_
**Model answer:** An `A` record maps a name directly to an IPv4 address — it's the actual destination. A `CNAME` record maps a name to *another name*, which the resolver then has to look up in turn (potentially finding another `CNAME`, and eventually an `A` or `AAAA` record at the end of the chain). `CNAME` is used for aliasing, so the target's underlying IP can change without needing to update every name that points at it.
_What the interviewer is probing for:_ Basic but correct understanding of record semantics and the indirection `CNAME` provides.

**🎯 Intermediate:** _"Why can't you put a `CNAME` record at the apex of a zone (e.g., directly on `example.com`, not `www.example.com`)?"_
**Model answer:** A zone apex must have an `SOA` record and at least one `NS` record, since those describe the zone's own administration and delegation. A `CNAME` record, by specification, cannot coexist with other record types at the same name — so placing one at the apex would conflict with those mandatory records. This is why cloud providers offer proprietary workarounds like Route 53's "Alias" record type, which behaves like a `CNAME` for resolution purposes but is implemented internally in a way that doesn't violate this restriction.
_What the interviewer is probing for:_ Whether the candidate understands this as a structural DNS constraint, not an arbitrary provider limitation, and knows the standard workaround.

**🎯 Senior:** _"What is a dangling `CNAME` and why is it a security concern in cloud environments specifically?"_
**Model answer:** A dangling `CNAME` points at a resource — a cloud storage bucket, a CDN distribution, a load balancer — that has since been deleted or deprovisioned, but the `CNAME` record itself was never removed. In many cloud platforms, resource names (like S3 bucket names or Azure blob endpoints) are globally or regionally unique but reusable once released. An attacker can claim that now-available resource name under their own account, and because the dangling `CNAME` still points at it, traffic intended for the original organization's subdomain now resolves to attacker-controlled infrastructure — a subdomain takeover. This is a growing concern specifically because cloud infrastructure is provisioned and torn down far more frequently than traditional on-prem infrastructure, multiplying the number of `CNAME`s that can go stale.
_What the interviewer is probing for:_ Awareness of a real, modern cloud-specific vulnerability class, not just textbook DNS record definitions.

**🎯 Architect:** _"You're designing DNS conventions for a platform where hundreds of services are provisioned and decommissioned weekly via automation. How do you prevent dangling records and other record-type-related risks at that scale?"_
**Model answer:** I'd make DNS record lifecycle part of the same automated provisioning/deprovisioning pipeline that creates the underlying resource, rather than a manual, separate step — every Terraform module or automation script that provisions a load balancer or storage endpoint should own the corresponding `CNAME`/`ALIAS` record in the same apply, and the teardown path should delete it in the same destroy. I'd add a periodic automated audit that resolves every `CNAME` in managed zones and flags any that point at resources no longer present in the current cloud inventory (a straightforward cross-reference between DNS records and cloud API resource lists), since manual process alone reliably fails at this scale and cadence. I'd also standardize on `TXT`-based ownership verification for any service integration, with an expiry/rotation policy, so verification records don't accumulate indefinitely after a service is decommissioned.
_What the interviewer is probing for:_ Systems-level thinking about DNS record lifecycle as something that must be automated and audited at scale, not manually curated — and specific, implementable mitigation, not just naming the risk.

## 12. Common Misconceptions

1. **"A domain has one canonical record type."** A single name commonly holds multiple simultaneous record types (`A` and `AAAA` and `TXT` and `MX` can all coexist at the same name) — the exception, not the rule, is `CNAME`'s exclusivity restriction.
2. **"`MX` records point directly at an IP address."** `MX` records point at a *hostname*, which itself must then be resolved via `A`/`AAAA` — mail routing is always a two-step resolution.
3. **"Reverse DNS (`PTR`) is automatically kept in sync with forward DNS."** They are entirely separate, independently maintained record sets in different namespaces; having a forward `A` record implies nothing about the existence or accuracy of a matching `PTR` record.
4. **"TXT records are just free-text comments with no functional effect."** Modern DNS relies on `TXT` records for critical, machine-parsed functions — SPF, DKIM, DMARC, and domain-ownership verification all depend on `TXT` records being syntactically exact.

## 13. 🔑 Key Takeaways

- Every DNS zone is a collection of typed resource records (`A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, `SOA`, `SRV`, `PTR`, and others), each with its own RDATA semantics and consumer.
- `CNAME` provides name-to-name aliasing but cannot coexist with most other record types at the same name or sit at a zone apex, which is why cloud providers offer `ALIAS`/`ANAME` workarounds.
- `MX`, `TXT` (SPF/DKIM/DMARC), and `PTR` together govern email deliverability, and a misconfiguration in any one of them can silently break mail delivery.
- `PTR` records live in a separate, IP-address-keyed reverse namespace (`in-addr.arpa`/`ip6.arpa`) and are not automatically maintained in sync with forward records.
- Dangling `CNAME` records pointing at deprovisioned cloud resources are a real, exploitable subdomain-takeover risk, and are best prevented by tying DNS record lifecycle directly to resource provisioning/deprovisioning automation.

## 14. Related Concepts & What's Next

[§44](Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md) introduced the hierarchy these records live within, and the `NS`/`SOA` records covered here are the literal implementation of the delegation and zone-authority concepts described there. [§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md) picks up the TTL field mentioned on every record type here and explains caching behavior in depth. [§48](Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) shows these exact record types in real zone-file syntax and covers how a full set of them is transferred between nameservers. [§66](../Part8/Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md) (Part 8) revisits `TXT`-based domain verification specifically in the context of ACME/Let's Encrypt certificate issuance.

**Next Section:** [§46](Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md) — `Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md`

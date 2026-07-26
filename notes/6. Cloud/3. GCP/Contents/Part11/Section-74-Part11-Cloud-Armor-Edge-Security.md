# Section 74 (Part 11): Cloud Armor & Edge Security Deep Dive

## 1. Definition

**Plain language:** Before traffic from the internet ever reaches your application, it has to pass through your load balancer. Cloud Armor sits at that entry point and acts as a bouncer: it blocks known attack patterns (like SQL injection attempts hidden in a request), stops floods of junk traffic trying to overwhelm your service, and can throttle or challenge suspicious visitors — all before a single request touches your actual application servers.

**Precise:** **Cloud Armor** is Google Cloud's web application firewall (WAF) and distributed denial-of-service (DDoS) protection service, attached to Google Cloud's global external Application Load Balancers and, for network-tier protection, to external passthrough Network Load Balancers (Section 22). It evaluates incoming requests against **preconfigured WAF rules** (based on the OWASP Core Rule Set), **custom rules** (written in Cloud Armor's rule language against request attributes), **rate-based rules**, and **adaptive protection** (machine-learning-based anomaly detection), enforcing allow/deny/rate-limit/redirect actions at Google's network edge.

## 2. Why It Exists / Problem It Solves

Cloud Load Balancing (Section 22) already distributes and routes traffic efficiently, but efficient routing and security filtering are different problems — a load balancer will happily and efficiently route a SQL injection payload or a volumetric flood straight to your backend unless something inspects and filters it first. Two distinct classes of threat drove Cloud Armor's design:

1. **Application-layer (Layer 7) attacks** — SQL injection, cross-site scripting, remote code execution attempts, and other payloads embedded in otherwise-well-formed HTTP requests. These attacks exploit application logic, not network volume, so they cannot be stopped by network-layer filtering alone; they require inspecting request content against known attack signatures.
2. **Volumetric and protocol-layer (Layer 3/4) attacks** — floods of traffic intended to exhaust bandwidth, connection tables, or compute capacity, regardless of whether any individual request is otherwise valid. These require absorbing and filtering traffic at a scale and proximity to the network edge that a single backend service cannot achieve on its own.

Because Cloud Armor operates at Google's global edge — the same points of presence Cloud Load Balancing's anycast IPs terminate at (Section 22) — malicious traffic can be filtered or absorbed before it ever consumes backend compute capacity or occupies backend network capacity, rather than being filtered only after arriving at the application.

## 3. Core Concepts

### 3.1 Attachment Point: Cloud Armor and Load Balancing

Cloud Armor is not a standalone service you point traffic at directly — it is configured as a **security policy** attached to a **backend service** or **backend bucket** behind a Google Cloud external Application Load Balancer (the HTTP(S) load balancer covered in Section 22), and separately offers network-tier DDoS protection for external passthrough Network Load Balancers and instances with external IPs. This attachment model means Cloud Armor's effectiveness is directly tied to correctly understanding your load balancing topology from Section 22 — a security policy attached to the wrong backend service, or a workload exposed through a path that bypasses the load balancer entirely (e.g., a VM with a public IP outside the LB), receives no Cloud Armor protection regardless of how well the policy itself is written.

### 3.2 Preconfigured WAF Rules (OWASP Core Rule Set)

**Definition:** preconfigured WAF rules are Google-maintained rule sets, based on the industry-standard **OWASP Core Rule Set (CRS)**, that detect common web application attack signatures — SQL injection (`sqli`), cross-site scripting (`xss`), remote code execution (`rce`), local file inclusion (`lfi`), and similar — without the customer writing any rule logic themselves.

- Each preconfigured rule group (`sqli-v33-stable`, `xss-v33-stable`, etc.) can be enabled independently, and within a group, individual **sensitivity levels** control how aggressively ambiguous patterns are flagged — higher sensitivity catches more attacks but raises false-positive risk against legitimate but unusually-shaped requests.
- Preconfigured rules are the direct Cloud Armor analog to curated detections in Chronicle (Section 73.3.2) — Google-maintained baseline content that should be enabled first, with custom rules reserved for organization-specific logic.

### 3.3 Custom Rules

**Definition:** custom rules are Cloud Armor policy rules written by the customer, using Cloud Armor's rule language (CEL-like expressions) against request attributes — source IP/geography, request headers, path, query parameters — to allow, deny, rate-limit, or redirect matching traffic.

```
# Example custom rule expression: block requests from a specific geography
# targeting an admin path
origin.region_code == "XX" && request.path.matches("/admin/.*")
```

- Common custom rule use cases: geo-blocking regions with no legitimate business need to access a service, allow-listing a known partner IP range to bypass rate limiting, or blocking requests missing an expected internal header (used to detect and block traffic attempting to bypass an intended internal-only path).
- Custom rules are evaluated in **priority order**; the first matching rule's action applies, so rule ordering (e.g., a specific allow-list rule with lower priority number than a broader deny rule) is a frequent source of misconfiguration when not carefully managed.

### 3.4 Rate-Based Rules and Bot Management

**Definition:** rate-based rules throttle or block clients that exceed a configured request-rate threshold within a time window, identified by a configurable key (source IP, or a combination of attributes).

- Distinct from a hard block: a rate-based rule's action is commonly "throttle" (allow up to the threshold, deny beyond it) rather than an outright deny, letting legitimate bursty clients continue at a reduced rate rather than being cut off entirely.
- **reCAPTCHA Enterprise integration** extends rate-based protection into active **bot management** — instead of only rate-limiting by request volume, suspicious traffic can be challenged with a reCAPTCHA assessment, and Cloud Armor rules can act on the resulting bot/human score, distinguishing scripted abuse from legitimate high-volume human traffic.

### 3.5 Adaptive Protection

**Definition:** Adaptive Protection is Cloud Armor's machine-learning-based Layer 7 DDoS detection feature, which builds a baseline of normal traffic patterns per backend service and automatically flags and suggests protective rules when it detects an anomalous, attack-like deviation from that baseline.

- Unlike preconfigured and custom rules, which are static until manually changed, Adaptive Protection is continuously adaptive — it generates an **alert with a suggested Cloud Armor rule** when it detects a likely Layer 7 DDoS pattern, which a security team can review and deploy (or, in more automated postures, apply programmatically, connecting directly to the automated incident response patterns in Section 75).
- Adaptive Protection specifically targets Layer 7 volumetric anomalies — a flood of legitimate-looking application requests overwhelming a specific endpoint — which signature-based preconfigured rules are not designed to catch, since no individual request in the flood necessarily matches a known attack pattern.

### 3.6 DDoS Protection Tiers: Standard vs. Managed Protection Plus

| Aspect                     | Standard (default, included)                                                                       | Managed Protection Plus (paid tier)                                                                                   |
| -------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Network-layer DDoS defense | Always-on protection for GCP's global network, included for every project by default               | Same always-on network protection, included                                                                           |
| Adaptive Protection        | Not included                                                                                       | Included — Layer 7 ML-based anomaly detection and suggested rules (74.3.5)                                            |
| WAF rule access            | Full access to preconfigured and custom rules                                                      | Full access, plus additional named IP threat intelligence rule feeds                                                  |
| Cost model                 | No additional charge for baseline network protection                                               | Subscription/commitment pricing, includes DDoS incident response support and cost protection during declared attacks  |
| Best fit                   | Workloads with lower risk profile or cost-sensitive projects relying on network-layer defense only | Internet-facing production workloads, especially those handling sensitive data or with high availability requirements |

> ⚠️ **Interview-relevant nuance:** "Standard" is not "no protection" — Google's global network-layer DDoS defenses are always-on for every project regardless of tier. Managed Protection Plus specifically adds Adaptive Protection, richer threat intelligence feeds, and financial/incident-response guarantees during a declared DDoS event — the distinction is about _additional_ Layer 7 intelligence and guarantees, not the presence or absence of baseline protection.

## 4. Edge Filtering Architecture Diagram

```
                         Internet Traffic
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │   Google Global Network Edge │
                 │   (always-on L3/L4 DDoS      │
                 │    defense, both tiers)      │
                 └───────────────┬──────────────┘
                                 ▼
                 ┌─────────────────────────────────┐
                 │   Cloud Armor Security Policy   │
                 │                                 │
                 │  Preconfigured WAF (OWASP CRS)  │
                 │  Custom Rules (priority order)  │
                 │  Rate-Based Rules + Bot Mgmt    │
                 │ Adaptive Protection (Plus tier) │
                 └───────────────┬─────────────────┘
                          allow  │  deny/throttle ► 403/429 response
                                 ▼
                 ┌────────────────────────────────┐
                 │  External Application/Network  │
                 │  Load Balancer (Section 22)    │
                 └───────────────┬────────────────┘
                                 ▼
                       Backend Services / GKE / VMs
```

## 5. Comparison: Cloud Armor vs. AWS WAF/Shield vs. Azure WAF/DDoS Protection

| Aspect                      | Cloud Armor (GCP)                                                                                                                 | AWS WAF + Shield                                                                                          | Azure WAF + DDoS Protection                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Attachment point            | Google Cloud Load Balancing backend services (Section 22)                                                                         | CloudFront, Application Load Balancer, API Gateway                                                        | Application Gateway, Azure Front Door                                                        |
| WAF rule baseline           | Preconfigured OWASP CRS-based rule groups                                                                                         | AWS Managed Rules (OWASP-aligned managed rule groups)                                                     | Managed rule sets (also OWASP CRS-based)                                                     |
| DDoS protection tiers       | Standard (always-on network layer) / Managed Protection Plus (adds L7 ML + guarantees)                                            | Shield Standard (always-on, free) / Shield Advanced (paid, adds L7 protection + cost/response guarantees) | Basic (always-on, free) / DDoS Protection Standard (paid, adds adaptive tuning + guarantees) |
| ML-based adaptive detection | Adaptive Protection (Plus tier)                                                                                                   | Shield Advanced's automatic application-layer mitigation                                                  | DDoS Protection Standard's adaptive tuning                                                   |
| Bot management              | reCAPTCHA Enterprise integration                                                                                                  | AWS WAF Bot Control (managed rule group)                                                                  | Azure Front Door / Application Gateway bot protection rule sets                              |
| Structural analog           | Nearly identical three-tier model: baseline free network defense, paid L7 ML tier, WAF rules as a separate but co-located control | Nearly identical: Shield Standard/Advanced split mirrors Cloud Armor's Standard/Plus split closely        | Nearly identical: Basic/Standard DDoS split plus separately configured WAF                   |

> 💡 **Interview-relevant nuance:** All three major clouds converge on the same structural pattern — a free, always-on network-layer DDoS baseline; a paid tier adding Layer 7 ML-based anomaly detection and financial/response guarantees; and a WAF component (rule-based, signature-driven) that is conceptually separate from DDoS protection even though it is commonly configured together. When comparing these services, naming this three-part structure (baseline DDoS / paid adaptive DDoS / WAF) demonstrates a precise understanding rather than treating "WAF" and "DDoS protection" as one undifferentiated feature.

## 6. Hands-On Example: Creating a Cloud Armor Security Policy with a Rate-Based Rule

**Purpose:** Create a Cloud Armor security policy that enables a preconfigured SQL injection rule and adds a rate-based rule throttling any single client IP exceeding 100 requests per minute, then attach it to a backend service.

```bash
gcloud compute security-policies create edge-protect-policy \
  --description="Baseline WAF + rate limiting for public API backend"

gcloud compute security-policies rules create 1000 \
  --security-policy=edge-protect-policy \
  --expression="evaluatePreconfiguredExpr('sqli-v33-stable')" \
  --action=deny-403

gcloud compute security-policies rules create 2000 \
  --security-policy=edge-protect-policy \
  --src-ip-ranges="*" \
  --action=throttle \
  --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60 \
  --conform-action=allow \
  --exceed-action=deny-429 \
  --enforce-on-key=IP

gcloud compute backend-services update public-api-backend \
  --security-policy=edge-protect-policy --global
```

**Expected output (final command):**

```
Updated [https://www.googleapis.com/compute/v1/projects/prod-1/global/backendServices/public-api-backend].
```

- **Purpose of each rule's priority number:** rules are evaluated in ascending priority order (1000 before 2000); the SQL injection deny rule is placed first so a request matching both the injection signature and the rate limit is denied for the injection attempt specifically, giving clearer signal in logs than a generic rate-limit denial would.
- **Common error:** creating and configuring a security policy but forgetting the final `backend-services update` attachment step — a fully configured, correct policy provides zero protection until it is explicitly attached to the relevant backend service(s).

> 💡 **Tip:** `--enforce-on-key=IP` is the simplest rate-limiting key, but production APIs behind a shared NAT gateway or corporate proxy often need a more granular key (e.g., a combination including a request header carrying an authenticated client/API-key identifier) to avoid throttling many legitimate distinct users who happen to share one egress IP.

## 7. Production & Enterprise Usage

- **Preview mode before enforcement.** New rules, especially custom rules and newly enabled preconfigured rule groups, are commonly deployed with `--preview` first — logging what _would_ have been blocked without actually blocking it — to validate against real production traffic before switching to active enforcement, avoiding an outage caused by an overly aggressive new rule.
- **Layered with Cloud CDN and regional backend architecture.** Cloud Armor is typically one layer in a broader edge stack including Cloud CDN for caching (reducing the volume of traffic that reaches origin at all) and Cloud Load Balancing's multi-region backend distribution (Section 22) for resilience.
- **Adaptive Protection alerts routed into SOC workflows.** Organizations running Managed Protection Plus commonly route Adaptive Protection's suggested-rule alerts into the same SOC triage and automated response pipeline (Sections 75–76) used for other security detections, rather than treating them as a separate, siloed notification channel.

## 8. Common Misconceptions

- **Misconception:** "Cloud Armor protects any GCP resource with a public IP automatically." Cloud Armor security policies apply only to traffic passing through a load balancer backend service/bucket they are explicitly attached to (74.3.1); a VM with a directly assigned public IP bypassing the load balancer receives no Cloud Armor protection regardless of policy configuration.
- **Misconception:** "The Standard DDoS tier means you are unprotected without paying for Managed Protection Plus." Google's network-layer DDoS defenses are always-on for every project by default; Managed Protection Plus specifically adds Layer 7 Adaptive Protection and cost/incident-response guarantees, not baseline protection itself (74.3.6).
- **Misconception:** "Enabling every preconfigured WAF rule group at maximum sensitivity is always the safest choice." Higher sensitivity increases false-positive risk against legitimate traffic with unusual-but-valid request shapes; production deployments tune sensitivity per rule group and validate in preview mode rather than maximizing every setting by default.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between a preconfigured WAF rule and a custom rule in Cloud Armor?_
**Model answer:** Preconfigured rules are Google-maintained, based on the OWASP Core Rule Set, detecting common attack signatures like SQL injection and cross-site scripting without requiring the customer to write any rule logic. Custom rules are written by the customer using Cloud Armor's rule expression language against request attributes like source IP, geography, or headers, to encode organization-specific logic that generic signature-based rules cannot anticipate, such as geo-blocking or allow-listing a known partner range.

**🎯 Intermediate:** _How does Adaptive Protection differ from a rate-based rule, and why are both useful?_
**Model answer:** A rate-based rule enforces a static, manually configured threshold (e.g., 100 requests per minute per IP) — simple and predictable, but it cannot distinguish a coordinated distributed Layer 7 flood spread across many distinct source IPs, each individually staying under the threshold, from genuinely independent legitimate traffic. Adaptive Protection uses machine learning to baseline normal traffic patterns per backend service and detect anomalous deviations from that baseline regardless of whether any single source IP crosses a fixed threshold, then suggests a targeted rule. They are complementary: rate-based rules handle simple, predictable abuse cheaply and immediately, while Adaptive Protection catches more sophisticated distributed patterns a static threshold would miss.

**🎯 Senior/Architect:** _A production API behind Cloud Armor is intermittently blocking legitimate customer traffic, and the team suspects an overly aggressive WAF rule. How would you diagnose and fix this without reopening the service to the attack the rule was meant to stop?_
**Model answer:** I would first confirm which specific rule is responsible by checking Cloud Armor's logging output (routed through Cloud Logging) for the denied requests, which identifies the matching rule and preconfigured signature group per blocked request rather than guessing. If it's a preconfigured rule group, I'd check whether the false positives cluster around a specific sensitivity level or a specific sub-signature within that group, and consider lowering sensitivity for that group specifically rather than disabling the whole group, preserving protection against the broader attack class. Critically, I would not simply disable the rule in production — I'd first re-deploy the adjusted rule configuration in preview mode against live traffic to confirm the false positives are resolved and that genuine attack traffic (if reproducible from logs of past real attempts) would still be caught, before promoting the change to active enforcement. If the false positives stem from a legitimate but unusually shaped request pattern specific to this API (e.g., a customer's client library sending an atypical but valid payload structure), I'd consider a narrowly scoped custom allow-list rule with higher priority than the preconfigured deny, rather than weakening the preconfigured rule's sensitivity globally across all backends sharing that policy.

## 10. Key Takeaways

- 🔑 Cloud Armor is attached to Cloud Load Balancing backend services/buckets (Section 22), not to individual VMs directly — protection only applies to traffic that actually passes through a protected load balancer.
- 🔑 Preconfigured WAF rules (OWASP CRS-based) provide Google-maintained baseline signature detection; custom rules encode organization-specific logic, mirroring the curated-first/custom-second pattern seen in Chronicle detections (Section 73).
- 🔑 Rate-based rules provide static, predictable throttling; Adaptive Protection (Managed Protection Plus tier) adds ML-based anomaly detection for Layer 7 patterns a fixed threshold cannot catch.
- 🔑 Standard DDoS protection (always-on, free) and Managed Protection Plus (paid, adds Adaptive Protection and guarantees) are not "unprotected vs. protected" — both include baseline network-layer defense.
- 🔑 All three major clouds converge on the same structural pattern: free baseline network DDoS defense, a paid tier adding L7 ML detection and guarantees, and a separately configured WAF layer.
- 🔑 Preview mode is the standard production pattern for validating new or adjusted rules against real traffic before enforcing them, avoiding self-inflicted outages from overly aggressive rules.

## 11. Related Concepts

Cloud Load Balancing (Section 22, the attachment point for all Cloud Armor policies), Security Command Center (Section 39, which can surface Cloud Armor-relevant findings), Chronicle's curated detections (Section 73, the closest conceptual analog to preconfigured WAF rules), and automated incident response acting on Adaptive Protection alerts (Section 75) all connect directly to the edge security model covered here.

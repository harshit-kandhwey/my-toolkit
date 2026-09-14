# Section 80 (Part 9): Cloud Load Balancer Types (ALB/NLB, Azure LB/App Gateway, GCP LB — Conceptual)

## 1. Definition

**Plain language:** Every major cloud provider offers a managed load-balancing service so teams don't have to run and patch their own software load balancer. Each provider splits its offering the same way conceptually — a fast, protocol-agnostic option for raw TCP/UDP traffic, and a smarter, HTTP-aware option for web/API traffic — even though the exact product names differ between AWS, Azure, and GCP.

**Precise definition:** All three major cloud providers implement managed load balancing along the same **Layer 4 / Layer 7 split** established in [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md), as fully managed services requiring no customer-operated load-balancer instances. **AWS** offers the **Network Load Balancer (NLB)** for Layer 4 (TCP/UDP, extreme throughput, static IP support) and the **Application Load Balancer (ALB)** for Layer 7 (HTTP/HTTPS, path/host-based routing, WebSocket support). **Azure** offers **Azure Load Balancer** for Layer 4 (TCP/UDP, public or internal) and **Application Gateway** for Layer 7 (HTTP/HTTPS, path-based routing, integrated WAF option). **GCP** offers a unified **Cloud Load Balancing** product family split by mode: **Network Load Balancer** (passthrough, Layer 4) and **Application Load Balancer** (proxy-based, Layer 7, global or regional). Across all three, the conceptual mapping is consistent: the L4 product is the low-latency, protocol-agnostic option; the L7 product is the content-aware, HTTP-specialized option with richer routing and security integration.

> 💡 **Tip:** This section is deliberately conceptual and cross-cloud, matching this roadmap's stated scope — provider-specific deep dives on exact configuration, pricing tiers, and console workflows for these products live in each cloud's own dedicated knowledge base track, not here. The goal here is to be able to correctly map any of these product names to the L4/L7 concepts already covered in [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) without hesitation.

## 2. Why This Matters

- **Cloud certifications and job postings assume fluency with these exact product names.** Being asked to choose "ALB or NLB" or "Azure Load Balancer or Application Gateway" in an interview or a real architecture decision requires mapping the product name directly back to the L4/L7 concept it implements.
- **Choosing the wrong product for a workload is a common, costly real-world mistake.** Attempting to run a raw TCP database connection through an HTTP-only Layer 7 product (or forfeiting needed path-based routing by choosing a Layer 4 product) leads to either outright failure or missing capability that has to be worked around later.
- **Managed load balancers remove an entire category of operational burden** (patching, scaling, high availability of the load balancer itself, [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md)'s "the load balancer needs its own redundancy strategy" concern) that self-managed software load balancers ([§81](Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md)) require the team to handle explicitly.
- **Pricing models differ meaningfully between L4 and L7 products** in ways directly tied to the underlying mechanism ([§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)) — L7 products generally bill on a processed-request/capacity-unit basis reflecting their higher per-request processing cost, while L4 products bill closer to pure data-volume terms.
- **Multi-cloud or cloud-agnostic architecture discussions require translating between provider vocabularies fluently** — recognizing that "NLB," "Azure Load Balancer," and "GCP Network Load Balancer" are conceptually the same category, just under different provider branding.

## 3. Prerequisites and Dependencies

This section is a direct, concrete application of [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)'s Layer 4/Layer 7 distinction and assumes it fully. It also draws on [§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md) (health check configuration, which every cloud load balancer product exposes as named settings) and [§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) (TLS termination, a standard feature of every L7 cloud product). Cross-reference: this section covers these products at the conceptual level only — full provider-specific configuration depth (exact console steps, IAM permissions, pricing details, provider-specific advanced features) belongs to this repo's dedicated AWS, Azure, and GCP knowledge base tracks, consistent with how the roadmap's assumption line scopes this Networking topic.

## 4. Architecture / Conceptual Diagram

```text
                    LAYER 4 (protocol-agnostic,          LAYER 7 (HTTP-aware,
                     high-throughput, passthrough)         content-based routing)

   AWS              Network Load Balancer (NLB)          Application Load Balancer (ALB)
                     - Static IP per AZ                   - Path/host-based routing
                     - Preserves source IP by default      - WebSocket, HTTP/2 support
                     - TCP/UDP/TLS passthrough or           - Native WAF integration
                       termination                          - Target: instances, IPs,
                     - Extreme connection throughput          Lambda functions

   Azure            Azure Load Balancer                   Application Gateway
                     - Public or internal (ILB)            - Path-based routing
                     - TCP/UDP, zone-redundant              - Integrated WAF (WAF_v2 SKU)
                     - Basic/Standard SKU tiers             - URL rewrite, header rewrite
                                                             - Autoscaling (v2 SKU)

   GCP              Network Load Balancer                 Application Load Balancer
                     (passthrough, regional)                - Global or regional
                     - Preserves client IP                   - Host/path-based routing
                     - TCP/UDP                                - Google Front End (GFE)
                                                                 integration, Cloud Armor
                                                                 (WAF-equivalent)

   ─────────────────────────────────────────────────────────────────────────────────
   Common thread across all three providers: L4 product = fast, protocol-agnostic,
   passthrough-oriented; L7 product = HTTP-native, richer routing, WAF-integrated,
   costs more per request processed.
```

- All three providers' **L4 products** default toward preserving the original client source IP more directly than their L7 counterparts, consistent with [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)'s general observation that L4 forwarding is naturally closer to NAT than to a full terminating proxy.
- All three providers' **L7 products** integrate natively with that provider's WAF offering (AWS WAF with ALB, Azure WAF with Application Gateway, Cloud Armor with GCP's Application Load Balancer) — reflecting the general principle from [§78](Section-78-Part9-Reverse-Proxies-vs-Load-Balancers-vs-API-Gateways.md) that L7 visibility is what enables content-aware security inspection at all.
- GCP's **global** Application Load Balancer variant is a notable cross-cutting feature — it operates as a single anycast-fronted ([§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md)) endpoint routing to backends across multiple regions, blending L7 load balancing with GSLB-like global routing in a single product, whereas AWS and Azure's equivalents are more strictly regional, requiring a separate GSLB layer (DNS-based, or provider-specific global routing products) to achieve similar cross-region behavior.

## 5. Hands-On

### 5.1 Creating an AWS Network Load Balancer (Conceptual CLI)

**Purpose:** Show the conceptual shape of provisioning an L4 cloud load balancer, mapping directly onto the target-group/health-check concepts already covered.

**Syntax:**

```bash
aws elbv2 create-load-balancer \
  --name my-nlb \
  --type network \
  --subnets subnet-0abc123 subnet-0def456

aws elbv2 create-target-group \
  --name my-tcp-targets \
  --protocol TCP \
  --port 443 \
  --vpc-id vpc-0abcdef \
  --health-check-protocol TCP
```

**Example usage and expected output:**

```bash
$ aws elbv2 create-load-balancer --name my-nlb --type network --subnets subnet-0abc123 subnet-0def456
{
    "LoadBalancers": [{
        "LoadBalancerArn": "arn:aws:elasticloadbalancing:...:loadbalancer/net/my-nlb/...",
        "DNSName": "my-nlb-1234567890.elb.us-east-1.amazonaws.com",
        "Type": "network",
        "State": {"Code": "provisioning"}
    }]
}
```

- `--type network` is the explicit switch selecting NLB (Layer 4) over ALB — this single flag is the point where the L4/L7 decision from [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) becomes a concrete API parameter.
- The `--health-check-protocol TCP` on the target group directly maps onto the TCP-level health check concept covered in [§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md)'s §5.1.

**Production usage example:** This exact pattern — NLB with a TCP target group — is standard for exposing a non-HTTP TCP service (a database proxy, a custom protocol service) or for extremely high-connection-rate HTTP workloads where NLB's lower overhead outweighs forgoing ALB's routing features.

**Common errors:** Attempting to attach path-based routing rules to an NLB listener fails outright, since NLB has no concept of HTTP paths at all — this is the exact "using the wrong layer's product for the requirement" mistake flagged as an anti-pattern throughout this Part.

### 5.2 Creating an AWS Application Load Balancer With Path-Based Routing (Conceptual CLI)

**Purpose:** Contrast directly with §5.1 by showing an L7 product's path-based routing capability configured via its listener rules.

**Syntax:**

```bash
aws elbv2 create-load-balancer \
  --name my-alb \
  --type application \
  --subnets subnet-0abc123 subnet-0def456

aws elbv2 create-rule \
  --listener-arn arn:aws:elasticloadbalancing:...:listener/app/my-alb/... \
  --priority 10 \
  --conditions Field=path-pattern,Values='/api/*' \
  --actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...:targetgroup/api-targets/...
```

**Example usage and expected output:**

```bash
$ curl -s https://my-alb-1234567890.us-east-1.elb.amazonaws.com/api/orders
{"orders": []}

$ curl -s https://my-alb-1234567890.us-east-1.elb.amazonaws.com/
<html>...web app...</html>
```

- `--conditions Field=path-pattern,Values='/api/*'` is only possible because ALB (`--type application`) fully parses the HTTP request path — the same conceptual capability demonstrated with NGINX `location` blocks in [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)'s §5.1, expressed here as a managed cloud API instead of a config file.

**Production usage example:** This pattern is the standard way to consolidate multiple backend services behind one public ALB and one public hostname, avoiding separate load balancers (and separate TLS certificates) per service — directly mirroring the software-based pattern from §5.1 in [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md).

**Common errors:** Forgetting to set listener rule priority correctly (lower numbers evaluated first) can cause a broader, less specific rule to match before a more specific one, silently misrouting traffic — analogous to the NGINX `location` block ordering issue described in [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md).

### 5.3 Testing a Cloud Load Balancer's Health Check Configuration From the CLI

**Purpose:** Verify a target group's configured health check settings directly, since a misconfigured health check is one of the most common sources of "healthy targets showing as unhealthy" support tickets.

**Syntax:**

```bash
aws elbv2 describe-target-health --target-group-arn <target-group-arn>
```

**Example usage and expected output:**

```bash
$ aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:...:targetgroup/api-targets/...
{
    "TargetHealthDescriptions": [
        {
            "Target": {"Id": "i-0abc123def456", "Port": 8080},
            "TargetHealth": {
                "State": "unhealthy",
                "Reason": "Target.ResponseCodeMismatch",
                "Description": "Health checks failed with these codes: [500]"
            }
        }
    ]
}
```

- The `Reason` and `Description` fields directly answer why a target is unhealthy — here, the health check endpoint is returning HTTP 500, which is exactly the kind of application-level failure a deep HTTP health check (as opposed to a shallow TCP check, [§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md)) is designed to catch.

**Production usage example:** This is the standard first diagnostic command when a cloud console shows targets as unhealthy — it gives the precise reason without needing to reproduce the health check manually against the target directly.

**Common errors:** Assuming "unhealthy" always means the application crashed — as shown here, it frequently means the health check itself is misconfigured (wrong expected status code, wrong path) against an application that's otherwise working correctly for real traffic.

## 6. Production Usage Notes

- **All three providers' load balancers are inherently highly available by design**, distributed across multiple availability zones automatically — this directly satisfies the "the load balancer itself needs a redundancy strategy" concern raised in [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md), without the customer needing to configure anything explicitly for that property.
- **L7 products' native WAF integration is a significant differentiator from self-managed software load balancers** — enabling AWS WAF on an ALB, Azure WAF on Application Gateway, or Cloud Armor on a GCP Application Load Balancer is a managed-service checkbox, versus a separately operated component in a self-managed NGINX/HAProxy deployment.
- **Cross-region behavior differs by provider and product** — GCP's global Application Load Balancer natively spans regions behind one anycast IP; AWS and Azure require an explicit additional layer (Route 53 with health checks, Azure Traffic Manager/Front Door) to achieve comparable GSLB-style ([§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md)) cross-region routing on top of their inherently regional load balancer products.

## 7. Security Considerations

- Managed cloud load balancers are natural chokepoints for security group/NSG rules restricting which sources can reach them at all ([§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) covers security groups vs. NACLs in depth) — public-facing load balancers should still be scoped to only the ports and protocols genuinely required, not opened broadly by default.
- L7 products' WAF integration should be treated as a meaningful layer of defense, not a substitute for secure application code — a WAF blocks known attack patterns but doesn't replace proper input validation and authentication at the application layer itself.
- Backends behind these managed load balancers should generally live in private subnets with no direct public IP or reachability, relying entirely on the load balancer as the sole ingress path — consistent with the general principle established in [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                                     | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Path-based routing rules configured but not taking effect           | Load balancer provisioned as an L4 product (NLB/Azure Load Balancer/GCP Network LB) instead of L7    | Recreate or migrate the workload to the corresponding L7 product (ALB/Application Gateway/GCP Application LB)       |
| Targets show unhealthy in the console despite the app running fine  | Health check path/expected status code misconfigured against what the app actually returns          | Use the CLI/API health-check description output (§5.3) to see the exact failure reason rather than guessing        |
| High latency added specifically to a raw TCP workload                | An L7 product is being used for a workload that only needs L4 forwarding                             | Reassess whether the workload actually needs L7 features; migrate to the L4 product if not                          |
| Global users experience inconsistent latency despite a "global" setup | Using a regional-only load balancer product (AWS ALB/Azure Application Gateway) without an added GSLB layer | Add a GSLB layer (Route 53 latency/geo routing, Azure Front End/Traffic Manager) or use GCP's natively global product if on GCP |

## 9. Best Practices

- Map the workload's actual requirement (protocol-agnostic vs. HTTP-aware routing, per [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)) to the correct product family before provisioning, rather than defaulting to whichever product a team has used before regardless of fit.
- Enable the provider's native WAF integration on L7 products for any public-facing web/API workload, since it's available as a managed feature with minimal operational overhead compared to self-managing that capability.
- When operating across multiple regions on AWS or Azure specifically, plan explicitly for the additional GSLB layer ([§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md)) needed to achieve cross-region routing, since neither provider's regional load balancer product spans regions natively the way GCP's global option does.

## 10. Common Anti-Patterns / Mistakes

- **Choosing a cloud load balancer product by habit or familiarity rather than by matching it to the L4/L7 requirement ([§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)).** This is the single most common real-world mistake covered in this section, and it surfaces immediately as missing routing capability or unnecessary overhead.
- **Assuming a regional L7 product (ALB, Application Gateway) automatically provides global, multi-region routing.** Only GCP's global Application Load Balancer variant does this natively; AWS and Azure require an explicit additional GSLB layer.
- **Treating WAF integration as a complete security solution on its own.** It's a valuable layer of defense but doesn't replace secure application design, authentication, and input validation.

## 11. Interview Questions

**🎯 Beginner:** _"On AWS, what's the difference between an NLB and an ALB?"_
**Model answer:** NLB is a Layer 4 load balancer — it works with any TCP or UDP traffic, has very high throughput, and generally preserves the client's original source IP; it has no awareness of HTTP content at all. ALB is a Layer 7 load balancer — it's HTTP/HTTPS-specific, and it can route based on the actual request content like URL path or hostname, supports WebSockets, and integrates natively with AWS WAF. The choice comes down to whether the workload needs HTTP-aware routing (ALB) or is a raw TCP/UDP workload or needs maximum throughput (NLB).
_What the interviewer is probing for:_ Whether the candidate correctly maps AWS's product naming onto the L4/L7 conceptual distinction rather than memorizing feature lists without understanding why they differ.

**🎯 Intermediate:** _"Your team is deploying the same conceptual architecture on Azure instead of AWS. What are the equivalent products, and are there meaningful differences beyond naming?"_
**Model answer:** The Layer 4 equivalent is Azure Load Balancer, and the Layer 7 equivalent is Application Gateway. Conceptually they map the same way as NLB and ALB — Azure Load Balancer for protocol-agnostic TCP/UDP traffic, Application Gateway for HTTP-aware routing with path-based rules and integrated WAF (as the WAF_v2 SKU). One meaningful difference worth knowing is that Application Gateway's SKU tiers matter for features like autoscaling, which isn't a decision AWS's ALB requires in the same way since ALB scales transparently as a fully managed service without a comparable SKU choice — so there's a bit more explicit tier/SKU decision-making on the Azure side for equivalent functionality.
_What the interviewer is probing for:_ The ability to translate the same conceptual model across cloud providers fluently, plus awareness that "equivalent" doesn't always mean "operationally identical" in every configuration detail.

**🎯 Senior:** _"A team building a global SaaS product on AWS complains that users in Asia experience much higher latency than users in North America, even though they've deployed an ALB in both regions. What's likely missing, and how would you fix it?"_
**Model answer:** An ALB is a regional resource — deploying one in each region gives each region its own load-balanced entry point, but nothing in that setup actually routes a given user to their *nearest* region automatically. Without an added GSLB layer, users are likely all resolving to a single hardcoded region's ALB DNS name (or being routed by some other non-geography-aware mechanism), meaning Asian users' requests are traveling the full distance to a North American region regardless of a perfectly healthy ALB existing closer to them. The fix is to add a GSLB layer on top — Route 53 with latency-based or geolocation routing policies, directing each user's DNS query to the ALB in their nearest healthy region — which is exactly the pattern covered in [§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md), since AWS's regional load balancer products don't provide this cross-region routing natively the way GCP's global load balancer option does.
_What the interviewer is probing for:_ Recognition that deploying regional load balancers in multiple regions isn't sufficient on its own — an explicit GSLB layer is required on AWS to actually route users geographically, connecting this section back to [§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md).

**🎯 Architect:** _"You're designing a multi-cloud-portable architecture that needs to run equivalently on AWS, Azure, and GCP without a fundamental redesign per provider. How do you approach the load-balancing layer given each provider's differently named products?"_
**Model answer:** I'd design the architecture around the L4/L7 conceptual model itself — decide which traffic genuinely needs Layer 7 features (path/host routing, WAF integration) versus which is pure L4 (protocol-agnostic TCP/UDP) — and treat the actual provider product choice (NLB/ALB, Azure Load Balancer/Application Gateway, GCP Network/Application Load Balancer) as an implementation detail selected per-provider using that same conceptual mapping, rather than trying to force a single provider's specific feature set to be replicated exactly elsewhere. Where genuine functional gaps exist between providers — most notably, GCP's natively global Application Load Balancer versus AWS/Azure's regional-only L7 products requiring an added GSLB layer — I'd explicitly account for that asymmetry in the deployment automation (provisioning a Route 53/Traffic Manager-equivalent GSLB layer on AWS/Azure, while relying on GCP's native global routing without needing that extra layer there) rather than assuming a single infrastructure-as-code template can be ported unchanged across all three. The key architectural discipline is keeping the L4/L7 decision and routing requirements as the portable, provider-agnostic part of the design, and treating exact product names, SKU tiers, and cross-region routing mechanics as the provider-specific implementation layer underneath it.
_What the interviewer is probing for:_ The ability to design at the right level of abstraction for genuine multi-cloud portability, recognizing real, non-cosmetic differences between providers (like GCP's native global L7 product) rather than assuming naming is the only difference.

## 12. Common Misconceptions

1. **"All three cloud providers' load balancer products are functionally identical, just named differently."** The core L4/L7 conceptual split is consistent, but real differences exist — most notably GCP's natively global Application Load Balancer versus AWS/Azure's regional-only L7 products.
2. **"A regional Layer 7 load balancer automatically provides global routing if deployed in multiple regions."** On AWS and Azure, this requires an explicit additional GSLB layer ([§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md)); simply deploying the same product in multiple regions doesn't create cross-region routing on its own.
3. **"Managed cloud load balancers don't need their own redundancy planning."** This part is actually true and is a genuine advantage — all three providers' load balancer products are inherently distributed across availability zones by design, unlike self-managed software load balancers ([§81](Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md)), which do require an explicit HA strategy.
4. **"WAF integration on an L7 product is a complete security solution."** It's a valuable additional layer but doesn't replace secure application design, authentication, and proper input validation at the application itself.

## 13. 🔑 Key Takeaways

- All three major cloud providers split their managed load balancer offerings along the same Layer 4/Layer 7 line established in [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md): AWS (NLB/ALB), Azure (Azure Load Balancer/Application Gateway), GCP (Network Load Balancer/Application Load Balancer).
- L7 products across all three providers integrate natively with that provider's WAF offering; L4 products are protocol-agnostic and generally preserve client source IP more directly.
- Managed cloud load balancers are inherently highly available across availability zones by design, removing a redundancy concern that self-managed software load balancers require explicit handling for.
- GCP's global Application Load Balancer natively spans regions behind a single anycast IP; AWS and Azure require an explicit additional GSLB layer ([§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md)) to achieve comparable cross-region routing.
- Choosing the correct product requires matching the workload's actual protocol and routing requirements ([§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)) to the L4 or L7 product family, not defaulting by habit.

## 14. Related Concepts & What's Next

[§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) is the direct conceptual foundation this entire section maps onto concrete cloud products. [§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md) covers the GSLB layer needed to achieve cross-region routing on AWS and Azure's regional-only L7 products. [§81](Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md) covers the self-managed software alternative to these managed cloud products, useful when a team needs capability, portability, or control that a managed service doesn't provide.

**Next Section:** [§81](Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md) — `Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md`

# Section 24 — Load Balancer (Layer 4) vs. Application Gateway (Layer 7)

## 24.1 Definition

**Plain language:** Both Load Balancer and Application Gateway distribute incoming traffic across multiple backend instances (like VMs in a Scale Set, Section 12) — but Load Balancer works at a lower, simpler network level (just IP addresses and ports), while Application Gateway understands actual web traffic (URLs, headers, cookies) and can make smarter, content-aware routing decisions.

**Precise definition:** **Azure Load Balancer** is a Layer 4 (Transport layer, in OSI model terms) load balancer, distributing TCP/UDP traffic across backend instances based on IP address and port information alone, with no visibility into the content of the traffic itself. **Azure Application Gateway** is a Layer 7 (Application layer) load balancer specifically for HTTP/HTTPS traffic, capable of routing decisions based on URL path, host header, and other application-level content, and bundling additional web-specific capabilities like a Web Application Firewall (WAF) and SSL/TLS termination.

## 24.2 Why It Exists / Problem It Solves

A single VM or App Service instance is both a single point of failure and a capacity ceiling; VM Scale Sets (Section 12) and multi-instance App Service deployments solve the "multiple instances" side of this, but something must still receive incoming traffic and distribute it across those instances — a client can't reasonably be expected to know about and directly address every individual backend instance itself, especially as instances are added/removed by autoscaling. Load Balancer and Application Gateway both solve this "distribute traffic across many backends" problem, but at different levels of traffic awareness: Load Balancer solves it generically for any TCP/UDP-based protocol without needing to understand what's actually being transmitted, while Application Gateway solves it specifically for HTTP/HTTPS web traffic, where deeper understanding of the request's actual content (not just its destination IP and port) enables smarter routing and additional web-specific security capabilities.

## 24.3 Azure Load Balancer (Layer 4)

### 24.3.1 How It Works

Load Balancer receives traffic on a **frontend IP** (public or private) and distributes it to a **backend pool** of instances based on a configurable **load balancing rule** (specifying which frontend port maps to which backend port, and which distribution algorithm to use), using **health probes** to continuously verify each backend instance is actually healthy before sending it traffic — an unhealthy instance is automatically removed from active rotation until it passes health checks again.

### 24.3.2 Public vs. Internal Load Balancer

- **Public Load Balancer** — has a public IP frontend, distributing internet-facing traffic to backend instances (which themselves may only have private IPs) — this is also the mechanism that allows VMs without their own public IP to still initiate outbound internet connections via **outbound rules**, a detail relevant to understanding how VMs behind a Load Balancer reach the internet for things like software updates.
- **Internal Load Balancer** — has a private IP frontend, distributing traffic that originates from within the VNet (or connected networks) only, used for internal, multi-tier application traffic (e.g., distributing traffic from a web tier to an internal application tier) that should never be reachable from the public internet directly.

### 24.3.3 SKU Tiers

Load Balancer is offered in different SKU tiers (commonly, Basic and Standard, with Standard being the modern, fully-featured, and generally recommended tier offering higher scale limits, Availability Zone support, and more granular security integration) — ⚠️ exact SKU names, feature differences, and Microsoft's current default/recommended tier should be verified against official documentation, since Basic tier has historically been on a path toward retirement in favor of Standard, and the current status of this transition should be checked before designing around a specific tier.

## 24.4 Application Gateway (Layer 7)

### 24.4.1 Content-Aware Routing

Because Application Gateway understands HTTP/HTTPS traffic specifically, it can route requests based on:

- **URL Path-Based Routing** — sending `/api/*` requests to one backend pool and `/images/*` requests to a different backend pool, for example, allowing a single Application Gateway to front multiple distinct backend services based on the request's actual path.
- **Host header-based (multi-site) routing** — routing traffic differently based on the hostname/domain in the request, allowing a single Application Gateway to serve multiple distinct websites/applications.

This kind of content-aware routing decision is fundamentally impossible for a Layer 4 Load Balancer, which has no visibility into the HTTP request's actual URL or headers at all — it only sees IP addresses and ports.

### 24.4.2 SSL/TLS Termination

Application Gateway can perform **SSL/TLS termination** — decrypting incoming HTTPS traffic at the gateway itself, then (optionally) communicating with backend instances over plain HTTP internally (within the presumably-trusted private VNet) — this offloads the computational cost of TLS decryption from the backend instances themselves and centralizes TLS certificate management at the gateway rather than requiring every backend instance to individually manage certificates.

⚠️ Terminating TLS at the gateway and using plain HTTP internally is a common pattern but should be a deliberate choice based on the organization's specific security requirements — some compliance frameworks or security postures require end-to-end encryption even for internal VNet traffic, in which case "SSL/TLS re-encryption" (decrypt at gateway, then re-encrypt for the backend connection) would be the appropriate configuration instead of a full offload to plain HTTP.

### 24.4.3 Web Application Firewall (WAF)

Application Gateway offers an integrated **Web Application Firewall (WAF)** SKU tier, providing protection against common web application attack patterns (such as those cataloged in the OWASP Top 10, a widely referenced industry list of common web application vulnerabilities) by inspecting HTTP request content itself — a capability entirely outside Layer 4 Load Balancer's scope, since it has no visibility into request content to inspect in the first place. WAF is covered in additional depth in Part 11's security discussion.

### 24.4.4 Autoscaling

Application Gateway (specifically its v2 SKU — ⚠️ verify current SKU/version naming against documentation) supports autoscaling of the gateway itself, automatically adjusting its own capacity to handle traffic volume, similar in concept to the compute autoscaling covered in Section 12.3.2, but applied to the gateway/load-balancing layer itself rather than backend compute instances.

## 24.5 Comparison Matrix

| Aspect                     | Load Balancer (Layer 4)                                      | Application Gateway (Layer 7)                                                                        |
| -------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| OSI Layer                  | Transport (4)                                                | Application (7)                                                                                      |
| Protocol awareness         | TCP/UDP, any protocol                                        | HTTP/HTTPS specifically                                                                              |
| Routing granularity        | IP + port only                                               | URL path, host header, and other HTTP content                                                        |
| SSL/TLS termination        | No                                                           | Yes                                                                                                  |
| Web Application Firewall   | No                                                           | Yes (WAF SKU)                                                                                        |
| Typical use case           | Any TCP/UDP workload; simple, protocol-agnostic distribution | Web applications/APIs needing content-aware routing and web-specific security                        |
| Performance characteristic | Very low latency, minimal processing overhead                | Slightly higher processing overhead due to content inspection, but negligible for most web workloads |

🎯 **Interview Tip:** "When would you use Load Balancer versus Application Gateway?" is an extremely common Azure networking interview question — the core distinguishing answer to lead with is the OSI layer difference (Layer 4 vs. Layer 7) and what that unlocks: content-aware routing, SSL termination, and WAF for Application Gateway, none of which Load Balancer can provide since it has no visibility into HTTP-level content.

## 24.6 Architecture Diagram

```
Internet
   │
   ▼
Application Gateway (public frontend, WAF enabled)
   │  Path-based routing:
   │    /api/*    → Backend Pool "app-tier" (App Service or VMSS)
   │    /images/* → Backend Pool "static-content" (Storage/CDN-backed)
   │  SSL/TLS terminated here; backend traffic re-encrypted or plain HTTP per policy
   │
   ▼
[Backend Pool: app-tier VMSS instances, spread across Availability Zones]
   │
   ▼ (internal-only traffic, Layer 4)
Internal Load Balancer (private frontend)
   │  Simple IP+port distribution, no content awareness needed here
   │
   ▼
[Backend Pool: internal database-facing service instances]
```

## 24.7 Configuration & Hands-On Example

**Creating a Standard Load Balancer with a health probe and load balancing rule:**

```bash
az network lb create \
  --resource-group rg-myapp-prod \
  --name lb-webapp-internal \
  --sku Standard \
  --frontend-ip-name feConfig \
  --backend-pool-name beBackendPool \
  --vnet-name vnet-prod \
  --subnet snet-backend

az network lb probe create \
  --resource-group rg-myapp-prod \
  --lb-name lb-webapp-internal \
  --name healthProbe \
  --protocol Tcp --port 80

az network lb rule create \
  --resource-group rg-myapp-prod \
  --lb-name lb-webapp-internal \
  --name httpRule \
  --protocol Tcp \
  --frontend-port 80 --backend-port 80 \
  --frontend-ip-name feConfig --backend-pool-name beBackendPool \
  --probe-name healthProbe
```

- **Purpose:** Creates an internal (private frontend, within `snet-backend`) Standard Load Balancer, a TCP health probe checking port 80, and a rule distributing incoming port-80 traffic to the backend pool, following the internal Layer-4 distribution pattern shown in the architecture diagram.
- **Important arguments explained individually:**
  - `--probe-name` (referenced in the rule) — the health probe determines which backend instances actually receive traffic; an instance failing the probe is automatically excluded until it recovers, directly implementing the health-check behavior described in Section 24.3.1.

**Creating an Application Gateway with path-based routing (conceptual, abbreviated for clarity):**

```bash
az network application-gateway create \
  --resource-group rg-myapp-prod \
  --name agw-webapp-prod \
  --sku Standard_v2 \
  --capacity 2 \
  --vnet-name vnet-prod \
  --subnet snet-appgw \
  --public-ip-address pip-agw-webapp \
  --servers <backend-pool-ip-or-fqdn-list>
```

- **Purpose:** Creates a v2 SKU (supporting autoscaling, per Section 24.4.4) Application Gateway with a public frontend, in its own dedicated subnet — Application Gateway requires a dedicated subnet not shared with other resource types, a specific Azure networking requirement worth remembering.
- ⚠️ Full path-based routing and WAF configuration require additional, more detailed configuration beyond this illustrative creation command (routing rules, listeners, and WAF policy definitions) — verify exact current command syntax and required sub-resource configuration against official documentation before building a complete production Application Gateway deployment.

## 24.8 Production & Enterprise Usage

Enterprises commonly use both together in the same architecture, as shown in Section 24.6's diagram: Application Gateway (with WAF) as the public-facing entry point for web/API traffic, handling SSL termination, content-aware routing across multiple backend services, and web application security filtering; and internal Load Balancers for simpler, private, Layer 4 distribution between internal application tiers where content-aware routing isn't needed and the simplicity/lower overhead of Layer 4 distribution is preferable. For multi-region deployments needing global traffic distribution rather than distribution within a single region, Azure Front Door (Section 25, covered next) sits at an even higher, global layer above both of these regional load-balancing mechanisms.

## 24.9 Security Considerations

- Application Gateway's WAF should be enabled and set to **Prevention mode** (actively blocking detected malicious requests) rather than only **Detection mode** (logging but not blocking) for production internet-facing applications, once WAF rules have been validated against legitimate traffic to avoid false-positive blocking of real users.
- SSL/TLS termination centralizes certificate management at the gateway, but the choice of full offload (plain HTTP internally) versus re-encryption for the backend connection should reflect the organization's actual internal-network trust model and any applicable compliance requirements, not default assumption.

## 24.10 Performance Considerations

Application Gateway's content inspection (path/header evaluation, WAF rule matching) introduces marginally more processing overhead per request than Load Balancer's simple IP/port-based distribution, though this overhead is generally negligible relative to typical web application response times; Application Gateway v2's autoscaling (Section 24.4.4) helps ensure the gateway layer itself doesn't become a bottleneck as traffic volume grows.

## 24.11 Monitoring

Both services integrate with Azure Monitor (Part 10); Application Gateway additionally provides WAF-specific logs detailing blocked/flagged requests and the specific rule that matched, essential for both tuning WAF rules (reducing false positives) and for security incident investigation.

## 24.12 Troubleshooting

| Symptom                                                                       | Likely Cause                                                                     | Fix                                                                                                                                        |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Load Balancer distributing traffic to an instance that's actually unhealthy   | Health probe misconfigured (wrong port/path, or too lenient failure threshold)   | Review and correct health probe configuration; verify it's actually checking a meaningful health indicator                                 |
| Application Gateway returns errors for legitimate requests after enabling WAF | WAF rules flagging legitimate traffic as malicious (false positive)              | Review WAF logs for the specific triggered rule; tune or exclude the specific rule if it's producing false positives, after careful review |
| Path-based routing not directing traffic to the expected backend pool         | Routing rule/listener path pattern misconfigured, or rule evaluation order issue | Review the Application Gateway's routing rules and listener configuration for correct path patterns and precedence                         |

## 24.13 Interview Questions — Section 24

### 🎯 Beginner

**Q: What's the fundamental difference between Azure Load Balancer and Application Gateway?**

_Model answer:_ Load Balancer operates at Layer 4 (Transport layer), distributing TCP/UDP traffic based only on IP address and port, with no awareness of the actual content of the traffic. Application Gateway operates at Layer 7 (Application layer), specifically for HTTP/HTTPS traffic, and can make routing decisions based on the actual request content — URL path, host header — while also providing SSL termination and an integrated Web Application Firewall, none of which Load Balancer can do since it simply doesn't have visibility into that level of the traffic.

_What the interviewer is probing:_ the fundamental OSI-layer distinction, which explains every subsequent capability difference between the two services.

### 🎯 Senior

**Q: Design the load-balancing and security layer for a public-facing e-commerce web application with a separate internal API for order processing that should never be directly internet-accessible.**

_Model answer:_ I'd place Application Gateway at the public edge, with a WAF policy in Prevention mode protecting against common web attacks, terminating SSL/TLS for the public-facing traffic, and using path-based routing if the web frontend and any public-facing API endpoints are served from the same domain but need to reach different backend pools. The web frontend backend pool would sit behind this Application Gateway. For the internal order-processing API, which should never be directly internet-accessible, I'd deploy it in a separate, non-internet-exposed subnet, fronted by an internal (private-frontend) Load Balancer for simple, low-overhead Layer 4 distribution across its instances — since this internal traffic doesn't need content-aware routing or a WAF, Layer 4 distribution is both sufficient and appropriately simpler/lower-latency than routing internal traffic through a second Application Gateway unnecessarily. NSGs (Section 22) on the internal API's subnet would further restrict inbound access to only the web frontend's subnet, ensuring the order-processing API is reachable only through the intended path, layering network-level access control on top of the load-balancing topology itself.

_What the interviewer is probing:_ whether the candidate can correctly match each traffic pattern (public web-facing vs. internal service-to-service) to the appropriately-scoped load-balancing tool, rather than defaulting to Application Gateway everywhere out of unfamiliarity with when simpler Layer 4 distribution is the better fit.

## 24.14 Common Misconceptions

- **"Application Gateway is just a more expensive, better version of Load Balancer, so you should always use it."** False — they serve different purposes; using Application Gateway for simple internal TCP/UDP traffic that doesn't need content-aware routing or WAF adds unnecessary complexity and processing overhead without corresponding benefit; Load Balancer remains the right tool for that scenario.
- **"Load Balancer can inspect and route based on HTTP request content."** False — Load Balancer operates purely at Layer 4 and has no visibility into HTTP-level content whatsoever; this capability is exclusively Application Gateway's (Layer 7) domain.

## 24.15 Key Takeaways

- 🔑 Load Balancer (Layer 4) distributes TCP/UDP traffic based on IP/port alone; Application Gateway (Layer 7) understands HTTP/HTTPS content, enabling path/host-based routing, SSL termination, and WAF.
- 🔑 Public and Internal Load Balancer variants serve internet-facing and private-only distribution needs respectively.
- 🔑 Application Gateway's WAF should be run in Prevention mode for production internet-facing protection, after validating rules against real traffic to avoid false-positive blocking.
- 🔑 Real architectures commonly use both together — Application Gateway at the public web edge, internal Load Balancers for simpler private service-to-service distribution — matched to each traffic pattern's actual needs.

## 24.16 Related Concepts (Next Up)

Section 25 covers **Azure Front Door & CDN** — extending traffic distribution and content delivery beyond a single region to a global scale, sitting above both Load Balancer and Application Gateway in the traffic path for architectures spanning multiple Azure regions, and introducing the Edge/PoP network concept first mentioned in Section 3.3.5.

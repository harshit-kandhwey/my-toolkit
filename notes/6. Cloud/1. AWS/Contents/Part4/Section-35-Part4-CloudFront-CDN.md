# Part 4 - Section 7 - Amazon CloudFront - CDN

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: CloudFront caches copies of your content at hundreds of locations worldwide, close to users, so most requests are served from a nearby cached copy instead of traveling back to your origin - dramatically reducing latency and taking load off your origin.

Precise: Amazon CloudFront is AWS's Content Delivery Network (CDN) service - a globally distributed system of edge locations that caches and serves content close to end users, reducing latency, improving performance, and reducing origin load, integrating with WAF, ACM, and Route 53.

---

## 2. Why It Exists

- Edge locations (Part 1 Section 2) exist to reduce content-delivery latency - CloudFront is the service that actually uses them for this purpose (Route 53 also uses edge locations, but for DNS).
- Core physics problem: speed of light imposes a hard latency floor for users far from the origin - the only lever is moving content physically closer, which caching at edge locations achieves.
- Origin offload: cached repeated requests mean the origin handles far less traffic - reduced load AND cost, a genuine two-sided benefit.

---

## 3. Core CloudFront Concepts

### 3.1 Distribution

The core CloudFront resource - configuration telling CloudFront which origin(s) to pull from, how to cache, and how to serve content; assigned a domain name (or a custom one via Route 53/ACM).

### 3.2 Origin

Where CloudFront fetches content when not cached - commonly an S3 bucket, an ALB, an EC2 instance, or an on-premises server. A single distribution can have multiple origins with cache behaviors routing different paths to different origins (parallel to ALB path-based routing, but for CDN origin selection).

### 3.3 Edge Locations and Regional Edge Caches

Edge locations are the hundreds of CloudFront points-of-presence holding cached content closest to users. Regional Edge Caches sit between edge locations and origin - a larger cache holding less-popular content longer, reducing origin fetches and improving hit ratio for regionally-popular content.

### 3.4 Cache Behaviors

Define how CloudFront handles requests matching a path pattern - origin selection, cookie/header/query-string forwarding, caching policy. Evaluated in order of specificity - a more specific path pattern takes precedence over a broader default.

### 3.5 Cache Policies and TTL

A cache policy determines the cache key (which request attributes make requests "different" and separately cacheable) and TTL (min/max/default). Including too many attributes in the cache key fragments the cache, dramatically reducing hit ratio - a real, common mistake.

### 3.6 Origin Access Control (OAC) - Securing S3 Origins

Ensures an S3 origin bucket can only be accessed through CloudFront, not its direct public S3 URL - extends the "don't leave S3 buckets publicly accessible" theme. A materially important security pattern: without OAC, content is also directly accessible at the raw S3 URL, bypassing CloudFront's caching, WAF, and access controls entirely.

---

## 4. CloudFront and WAF

- Attach WAF to CloudFront (not just the origin) because CloudFront sits at the edge, closest to the user and furthest from the origin - malicious traffic filtered before reaching the origin Region, a performance/cost benefit on top of security.
- Mechanically: WAF operates on HTTP/HTTPS content, and CloudFront is exactly the HTTP/HTTPS-serving layer where that content is available for inspection - the same reasoning that placed WAF on ALB, now at the edge.

---

## 5. Signed URLs and Signed Cookies

- For content that shouldn't be publicly accessible (paid/subscription/time-limited), CloudFront supports signed URLs (single URL, embedded signed expiration/policy) and signed cookies (broader access across multiple files via one cookie).
- Signed URLs: individual file access (one video, one document). Signed cookies: access to multiple resources (an entire subscription-gated library) without signing every URL.

---

## 6. HTTPS and TLS Termination at CloudFront

- CloudFront can terminate TLS at the edge (parallel to ALB TLS termination, at the CDN layer), using ACM for the certificate, optionally re-encrypting to the origin for end-to-end encryption.
- Viewer protocol policy - redirect HTTP to HTTPS, allow both, or require HTTPS-only - a common hardening choice.

---

## 7. CloudFront Functions and Lambda@Edge

- CloudFront Functions - lightweight JavaScript functions at edge locations, for simple, high-volume, sub-millisecond operations (header manipulation, URL rewrites, simple redirects).
- Lambda@Edge - actual Lambda functions running at edge (or Regional Edge Cache) locations, for more complex logic, at higher latency/cost than CloudFront Functions.
- Decision mirrors the broader "right tool for the compute need" theme - CloudFront Functions for simple high-volume edge logic, Lambda@Edge for genuinely complex processing.

---

## 8. Production & Enterprise Usage

- Static asset delivery from S3 (images, video, JS/CSS) via CloudFront + OAC - one of the most common, foundational use cases, reducing both latency and S3 origin cost.
- Dynamic content acceleration - CloudFront accelerates even uncacheable dynamic content via AWS's optimized backbone between edge and origin.
- Multi-origin distributions for microservices - one distribution routing /api/_ to an ALB, /static/_ to S3, /images/\* to a different bucket, consolidating multiple endpoints into one coherent, cacheable, WAF-protected front door.
- CloudFront as the standard front door for the WAF + Shield Advanced layered edge-security stack (Part 2 Section 9).

---

## 9. Security Considerations

- OAC is a required best practice for any S3 origin, not optional - without it, direct public URL bypass defeats every CloudFront control.
- Signed URLs/cookies are the correct mechanism for restricted content - unguessable-but-public URLs are not a substitute.
- WAF + Shield Advanced at the CloudFront layer remains the standard layered edge-security stack, with CloudFront as the delivery mechanism underneath.

---

## 10. Performance Considerations

- Cache hit ratio is the primary performance metric, driven by cache-key design - overly broad keys fragment the cache; overly narrow ones risk serving stale/wrong content across users who shouldn't share a response.
- Regional Edge Caches improve hit ratio for regionally-popular-but-not-globally-popular content - a genuine intermediate caching tier.
- TTL tuning mirrors Section 6's DNS TTL trade-off - low TTL means fresher content, more origin fetches; high TTL means better efficiency, slower update propagation.

---

## 11. Troubleshooting

| Symptom                                                | Cause                                                                      | Fix                                                                                      |
| ------------------------------------------------------ | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Users access S3 content directly, bypassing CloudFront | No OAC configured, bucket/objects publicly accessible                      | Configure OAC; restrict bucket policy to CloudFront only                                 |
| Poor cache hit ratio despite cacheable content         | Cache key includes unnecessary varying attributes                          | Narrow the cache policy's cache key to attributes that genuinely differentiate responses |
| Content updates not showing for users                  | TTL still active on cached version                                         | Wait out TTL, or use a CloudFront invalidation                                           |
| Signed URL access being bypassed                       | Underlying resource also directly accessible (e.g., S3 origin without OAC) | Ensure OAC (or equivalent) makes signed-URL access the only path                         |

---

## 12. Best Practices & Anti-Patterns

Best practices: always configure OAC for S3 origins; design cache keys deliberately; attach WAF to CloudFront for internet-facing distributions; use signed URLs for single-file, signed cookies for multi-resource access; use CloudFront Functions for simple logic, Lambda@Edge for complex processing.

Anti-patterns: leaving an S3 origin bucket independently public alongside CloudFront; overly broad cache keys degrading hit ratio; relying on unguessable-but-public URLs instead of signed access; using Lambda@Edge for trivial logic CloudFront Functions could handle.

---

## 13. Common Misconceptions

- "CloudFront is only for static content." False - accelerates dynamic uncacheable content too, and fronts APIs (ALB origins) as well as static buckets.
- "An S3 bucket behind CloudFront is automatically private." False - without OAC explicitly configured, the bucket can remain independently public.
- "CloudFront Functions and Lambda@Edge are interchangeable." False - different complexity/latency/cost tiers.
- "A broader cache key always improves correctness with no downside." False - fragments the cache, degrading hit ratio.

---

## 14. Interview Questions (with model answers)

Beginner - What problem does CloudFront solve, and how? Reduces latency by caching content at edge locations near users instead of every request reaching the origin. Also reduces origin load since repeated requests serve from cache - a performance benefit for users and a cost/load benefit for the origin simultaneously.

Beginner - Why is OAC important for an S3 CloudFront origin? Without it, the bucket could be directly, publicly accessible at its raw S3 URL, completely bypassing CloudFront - any access controls, caching, or WAF protection could be sidestepped by going straight to S3. OAC ensures CloudFront is the sole access path, keeping the bucket private.

Intermediate - Why might an overly broad cache key hurt performance? The cache key determines which attributes make requests "different." Including attributes that vary but don't actually change the response makes CloudFront treat many requests as unique when they could share one cached response - fragmenting the cache, increasing origin misses, hurting latency and origin load, the opposite of CloudFront's purpose.

Intermediate - Signed URL vs signed cookie for restricted content? Signed URLs for single-file access (one video/document), each carrying its own signed policy. Signed cookies for multi-resource access (an entire subscription library) without signing every individual URL.

Senior - Design CloudFront for a marketing site (static), a REST API, and a subscription video library, with a requirement that nothing bypasses CloudFront? Single distribution, multiple origins, path-based cache behaviors: marketing assets from an OAC-protected S3 bucket with no independent public access; REST API routed to an ALB origin with minimal/no caching (still accelerated via AWS's backbone even uncached); video library from a separate OAC-protected origin using signed cookies (multi-video subscription access, not one-off). WAF attached at the distribution level; HTTPS-only via ACM. No-bypass requirement satisfied by OAC on both S3 origins plus the ALB's security group only allowing CloudFront's traffic (known IP ranges or shared secret header), not open to the internet directly.

---

## Key Takeaways

1. CloudFront caches content at edge locations to reduce latency and offload the origin - a two-sided benefit grounded in the physical reality that proximity is the only real latency lever.
2. Origin Access Control is essential, not optional, for S3 origins - without it, the raw URL bypasses every CloudFront control.
3. Cache-key design directly determines cache hit ratio - unnecessary varying attributes fragment the cache and degrade the performance benefit CloudFront exists to provide.
4. Signed URLs (single-file) and signed cookies (multi-resource) are the correct mechanisms for restricted content access.
5. CloudFront Functions and Lambda@Edge serve different complexity tiers of edge compute - lightweight/high-volume vs more complex logic.

## Related Concepts (forward links)

- AWS Certificate Manager for TLS certificates used by CloudFront (and ALB) -> [§36](./Section-36-Part4-ACM-APIGateway.md)
- API Gateway as an alternative/complementary API front door, sometimes behind CloudFront -> [§36](./Section-36-Part4-ACM-APIGateway.md)
- VPC Endpoints and Flow Logs for observing origin-side traffic -> [§37](./Section-37-Part4-VPCEndpoints-FlowLogs-Troubleshooting.md)

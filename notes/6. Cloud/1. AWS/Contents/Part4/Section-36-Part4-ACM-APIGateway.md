# Part 4 - Section 8 - AWS Certificate Manager & API Gateway

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: AWS Certificate Manager provisions and manages the SSL/TLS certificates that let applications use HTTPS, handling renewal automatically. API Gateway is a fully managed service for creating, publishing, and securing APIs - the front door that routes requests to Lambda functions, AWS services, or your own backend without you managing infrastructure.

Precise: AWS Certificate Manager (ACM) is a managed service for provisioning, deploying, and automatically renewing SSL/TLS certificates for AWS services. Amazon API Gateway is a fully managed service for creating, publishing, maintaining, monitoring, and securing APIs at any scale, integrating natively with Lambda, other AWS services, and HTTP backends.

---

## 2. AWS Certificate Manager (ACM)

### 2.1 Why It Exists

- ACM supplies the certificates referenced throughout ALB and CloudFront TLS termination discussions, removing manual purchase/install/renewal pain - especially the common, high-impact failure of a certificate silently expiring and causing an outage.
- Free for AWS-issued certificates used with integrated services (ALB, CloudFront, API Gateway) - a deliberate removal of a traditional HTTPS cost/friction point.

### 2.2 Certificate Validation

- DNS validation - add a CNAME record to the domain's DNS (trivially automated via Route 53) - AWS's recommended method, enabling automatic renewal without manual action.
- Email validation - sends a validation email requiring manual click each time, including at renewal - weaker for automatic renewal.

Interview tip: DNS validation is preferred specifically because it enables automatic renewal without human intervention - email validation requires a person to click a link, a real operational risk at renewal time.

### 2.3 Where ACM Certificates Can Be Used

- Only with integrated AWS services (ALB/NLB, CloudFront, API Gateway, etc.) - you cannot export the private key to install on a self-managed EC2 web server.
- A self-managed server needs a certificate from a traditional external Certificate Authority instead.

### 2.4 Regional Consideration for CloudFront

- ACM certificates used with CloudFront MUST be requested in us-east-1 (N. Virginia) specifically, regardless of where other resources live - a frequently confused, specific platform requirement.

---

## 3. Amazon API Gateway

### 3.1 Why It Exists

- API Gateway is the standard way to expose Lambda (or other backends) as a production-grade HTTP API - handling routing, auth, rate limiting, transformation, monitoring without building it yourself.
- Extends the "don't manage servers" philosophy from Lambda to the API-management layer.

### 3.2 API Types

| Type          | Best for                                                                   | Characteristics                                       |
| ------------- | -------------------------------------------------------------------------- | ----------------------------------------------------- |
| HTTP API      | Modern, low-latency, cost-sensitive REST-style APIs                        | Newer, simpler, lower cost, fewer advanced features   |
| REST API      | Full feature set (request validation, API keys, usage plans, private APIs) | Original offering, more configuration, higher cost    |
| WebSocket API | Real-time bidirectional communication (chat, dashboards, gaming)           | Persistent connections, content-based message routing |

Key idea: HTTP APIs are AWS's current general recommendation for new REST-style APIs given lower cost/latency, unless a REST-specific feature is genuinely required - the same "start simpler unless a feature justifies more" pattern seen throughout this course.

### 3.3 Integration Types

- Lambda integration - most common, routes to a Lambda function.
- HTTP integration - routes to an existing HTTP endpoint (ALB or any HTTP backend).
- AWS service integration - routes directly to another AWS service API (e.g., DynamoDB) without a Lambda function, reducing glue code.
- Mock integration - returns a response without forwarding anywhere, for testing or static responses.

### 3.4 Authentication and Authorization

- IAM authorization - uses IAM permissions to control who can invoke specific methods.
- Lambda authorizers - a custom Lambda function inspecting the request and returning an IAM policy decision - flexible for custom auth logic not mapping cleanly to IAM/Cognito.
- Cognito authorizers - integrate with Amazon Cognito user pools, validating Cognito-issued tokens without custom Lambda logic.

### 3.5 REST-API-Specific Features

- Usage Plans and API Keys - issue API keys per consumer tied to usage plans (rate limits, quota) - essential for API-as-a-product scenarios; not natively supported by HTTP APIs.
- Request validation - validates incoming request structure before it reaches the backend, rejecting malformed requests early, reducing unnecessary (and for Lambda, costly) invocations.
- Private APIs - accessible only from within a VPC via a VPC Endpoint, never the public internet - extends PrivateLink's concept to the API-Gateway layer.

### 3.6 Stages and Deployment

- An API must be deployed to a stage (dev/staging/prod) before it's callable; each stage has its own config (throttling, logging, variables) - mirrors environment separation at the individual-API level.
- Canary deployments - direct a percentage of traffic to a new stage version before full promotion - the same gradual percentage-based traffic-shifting pattern seen at nearly every layer of this course (weighted target groups, weighted DNS routing, now API deployments).

### 3.7 Throttling and Caching

- Throttling - enforces rate limits at account/API/usage-plan level, protecting backends (especially Lambda's own concurrency limits) from being overwhelmed.
- Caching - API Gateway can cache responses at its own layer, reducing requests reaching the backend - conceptually similar to CloudFront caching but scoped to API responses.

---

## 4. ACM + API Gateway + CloudFront Together

Flow: Client -> CloudFront (optional, TLS terminated with a us-east-1 ACM cert, caching/WAF/global distribution) -> API Gateway (custom domain, its own ACM cert in its own Region; routing/auth/throttling/validation) -> Lambda/HTTP backend/AWS service integration.

- A common sophisticated pattern: CloudFront in front of API Gateway, combining edge caching/WAF/global distribution with API Gateway's routing/auth/throttling - each layer contributing something distinct.
- Two separate ACM certificates typically involved - one for CloudFront (must be us-east-1) and one for the API Gateway custom domain (in its own Region) - an easy detail to miss.

---

## 5. Production & Enterprise Usage

- HTTP API + Lambda + Cognito authorizer - a common modern serverless API stack, cost-effective and low-latency with managed identity.
- REST API for API-as-a-product - usage plans/API keys are why organizations selling tiered API access typically need REST APIs.
- Private REST APIs for internal service-to-service communication - never internet-reachable, accessible only via VPC Endpoint.
- ACM's automatic renewal eliminates manual certificate-expiration tracking as an operational burden - a concrete, frequently-cited improvement.

---

## 6. Security Considerations

- Lambda authorizer results should be cached (configurable TTL) to avoid invoking on every request - balance performance/cost against how long a revoked permission might remain valid.
- Private APIs are correct for genuinely internal-only APIs - relying solely on IAM/authorizer logic on a public endpoint is less robust than removing public reachability entirely.
- DNS validation for ACM matters for security continuity too - automatic renewal avoids lapses that could themselves become incidents.

---

## 7. Performance Considerations

- HTTP APIs have lower latency than REST APIs for equivalent functionality - a genuine reason beyond cost to default to HTTP API.
- API Gateway caching reduces backend load exactly like CloudFront caching reduces origin load, one layer closer to the backend.
- CloudFront in front of API Gateway adds an edge caching layer for cacheable responses while still relying on API Gateway for routing/auth logic.

---

## 8. Troubleshooting

| Symptom                                          | Cause                                                          | Fix                                                          |
| ------------------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------ |
| ACM certificate stuck "pending validation"       | DNS CNAME not added/propagated, or email link not clicked      | Verify CNAME propagation (DNS) or check for validation email |
| CloudFront can't use a requested ACM certificate | Not requested in us-east-1                                     | Re-request specifically in us-east-1                         |
| API Gateway authorization failing unexpectedly   | Stale cached Lambda authorizer result, or authorizer logic bug | Check cache TTL and logic; shorten TTL if staleness recurs   |
| Need different rate limits per consumer          | Using HTTP API, which lacks usage plans/API keys               | Migrate to REST API                                          |

---

## 9. Best Practices & Anti-Patterns

Best practices: use DNS validation for ACM wherever possible; remember the us-east-1 requirement for CloudFront certs; default to HTTP API, reserving REST API for usage plans/validation/private API needs; use Private APIs for internal-only services; cache Lambda authorizer results with a deliberate TTL.

Anti-patterns: email validation for certs needing reliable auto-renewal; requesting a CloudFront cert in the wrong Region; defaulting to REST API "just in case"; exposing an internal-only API publicly and relying only on authorization logic.

---

## 10. Common Misconceptions

- "ACM certificates work on any server including self-managed EC2." False - only integrated AWS services; self-managed servers need an external CA certificate.
- "Any ACM certificate works with any AWS service regardless of Region." False - CloudFront specifically requires us-east-1.
- "HTTP APIs and REST APIs are the same thing." False - different feature sets, cost, latency; REST APIs support usage plans/API keys/request validation HTTP APIs don't.
- "API Gateway always needs a Lambda function behind it." False - also supports direct HTTP and AWS service integrations.

---

## 11. Interview Questions (with model answers)

Beginner - What problem does ACM solve? Provisions/manages SSL/TLS certificates for integrated AWS services and handles renewal automatically - eliminating manual installation and the risk of forgetting to renew before expiration, a historically real cause of outages.

Beginner - HTTP API vs REST API? HTTP API: newer, simpler, lower cost/latency, for most modern REST-style APIs. REST API: original, more feature-rich - usage plans/API keys for per-consumer rate limiting, request validation before the backend. Default to HTTP API unless a REST-specific feature is needed.

Intermediate - Why must a CloudFront ACM certificate be requested in us-east-1? CloudFront is global, but AWS specifically requires certificates attached to a CloudFront distribution to be requested in us-east-1 regardless of where other resources live - a specific, non-obvious platform requirement and common first-time point of confusion.

Intermediate - Lambda authorizer vs Cognito authorizer - when to choose which? Cognito authorizer when already using Cognito for identity and just validating its tokens. Lambda authorizer for custom authentication logic not mapping to Cognito directly - third-party token formats, custom identity systems, extra business logic. More flexible but more custom-code-dependent.

Senior - Design API architecture for tiered external API sales, needing global low latency and abuse protection? REST API specifically for usage plans/API keys - distinct key per customer tied to a usage plan matching their tier's limits. CloudFront in front of the API Gateway custom domain for edge caching/global latency, with a us-east-1 ACM cert for CloudFront and a separate ACM cert (API's own Region) for the API Gateway domain. Abuse protection: WAF on CloudFront filtering at the edge, API Gateway's own throttling as a second defense layer, request validation on the REST API rejecting malformed requests before reaching Lambda - reducing both abuse surface and invocation cost.

---

## Key Takeaways

1. ACM removes certificate management pain - automatic issuance/renewal for integrated services, DNS validation preferred for enabling renewal without human intervention.
2. ACM certificates work only with integrated AWS services, and CloudFront-bound certificates must be requested in us-east-1 regardless of other resources' Region.
3. API Gateway is the managed front door for Lambda (and other backends), handling routing/auth/throttling/monitoring you'd otherwise build yourself.
4. HTTP API vs REST API is a genuine feature/cost/latency trade-off - default to HTTP API, reserve REST API for usage plans/API keys/validation/private API needs.
5. CloudFront + API Gateway together (each with its own correctly-scoped ACM cert) is a standard sophisticated pattern - edge caching/WAF/distribution from CloudFront, routing/auth/throttling from API Gateway, neither redundant with the other.

## Related Concepts (forward links)

- VPC Endpoints (for Private APIs), Flow Logs, network troubleshooting -> Part 4, Section 9 (next, final content section)
- Amazon Cognito in full depth -> Part 10 (related technologies)
- Part 4 Wrap-Up and comprehensive Networking interview drill -> Part 4, Section 10

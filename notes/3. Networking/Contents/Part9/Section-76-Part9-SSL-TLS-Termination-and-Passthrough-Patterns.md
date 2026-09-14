# Section 76 (Part 9): SSL/TLS Termination and Passthrough Patterns

## 1. Definition

**Plain language:** When a client connects over HTTPS, someone has to decrypt that traffic to actually read it. TLS termination means the load balancer does that decryption itself and talks to the backends in plain, unencrypted HTTP. TLS passthrough means the load balancer never decrypts anything — it just forwards the still-encrypted bytes straight through, and the backend server does the decryption itself.

**Precise definition:** **TLS termination** at a load balancer means the load balancer holds the TLS certificate and private key, performs the full TLS handshake with the client itself, decrypts incoming traffic, and forwards the request to the backend either in plaintext (**TLS termination, no re-encryption**) or by establishing a second, separate TLS connection to the backend (**TLS termination with re-encryption**, sometimes called **TLS bridging**). **TLS passthrough** means the load balancer forwards the encrypted TCP stream to the backend untouched, without possessing the certificate or private key at all, and the backend performs the TLS handshake directly with the client. A middle-ground pattern, **SNI-based routing**, inspects only the unencrypted **Server Name Indication (SNI)** field sent in the client's initial TLS handshake to route to the correct backend by hostname, without decrypting the rest of the session.

> 💡 **Tip:** TLS termination is fundamentally an L7-adjacent capability ([§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)) — the load balancer must fully own and process the TLS session to do it, whereas passthrough is naturally compatible with pure L4 forwarding, since the load balancer never needs to understand anything about the encrypted content at all.

## 2. Why This Matters

- **Termination is what enables Layer 7 features at all.** Path-based routing, header inspection, WAF rules ([§89](../Part10/Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)), and cookie-based session persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) all require reading the decrypted HTTP request — none of that is possible while traffic remains encrypted, which is exactly what passthrough preserves.
- **Certificate management is centralized or distributed depending on this choice.** Termination means one certificate (or a small set) lives at the load balancer, simplifying renewal and rotation; passthrough means every backend needs its own certificate and its own renewal process, multiplying operational surface area.
- **Compliance and internal security policy sometimes mandate encryption all the way to the backend**, ruling out plain termination-without-re-encryption and requiring either passthrough or termination-with-re-encryption (TLS bridging) instead — this is a real, recurring requirement in regulated environments.
- **Performance trade-offs are concrete and measurable.** TLS handshakes and encryption/decryption consume CPU; terminating at the load balancer offloads that cost from every individual backend onto the load balancer tier, which is one of the most common reasons organizations terminate centrally even when re-encryption to the backend is also configured.
- **The choice directly affects what the backend can see.** A backend behind full termination sees plaintext HTTP and must rely on forwarded headers for any client-TLS-related information (client certificate details, cipher suite used); a backend performing its own passthrough termination sees everything about the TLS session directly.

## 3. Prerequisites and Dependencies

This section depends directly on [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) for the L4/L7 distinction underlying termination vs. passthrough, and assumes basic TLS handshake mechanics (certificates, the handshake sequence, SNI) which are covered in full in Part 8, [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) (TLS/SSL fundamentals) and [§66](../Part8/Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md) (certificate authorities and chains of trust) — this section uses those concepts without re-deriving them. [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md)'s backend pool concept is assumed throughout.

## 4. Architecture / Conceptual Diagram

```text
   TLS TERMINATION (no re-encryption)          TLS TERMINATION WITH RE-ENCRYPTION
   ("TLS bridging")

   Client ══TLS══► LB ──plain HTTP──► Backend  Client ══TLS══► LB ══new TLS══► Backend
           (encrypted)  (unencrypted)                  (encrypted)   (re-encrypted,
                                                                       separate cert)
   LB holds cert + key.                        LB holds cert + key for CLIENT-facing
   Backend gets plaintext —                    leg; backend has its OWN cert + key
   trusts the network path                     for the LB-to-backend leg.
   between LB and backend                      Encrypted end-to-end, but LB still
   is itself secure.                           sees plaintext in between.

   TLS PASSTHROUGH                             SNI-BASED ROUTING (hybrid)

   Client ══════════TLS═══════════► Backend    Client ──TLS ClientHello──► LB
           (LB forwards encrypted                      (SNI field read in
            bytes untouched — LB                        cleartext, rest stays
            never holds the cert/key                    encrypted)
            or decrypts anything)                              │
                                                       route by SNI hostname
   Backend performs the FULL TLS                               ▼
   handshake directly with the                    ══════TLS═══════► Backend
   client. LB is a pure L4 forwarder              (still fully encrypted end
   for this connection.                            to end — LB only read SNI)
```

- **Termination without re-encryption** is the simplest and lowest-overhead pattern but means traffic between the load balancer and backend travels unencrypted — acceptable only when that internal network segment is itself trusted and isolated (e.g., a private subnet with no other tenants).
- **Termination with re-encryption (TLS bridging)** satisfies "encrypted everywhere" requirements while still allowing the load balancer to inspect and route on decrypted content in the middle — at the cost of two full TLS handshakes and certificate management on both legs.
- **Passthrough** keeps the load balancer completely blind to content (no L7 features possible on that connection) but avoids all central certificate/private-key exposure at the load balancer, which matters when the backend team, not the network/platform team, must retain sole custody of the private key.
- **SNI-based routing** is the practical way to run multiple TLS-terminating backends (each serving a different hostname, each with its own certificate) behind one L4-level load balancer without that load balancer ever holding any of the certificates itself.

## 5. Hands-On

### 5.1 TLS Termination at NGINX With Plaintext to Backend

**Purpose:** Show a standard termination configuration where the load balancer holds the certificate and forwards plaintext HTTP internally.

**Syntax:**

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/certs/example.com.crt;
    ssl_certificate_key /etc/nginx/certs/example.com.key;

    location / {
        proxy_pass http://backend_pool;   # note: http, not https
        proxy_set_header X-Forwarded-Proto https;
    }
}

upstream backend_pool {
    server 10.0.1.10:8080;
}
```

**Example usage and expected output:**

```bash
$ curl -sv https://example.com/ 2>&1 | grep -E "SSL connection|HTTP/"
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
< HTTP/1.1 200 OK
```

- The client's connection is encrypted (TLSv1.3 visible in the handshake), but the connection from NGINX to the backend (`proxy_pass http://...`) is plain HTTP — the backend never sees TLS at all.
- `proxy_set_header X-Forwarded-Proto https` is essential here — without it, the backend has no way to know the original client request arrived over HTTPS, which breaks anything that depends on that (redirect logic, "secure" cookie flags).

**Production usage example:** This is the default, most common pattern for internal microservice traffic within a single trusted VPC/subnet, where the network segment between the load balancer and backend is not exposed beyond the organization's own infrastructure.

**Common errors:** Forgetting `X-Forwarded-Proto` causes subtle bugs — application frameworks that generate absolute URLs or set secure-only cookies based on the *original* client protocol will incorrectly think the request arrived over plain HTTP, sometimes causing redirect loops (the app redirects to `https://` again, but the LB already terminated it, restarting the cycle).

### 5.2 TLS Passthrough in HAProxy

**Purpose:** Show a passthrough configuration where the load balancer never possesses the certificate and forwards the encrypted stream directly to backends that each terminate TLS themselves.

**Syntax:**

```
frontend tls_front
    bind *:443
    mode tcp
    tcp-request inspect-delay 5s
    tcp-request content accept if { req.ssl_hello_type 1 }
    use_backend web_pool

backend web_pool
    mode tcp
    server web1 10.0.1.10:443 check
    server web2 10.0.1.11:443 check
```

**Example usage and expected output:**

```bash
$ curl -sv https://example.com/ 2>&1 | grep -E "SSL connection|subject:"
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
*  subject: CN=example.com
```

- The certificate `curl` receives and validates is the **backend's own certificate** (`10.0.1.10:443`), not one presented by HAProxy — HAProxy here never touches the TLS session at all, confirmed by `mode tcp` forwarding raw bytes.

**Production usage example:** Passthrough is the standard pattern when regulatory or organizational policy requires the private key to remain solely in the backend team's custody (never shared with a shared platform/network team operating the load balancer), or when client certificate authentication (mutual TLS) requires the backend to see and validate the client's certificate directly.

**Common errors:** Because the load balancer never decrypts the traffic in passthrough mode, it structurally cannot do path-based routing, header inspection, or any L7 feature on that connection — attempting to combine passthrough with L7 routing rules in the same listener is a configuration contradiction that will simply not work as expected.

### 5.3 SNI-Based Routing Without Decryption

**Purpose:** Route TLS connections to different backend pools by hostname, without the load balancer ever decrypting the session — a hybrid between pure passthrough and full termination.

**Syntax:**

```
frontend tls_sni_front
    bind *:443
    mode tcp
    tcp-request inspect-delay 5s
    tcp-request content accept if { req.ssl_hello_type 1 }
    use_backend api_pool if { req.ssl_sni -i api.example.com }
    use_backend web_pool if { req.ssl_sni -i www.example.com }
    default_backend web_pool
```

**Example usage and expected output:**

```bash
$ curl -sv https://api.example.com/ 2>&1 | grep "subject:"
*  subject: CN=api.example.com

$ curl -sv https://www.example.com/ 2>&1 | grep "subject:"
*  subject: CN=www.example.com
```

- Each hostname reaches a distinct backend pool, each presenting its own distinct certificate — HAProxy only ever read the plaintext SNI field from the initial handshake to make this routing decision, and never decrypted anything past that.

**Production usage example:** SNI-based routing is common for multi-tenant platforms where each tenant's traffic needs to reach a distinct backend with its own certificate, without centralizing all tenant private keys at a shared load balancer.

**Common errors:** Clients that don't send SNI at all (very old TLS clients, or specific non-browser clients misconfigured to omit it) have no hostname for the load balancer to route on — a `default_backend` fallback is necessary to avoid connections being dropped outright in that case.

## 6. Production Usage Notes

- **Termination is the overwhelmingly more common pattern for standard web/API traffic**, primarily because it enables the L7 features (routing, WAF, persistence) that most HTTP-based architectures actually need; passthrough and pure L4 patterns are reserved for cases with a specific, deliberate reason to avoid decryption at the load balancer.
- **Certificate rotation is dramatically simpler under termination** — renewing a certificate at the load balancer (or via ACME automation, Part 8 [§66](../Part8/Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)) updates the trust for every backend simultaneously, versus needing to coordinate rotation across every individual backend under passthrough.
- **Mutual TLS (mTLS), where the client also presents a certificate the server validates**, generally requires either passthrough (so the backend can validate the client cert directly) or a termination configuration explicitly designed to extract and forward client certificate details to the backend — this is a common point of confusion when combining mTLS requirements with a terminating load balancer.

## 7. Security Considerations

- **Termination without re-encryption exposes plaintext traffic on the internal network segment between load balancer and backend** — this is an acceptable, common trade-off only when that segment is genuinely isolated and trusted; in shared or multi-tenant network environments, re-encryption (TLS bridging) is the safer default.
- **Centralizing the private key at the load balancer under termination concentrates risk** — a compromised load balancer under termination exposes the ability to decrypt all traffic passing through it, whereas under passthrough, compromising the load balancer alone doesn't expose any TLS private key at all (though it could still enable traffic interception if the attacker can also manipulate routing).
- **SNI itself is sent in cleartext even under otherwise-encrypted TLS** (prior to encrypted-SNI/ECH adoption), meaning the hostname a client is connecting to is visible to any network observer along the path regardless of which pattern is used — this is a known, generally accepted limitation rather than something termination or passthrough choice changes.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                                     | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Application redirect loop on every HTTPS request                    | TLS terminated at LB but `X-Forwarded-Proto` not set/read, app thinks request is plain HTTP and redirects | Set `X-Forwarded-Proto https` at the LB and configure the app framework to trust and read it                       |
| Path-based or header-based routing rules don't apply to HTTPS traffic | Listener is configured for TLS passthrough (pure L4/TCP mode), which cannot see decrypted content    | Switch to TLS termination if L7 routing features are required for that traffic                                     |
| Client TLS certificate (mTLS) isn't visible to the backend           | LB is terminating TLS without forwarding client certificate details, or terminating instead of passing through | Configure the LB to extract and forward client cert info as headers, or switch to passthrough for full mTLS visibility |
| Certificate renewal requires updates across many individual backends | Passthrough architecture, each backend managing its own certificate independently                    | Consider centralizing to termination if per-backend certificate management overhead is unsustainable                |

## 9. Best Practices

- Default to TLS termination at the load balancer for standard HTTP/API workloads, since it enables the L7 features most architectures actually need and centralizes certificate management.
- Use re-encryption (TLS bridging) rather than plain termination whenever the segment between load balancer and backend crosses a trust boundary that isn't fully controlled and isolated.
- Reserve passthrough for cases with a specific, deliberate requirement — mutual TLS validated at the backend, regulatory mandates on private key custody, or non-HTTP protocols where L7 features are irrelevant anyway.

## 10. Common Anti-Patterns / Mistakes

- **Terminating TLS and forwarding plaintext across an untrusted or shared network segment "because it's simpler."** This exposes the entire internal traffic path in plaintext, which is a materially different risk profile than an isolated, single-tenant private subnet.
- **Forgetting `X-Forwarded-Proto` (or equivalent) after enabling termination**, causing subtle, hard-to-diagnose redirect loops and incorrect secure-cookie behavior in the application.
- **Attempting to combine passthrough with Layer 7 routing rules on the same listener.** These are structurally incompatible — a passthrough load balancer cannot inspect content it never decrypts, and misconfigurations attempting this typically fail silently or with confusing errors.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between TLS termination and TLS passthrough at a load balancer?"_
**Model answer:** With TLS termination, the load balancer holds the certificate and private key, decrypts the client's traffic itself, and forwards the request to the backend — either as plain HTTP or re-encrypted with a separate certificate. With TLS passthrough, the load balancer never decrypts anything at all — it just forwards the encrypted bytes through to the backend, which performs the TLS handshake directly with the client itself.
_What the interviewer is probing for:_ Basic recall of the two patterns and where decryption actually happens in each.

**🎯 Intermediate:** _"Why would termination without re-encryption to the backend be considered acceptable in some environments but not others?"_
**Model answer:** Termination without re-encryption means traffic between the load balancer and backend travels in plaintext. That's an acceptable trade-off when that internal network segment is genuinely isolated and trusted — for example, a private subnet with no other tenants and controlled network access, where the risk of a third party intercepting that internal traffic is very low. It becomes unacceptable in a shared, multi-tenant network environment, or under compliance regimes that specifically require encryption in transit end-to-end, where plaintext on any segment — even an internal one — is a real exposure. In those cases, re-encryption (TLS bridging) or full passthrough is the appropriate choice instead.
_What the interviewer is probing for:_ Understanding that "acceptable" here is a risk-based, environment-dependent judgment, not a universal rule.

**🎯 Senior:** _"A team wants to implement mutual TLS (mTLS), where the backend validates a client-presented certificate, but their load balancer currently terminates TLS. What's the issue, and what are the options?"_
**Model answer:** Under standard termination, the load balancer completes the TLS handshake with the client itself, which means it's the one that would see and need to validate any client certificate — the backend, receiving plaintext (or a separately re-encrypted connection) from the load balancer, never sees the original client TLS session at all unless something explicitly extracts and forwards the client certificate details. There are two real options: either configure the load balancer to validate the client certificate itself and forward relevant details (like the certificate's subject or fingerprint) as headers to the backend, trusting the load balancer to have done that validation correctly; or switch that specific traffic to passthrough, letting the backend perform the full TLS handshake — including client certificate validation — directly, at the cost of losing any L7 routing features on that connection. Which is right depends on whether the backend genuinely needs to see and validate the certificate itself, or whether trusting the load balancer's validation and forwarding a summary is sufficient for the security model.
_What the interviewer is probing for:_ Recognition that termination and mTLS have a real interaction that needs deliberate handling, not an assumption that mTLS "just works" transparently through a terminating load balancer.

**🎯 Architect:** _"You're designing ingress for a platform operating under a compliance requirement that mandates encryption in transit for all internal traffic, including between the load balancer and backend services. How do you reconcile this with wanting Layer 7 routing features like path-based routing and a WAF?"_
**Model answer:** TLS bridging (termination with re-encryption) is the pattern that satisfies both requirements simultaneously: the load balancer terminates the client's TLS connection, gaining full L7 visibility to apply path-based routing, WAF rules, and other content-aware features — then immediately re-encrypts before forwarding to the backend over a second, independent TLS connection, satisfying the "encrypted in transit everywhere" mandate. The trade-off is operational: this requires managing certificates on both legs (the public-facing certificate at the load balancer, and internal certificates for every backend, potentially issued by an internal CA rather than a public one, since these certificates never need to be publicly trusted), and it costs a second full TLS handshake and its associated CPU overhead. I'd pair this with an internal certificate authority and automated internal certificate issuance/rotation (rather than manually managing per-backend certificates) to keep the operational overhead of the second TLS leg from becoming unsustainable at scale, and would confirm that terminated Layer 7 processing itself doesn't inadvertently violate the "no plaintext" requirement even momentarily in memory, if the compliance framework is strict about that distinction.
_What the interviewer is probing for:_ The ability to reconcile a compliance constraint with a genuine architectural need (L7 features) using the correct pattern (bridging), plus awareness of the operational cost that pattern introduces.

## 12. Common Misconceptions

1. **"TLS termination means traffic is unencrypted for the rest of its journey."** This is only true for termination *without* re-encryption; TLS bridging re-encrypts for the backend leg, keeping the connection encrypted end-to-end in two separate hops.
2. **"Passthrough is always more secure than termination."** It avoids centralizing the private key at the load balancer, but it also means the load balancer can't provide any content-aware security inspection (WAF, header validation) at all — which pattern is "more secure" depends entirely on what threat is being defended against.
3. **"SNI-based routing decrypts the connection to read the hostname."** SNI is sent in cleartext as part of the initial handshake by design (prior to encrypted-SNI adoption); reading it requires no decryption of the actual TLS session at all.
4. **"Mutual TLS always requires passthrough."** It's possible to terminate and validate the client certificate at the load balancer itself, forwarding relevant details to the backend — passthrough is one valid approach, not the only one.

## 13. 🔑 Key Takeaways

- TLS termination decrypts at the load balancer (enabling L7 features); passthrough forwards encrypted bytes untouched, leaving the backend to handle TLS directly.
- TLS bridging (termination with re-encryption) satisfies both L7 feature requirements and end-to-end encryption mandates, at the cost of a second TLS handshake and certificate management on both legs.
- Certificate management is centralized under termination and distributed under passthrough — a direct operational trade-off.
- SNI-based routing is a hybrid pattern that routes by hostname using only the cleartext SNI field, without decrypting the rest of the session.
- Mutual TLS interacts meaningfully with this choice — it requires either backend-side validation (favoring passthrough) or load-balancer-side validation with forwarded details (compatible with termination).

## 14. Related Concepts & What's Next

[§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) underlies the entire termination/passthrough distinction, since termination is inherently L7-adjacent while passthrough is naturally L4-compatible. Part 8's [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) and [§66](../Part8/Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md) cover TLS handshake mechanics and certificate authority/chain-of-trust concepts this section builds on without re-deriving. [§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md) covers cookie-based session persistence, a feature that — like path-based routing — is only possible once the load balancer has actually terminated TLS and can read the decrypted request.

**Next Section:** [§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md) — `Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md`

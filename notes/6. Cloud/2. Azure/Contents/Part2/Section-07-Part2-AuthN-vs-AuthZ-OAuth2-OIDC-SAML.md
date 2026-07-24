# Section 7 — Authentication vs. Authorization, and Protocol Mechanics

## 7.1 Definition

**Plain language:** Authentication answers "who are you?" — proving your identity, usually with a password, certificate, or biometric factor. Authorization answers "what are you allowed to do?" — a separate decision made _after_ authentication succeeds, based on assigned permissions.

**Precise definition:** Authentication (AuthN) is the process of verifying a claimed identity, resulting in a trusted, verifiable representation of that identity (a token or session). Authorization (AuthZ) is the process of evaluating whether an authenticated identity is permitted to perform a specific action on a specific resource, evaluated separately and after authentication, typically via a policy or role-based mechanism such as Azure RBAC (Section 8).

## 7.2 Why the Distinction Matters

These two concepts are frequently conflated by newcomers but are architecturally and operationally distinct, handled by different systems even though they happen in close sequence. Entra ID (Section 6) is fundamentally an **authentication and identity directory** service — it proves who you are and issues tokens asserting that identity. Azure RBAC (Section 8) and application-level permission systems are **authorization** systems — they decide what an already-authenticated identity is allowed to do. Understanding this separation matters practically: a user can be perfectly, successfully authenticated (Entra ID confirms they are who they claim) and still be denied every single action (because RBAC grants them zero permissions) — these are two independent checkpoints, and troubleshooting an access problem requires figuring out which one is failing.

> 🎯 **Interview Tip:** "The user can log in but can't do anything" is a classic scenario question specifically designed to test whether a candidate understands that successful authentication does not imply any authorization — a very common real interview probe.

## 7.3 OAuth 2.0

**Definition:** OAuth 2.0 is an **authorization framework** (not an authentication protocol on its own) that allows a third-party application to obtain limited, scoped access to resources on behalf of a user, without that application ever handling the user's actual password.

**The problem OAuth 2.0 solves:** Before OAuth, an application wanting to access a user's data on another service (e.g., a scheduling app wanting to read a user's calendar) would typically require the user to hand over their actual username and password for that other service — a serious security risk, since the third-party app would then hold a credential capable of _anything_ the user could do, not just calendar reading, with no ability to revoke that specific access without changing the password entirely. OAuth 2.0 solves this by introducing **tokens**: narrowly-scoped, revocable, time-limited credentials that grant only specific permissions (e.g., "read calendar events" but not "send email"), issued by an authorization server (Entra ID, in Azure's case) after the user explicitly consents.

**Core OAuth 2.0 roles:**

| Role                 | Description                                                                                                  |
| -------------------- | ------------------------------------------------------------------------------------------------------------ |
| Resource Owner       | The user who owns the data/resource being accessed.                                                          |
| Client               | The application requesting access (e.g., a web app wanting to read the user's calendar).                     |
| Authorization Server | The system that authenticates the user and issues tokens — Entra ID, in Azure.                               |
| Resource Server      | The API/service that actually holds the protected data and validates incoming tokens before granting access. |

**Simplified flow (Authorization Code flow, the most common and secure pattern for web apps):**

```
1. User → Client app: "I want to sign in / grant access"
2. Client app → Authorization Server (Entra ID): redirects user to sign in and consent
3. User authenticates with Entra ID (password, MFA, etc.)
4. Entra ID → Client app: returns a short-lived authorization code
5. Client app → Entra ID: exchanges the code (plus its own client secret) for an access token
6. Client app → Resource Server: calls the API, presenting the access token
7. Resource Server: validates the token, grants access to the requested scope only
```

> ⚠️ Exact token lifetimes, specific flow variants (e.g., PKCE requirements for public clients), and default configuration values change over time and by application type — verify current specifics against Microsoft identity platform documentation before relying on exact numbers in production security design.

## 7.4 OpenID Connect (OIDC)

**Definition:** OpenID Connect is a thin **authentication layer built directly on top of OAuth 2.0**. Where OAuth 2.0 alone only proves "this app has been granted access to X," OIDC adds a standardized **ID token** (a JSON Web Token, or JWT) that specifically asserts "this user's identity has been verified," including standardized identity claims like the user's name, email, and unique identifier.

**Why it exists separately from OAuth 2.0:** OAuth 2.0 was originally designed purely for authorization (delegated access), not identity verification — using OAuth alone for "login" purposes led to inconsistent, insecure, ad hoc implementations across different providers before OIDC standardized it. OIDC formalizes "sign in with X" as a specific, secure, interoperable pattern built on OAuth's existing token-exchange machinery, rather than reinventing authentication from scratch.

**In the Azure context:** When a user performs "Sign in with Microsoft," they are going through an OIDC flow against Entra ID as the identity provider — the application receives both an ID token (proving who the user is) and, typically, an access token (authorizing calls to a specific API on the user's behalf), issued together in the same underlying flow.

## 7.5 SAML (Security Assertion Markup Language)

**Definition:** SAML is an older, XML-based protocol for exchanging authentication and authorization data between an identity provider and a service provider, predominantly used for enterprise single sign-on (SSO).

**Why it still matters:** Despite being architecturally older and more verbose (XML-based rather than the JSON-based tokens used by OIDC), SAML remains widely deployed because many established enterprise SaaS applications built their SSO integrations on SAML years before OIDC became dominant, and switching an existing, working enterprise integration carries real migration cost and risk. Entra ID supports acting as a SAML identity provider specifically to support these legacy/enterprise integrations, alongside its native OIDC support for modern applications.

**Comparison — OIDC vs SAML:**

| Aspect              | OpenID Connect (OIDC)                       | SAML                                           |
| ------------------- | ------------------------------------------- | ---------------------------------------------- |
| Data format         | JSON (JWT tokens)                           | XML (SAML assertions)                          |
| Built on            | OAuth 2.0                                   | Its own standard, predates OAuth               |
| Primary use case    | Modern web/mobile apps, APIs                | Enterprise SSO, legacy SaaS                    |
| Typical transport   | HTTP redirects with tokens in URL/POST body | HTTP POST with XML payload                     |
| Mobile-friendliness | Strong                                      | Weaker, generally considered legacy for mobile |

## 7.6 Where RBAC Fits (Preview of Section 8)

Once OIDC/OAuth2 has authenticated a user and issued tokens, **Azure RBAC** is the system that decides what that authenticated identity can actually do to Azure resources specifically (as opposed to application-level permissions, which are typically defined by the application itself using OAuth scopes). This is the authorization layer referenced throughout this section, and is covered in full depth in Section 8 immediately following.

## 7.7 Configuration Example — Registering an App for OIDC Sign-In

```bash
az ad app create --display-name "internal-dashboard-app" \
  --sign-in-audience "AzureADMyOrg" \
  --web-redirect-uris "https://dashboard.contoso.com/auth/callback"
```

- **Purpose:** Registers a new application in Entra ID (Section 6.3.4) configured to support web-based OIDC sign-in, restricted to the organization's own tenant.
- **Important arguments explained individually:**
  - `--sign-in-audience` — controls which identities can sign in: `AzureADMyOrg` restricts to the current tenant only; other values (verify current supported values in documentation) allow multi-tenant or personal Microsoft account sign-in, a significant security-relevant configuration choice.
  - `--web-redirect-uris` — the exact URL(s) Entra ID is allowed to redirect back to after authentication completes; this must exactly match the application's actual callback endpoint, and is a deliberate security control preventing tokens from being redirected to an attacker-controlled URL.
- **Security impact:** Misconfiguring the redirect URI (e.g., allowing wildcard or overly broad redirect URIs) is a well-known real-world vulnerability class that can enable token theft via open-redirect style attacks — redirect URIs should always be as narrowly and exactly specified as possible.

## 7.8 Troubleshooting

| Symptom                                                           | Likely Layer                    | Likely Cause                                                                                                                                      |
| ----------------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| User cannot sign in at all                                        | Authentication (Entra ID)       | Wrong credentials, account disabled, Conditional Access block (Section 10)                                                                        |
| User signs in successfully but sees "Access Denied" on a resource | Authorization (RBAC, Section 8) | No role assignment, or role assigned at wrong scope                                                                                               |
| Application shows "invalid redirect URI" error                    | OAuth2/OIDC configuration       | Redirect URI in the request doesn't exactly match a registered URI on the App Registration                                                        |
| Application receives a token but can't call the target API        | Token scope/audience mismatch   | The requested token's `scope`/`audience` doesn't match what the resource server expects — verify scope configuration on both client and API sides |

## 7.9 Interview Questions — Section 7

### 🎯 Intermediate

**Q: Explain the difference between authentication and authorization using a concrete Azure example.**

_Model answer:_ Authentication is Entra ID verifying that a user really is who they claim to be — for example, validating a password and MFA code during sign-in, resulting in an authenticated session/token. Authorization happens afterward and separately: Azure RBAC checks whether that now-authenticated user has a role assignment granting them permission to, say, start a specific VM. A user can authenticate successfully every time but still receive "Forbidden" errors on every action if they have no RBAC role assignments — this demonstrates the two systems are fully independent checkpoints.

_What the interviewer is probing:_ precise conceptual separation between AuthN and AuthZ, which is foundational to correctly diagnosing access issues in real environments.

### 🎯 Senior

**Q: Why does OpenID Connect exist as a separate standard from OAuth 2.0, rather than just using OAuth 2.0 tokens directly for login?**

_Model answer:_ OAuth 2.0 was designed purely for delegated authorization — granting an application scoped access to a resource — and doesn't natively define a standardized way to assert "this represents a verified human identity" with structured, interoperable identity claims. Early implementations that repurposed plain OAuth access tokens for login purposes were inconsistent and had real security weaknesses, since an access token's presence doesn't inherently prove fresh user authentication occurred or specify who the user actually is in a standard format. OIDC solves this by adding a distinct, purpose-built ID token (a signed JWT with standardized identity claims) alongside OAuth's existing access token machinery, giving applications a secure, standardized, interoperable way to implement "sign in with X" without ambiguity about what the token actually proves.

_What the interviewer is probing:_ whether the candidate understands _why_ a standard exists, not just that it exists — distinguishing genuine protocol-level understanding from surface-level familiarity with buzzwords.

## 7.10 Common Misconceptions

- **"OAuth 2.0 is a login protocol."** Not by itself — OAuth 2.0 is an authorization delegation framework; OpenID Connect is the layer that adds actual authentication/login semantics on top of it.
- **"Once a user authenticates, they can do anything they're able to see in the Portal."** False — visibility in the Portal and actual permission to act are governed by separate RBAC checks (Section 8); a user might see a resource listed but be denied any action on it.

## 7.11 Key Takeaways

- 🔑 Authentication (who are you) and Authorization (what can you do) are separate, sequential checkpoints handled by different systems — Entra ID authenticates, RBAC (and application logic) authorizes.
- 🔑 OAuth 2.0 is an authorization delegation framework using scoped, revocable tokens instead of password sharing; OpenID Connect adds standardized authentication semantics on top of it via ID tokens.
- 🔑 SAML remains relevant for legacy/enterprise SSO integrations despite being architecturally older than OIDC, and Entra ID supports both to serve both modern and legacy application ecosystems.
- 🔑 Redirect URI configuration is a genuine, exploitable security surface — always scope it exactly, never broadly.

## 7.12 Related Concepts (Next Up)

Section 8 covers **Role-Based Access Control (RBAC)** in full depth — the authorization system referenced repeatedly throughout this section, including built-in vs. custom roles, scope, role assignment mechanics, and how RBAC's inheritance model (introduced conceptually in Section 4.4) works in practice.

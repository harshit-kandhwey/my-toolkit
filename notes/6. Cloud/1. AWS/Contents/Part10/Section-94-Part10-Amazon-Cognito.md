# Part 10, Section 6: Amazon Cognito — Identity for Applications

## 1. Definition

**Plain language:** Everything in Part 2's IAM section was about _AWS's own_ identity system — controlling who can call AWS APIs. Cognito is different: it's identity for the _users of your application_ — the people signing up, logging in, and resetting their password on your website or mobile app — who have nothing to do with your AWS account's own IAM users at all.

**Precise definition:** Amazon Cognito is a managed application-identity service providing two distinct capabilities: **User Pools**, a fully managed user directory handling sign-up, sign-in, multi-factor authentication, and issuing standard OAuth 2.0/OIDC tokens (JWTs) for application users; and **Identity Pools**, which exchange an authenticated identity (from a User Pool, a social/enterprise identity provider, or even unauthenticated "guest" access) for temporary, scoped AWS credentials via STS, letting application users securely access AWS resources directly.

## 2. Why It Exists / Problem It Solves

Part 2's IAM model is built around a fundamentally different problem than most applications actually have: IAM users, roles, and policies are for controlling access to _AWS itself_ — engineers, services, and automation calling AWS APIs. But a consumer-facing web or mobile application has a completely different identity problem: it needs to let potentially millions of _end users_ — people who have no AWS account, no IAM presence, and shouldn't need either — sign up, log in, verify their email, reset a forgotten password, and optionally use MFA, all through a secure, standards-compliant authentication flow that the application itself shouldn't have to build and maintain from scratch (password hashing, secure token issuance, MFA delivery, and all of the security-critical detail that goes with a home-built authentication system are exactly the kind of "undifferentiated heavy lifting" the Well-Architected Performance Efficiency pillar, [§89](./Section-89-Part10-WellArchitected-Framework.md), argues against building yourself).

Cognito solves this with User Pools as a fully managed, standards-based (OAuth 2.0/OpenID Connect) user directory and authentication service — and, since some applications also need their end users to directly and securely access specific AWS resources (uploading a photo directly to S3 from a mobile app, for example), Identity Pools solve the second, related problem of converting "this user is authenticated" into "this user has temporary, appropriately scoped AWS credentials."

## 3. Prerequisites and Dependencies

- **IAM** ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)): Identity Pools issue temporary credentials via STS by assuming an IAM role — directly building on the role/trust-policy model from Part 2, but for application end users rather than AWS principals.
- **API Gateway** (a Part 4 topic): commonly integrates directly with Cognito User Pools as an authorizer, validating a user's JWT before allowing an API call through.
- General familiarity with OAuth 2.0/OpenID Connect concepts is helpful but not assumed.

## 4. Internal Working

### User Pools

- A User Pool is a managed **user directory** — it stores user records (with configurable required/custom attributes), handles the actual sign-up and sign-in flows, sends verification emails/SMS, manages password policies and reset flows, and supports **MFA** (SMS or TOTP-based authenticator apps).
- On successful authentication, a User Pool issues three **JSON Web Tokens (JWTs)**: an **ID token** (contains the user's identity claims — who they are), an **access token** (used to authorize API calls, scoped to what the user is permitted to do), and a **refresh token** (used to obtain new ID/access tokens without requiring the user to log in again, until the refresh token itself expires).
- User Pools support **federation** — allowing sign-in via external identity providers (Google, Facebook, Apple, or an enterprise SAML/OIDC provider) in addition to (or instead of) Cognito's own native username/password directory, presenting a unified token to the application regardless of which underlying provider the user actually authenticated through.

### Identity Pools

- An Identity Pool takes an already-authenticated identity — from a Cognito User Pool, a supported social/enterprise provider, or even an unauthenticated guest — and **exchanges it for temporary AWS credentials** via AWS STS (the same token-vending mechanism underlying IAM role assumption, [§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)), by mapping the identity to a specific IAM role.
- Critically, Identity Pools support **role mapping rules**, allowing different authenticated users to be granted different IAM roles (and therefore different AWS permissions) based on attributes of their identity — for example, users in a "premium" user group getting a role with broader S3 access than users in a "free" tier.
- This is the mechanism that lets a mobile app's end user **directly and securely upload a file to a specific S3 prefix**, or **write directly to a specific DynamoDB table row scoped to their own user ID**, without the application's own backend needing to proxy every such request — genuinely useful for reducing backend load and latency for exactly this class of user-scoped, direct-to-AWS-resource access pattern.

```
End User ──▶ Cognito User Pool (sign-up/sign-in, MFA, federation)
                     │
              JWT (ID token, access token, refresh token)
                     │
        ┌────────────┴────────────┐
        ▼                          ▼
API Gateway Authorizer      Cognito Identity Pool
(validates JWT before        (exchanges JWT for temporary
 allowing API call)           AWS credentials via STS,
                               scoped by IAM role mapping)
                                      │
                                      ▼
                          Direct, scoped access to
                          S3 / DynamoDB / other AWS services
```

## 5. Architecture & Components

| Component                              | Explanation                                                                                                                                          |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **User Pool**                          | The managed user directory — sign-up/sign-in, MFA, password policy, federation, JWT issuance.                                                        |
| **App Client**                         | A specific application's registered connection to a User Pool, with its own configuration (which auth flows are allowed, token expiration settings). |
| **Identity Pool**                      | Exchanges an authenticated (or guest) identity for temporary AWS credentials via STS and IAM role mapping.                                           |
| **JWT (ID/Access/Refresh Token)**      | The three tokens issued on successful User Pool authentication, each serving a distinct purpose.                                                     |
| **Identity Provider (IdP) Federation** | Allows sign-in via Google, Facebook, Apple, SAML, or OIDC providers, unified behind Cognito's own token issuance.                                    |
| **Role Mapping Rule**                  | Identity Pool configuration determining which IAM role a given authenticated identity (or attribute of that identity) receives.                      |

## 6. Lifecycle / Workflow

1. **Create a User Pool**, configuring required attributes, password policy, MFA settings, and any federated identity providers.
2. **Register an App Client** for your specific application (web, mobile, or backend service) against the User Pool.
3. An **end user signs up or signs in** through the application, which calls the User Pool's authentication APIs (or uses a hosted UI Cognito provides).
4. On success, the User Pool **issues JWTs** to the application.
5. The application uses the **access token** to authenticate API calls (commonly validated by an API Gateway Cognito authorizer), and/or exchanges the token via an **Identity Pool** for temporary AWS credentials if the user needs direct AWS resource access.
6. **Refresh tokens** allow the application to obtain new tokens without re-prompting the user to log in, until the refresh token's own expiration.

## 7. Configuration

| Setting                                   | Purpose                                                                                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Password policy / MFA configuration       | Security posture for the user directory                                                                                                                |
| App Client allowed auth flows             | Which authentication flows (e.g., username/password, refresh-token, custom) this specific application is permitted to use                              |
| Token expiration (ID/access/refresh)      | Balances user convenience (longer-lived tokens, fewer re-logins) against security exposure (shorter-lived tokens limit a stolen token's window of use) |
| Identity Pool role mapping rules          | Determines which IAM role (and therefore AWS permissions) an authenticated user receives                                                               |
| Federated identity provider configuration | Connects external IdPs (Google, SAML, etc.) to the User Pool                                                                                           |

⚠️ **Warning:** Identity Pool role mapping is a genuine, direct security boundary — a role mapping rule that's too permissive (e.g., every authenticated user getting a role with broad S3 access rather than access scoped to just their own user-prefixed objects) can let one user access another user's data; role mapping should be designed with the same least-privilege discipline as any other IAM role ([§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)), commonly using policy variables (like `${cognito-identity.amazonaws.com:sub}`) to scope permissions dynamically to each specific user's own identity.

## 8. Interview Questions with Model Answers

**🎯 Junior:** _"What's the difference between a Cognito User Pool and an Identity Pool?"_
**Model answer:** A User Pool is a managed user directory — it handles sign-up, sign-in, password resets, MFA, and issues JWTs proving who a user is. An Identity Pool is a separate capability that takes an already-authenticated identity, whether from a User Pool or another provider, and exchanges it for temporary AWS credentials, so the application's end user can directly access specific AWS resources like S3 or DynamoDB. You'd use a User Pool any time you need user authentication for your application; you'd add an Identity Pool specifically when your application's end users also need to directly interact with AWS resources, not just authenticate.

**🎯 Intermediate:** _"Why is Identity Pool role mapping described as a genuine security risk if done carelessly?"_
**Model answer:** Because the IAM role a user receives through an Identity Pool determines exactly what AWS resources and actions that user can perform directly, so a role mapping that's too broad — every user getting the same permissive role rather than permissions scoped specifically to their own data — could let one authenticated user read or modify another user's resources, which is a real, serious security and privacy failure. The fix is designing role mapping with least privilege in mind, commonly using policy variables that reference the specific authenticated user's own identity, so an IAM policy can dynamically scope an S3 or DynamoDB permission to only that user's own prefix or partition key, rather than granting broad access that happens to work correctly only because the application's own code is well-behaved.

**🎯 Senior:** _"A mobile app team wants users to upload photos directly to S3 from their phones rather than routing uploads through a backend API. Walk through how you'd design this securely with Cognito."_
**Model answer:** I'd set up a Cognito User Pool for authentication, and an Identity Pool that exchanges the authenticated user's token for temporary AWS credentials scoped to a specific IAM role. That role's policy would grant `s3:PutObject` permission, but critically, scoped to a specific S3 key prefix incorporating the authenticated user's own Cognito identity ID as a policy variable — something like allowing writes only to `photos/${cognito-identity.amazonaws.com:sub}/*` — so each user's temporary credentials only ever let them write into their own dedicated prefix, never another user's. This avoids the app needing to proxy every upload through a backend API (reducing backend load and upload latency) while still maintaining genuine per-user data isolation through the IAM policy itself, rather than relying on the mobile app's own client-side logic to "behave correctly," which wouldn't be a real security boundary since a malicious or modified client could ignore that logic entirely.

**🎯 Architect:** _"Design an authentication architecture for a B2B SaaS platform where each customer organization needs to use their own existing enterprise identity provider (their own SSO) rather than creating new Cognito-native accounts for every employee."_
**Model answer:** I'd configure the Cognito User Pool with SAML or OIDC federation, connecting to each customer organization's existing enterprise identity provider, so their employees authenticate through their own company's SSO rather than through a Cognito-native username/password flow — this is precisely the multi-tenant federation use case Cognito's IdP federation capability is designed for. I'd design the User Pool (or potentially multiple pools, depending on how strictly each customer organization's user base needs to be isolated from others) to map incoming SAML/OIDC claims from each customer's IdP into consistent Cognito user attributes, including an attribute identifying which customer organization the user belongs to, so downstream authorization logic (both in application code and in any Identity Pool role mapping) can correctly scope what each user can access based on their organization, not just their individual identity. This gives each B2B customer the SSO experience their own security policies likely require, without the platform needing to build and separately maintain a custom SSO integration per customer — Cognito's federation handles the protocol-level integration work generically across all of them.

## 9. Common Misconceptions

- "Cognito User Pools and IAM users are basically the same thing." False — IAM users are for AWS's own access control (engineers, automation calling AWS APIs); Cognito User Pools are for your application's own end users, who typically have no AWS presence or awareness at all.
- "You always need both a User Pool and an Identity Pool." False — many applications only need a User Pool for authentication and pass the resulting JWT to their own backend (validated via API Gateway or application code); Identity Pools are specifically needed only when end users must directly access AWS resources.

## 10. Key Takeaways

🔑 Cognito User Pools handle end-user authentication (sign-up, sign-in, MFA, federation) and issue standards-based JWTs — a fundamentally different identity system from IAM's AWS-access-control model.
🔑 Cognito Identity Pools exchange an authenticated identity for temporary AWS credentials via STS and IAM role mapping, enabling direct, secure end-user access to AWS resources.
🔑 Identity Pool role mapping is a genuine security boundary requiring least-privilege design, commonly using policy variables to scope permissions to each user's own identity.
🔑 Federation lets Cognito unify sign-in across native accounts, social providers, and enterprise SAML/OIDC IdPs behind one consistent token-issuance model — valuable for both consumer and B2B multi-tenant SSO scenarios.
🔑 Not every application needs an Identity Pool — only those where end users need direct, scoped access to AWS resources beyond simple backend-mediated authentication.

## 11. Related Concepts

- **IAM** (the role/trust-policy/STS model Identity Pools directly build on) → [§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md).
- **API Gateway** (commonly integrates with User Pools as a request authorizer) — a Part 4 topic.
- **S3** (a common direct-access target for Identity Pool-issued credentials) → Part 5.
- **Neptune & Graph ML Tie-In** (the next section, a different specialized-service deep dive) → next section, [§95](./Section-95-Part10-Neptune-GraphML.md).

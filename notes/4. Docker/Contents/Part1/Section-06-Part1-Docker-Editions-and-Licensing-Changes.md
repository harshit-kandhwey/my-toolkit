# Section 6 (Part 1): Docker Editions and Licensing Changes

## 1. Definition

**Plain language:** "Docker" is several products with different licenses. The core engine is open source and free to use anywhere. Docker Desktop, the convenient laptop app, is free for small companies, individuals, education, and open-source work, but requires a paid subscription for larger organizations. Over the years Docker has also renamed and reshuffled its editions, which makes older articles confusing.

**Precise definition:** The **Docker Engine** (moby-derived daemon and CLI) is released under the Apache 2.0 license. **Docker Desktop** is proprietary software under the Docker Subscription Service Agreement; since the terms took effect in 2021-2022, commercial use in a company with more than 250 employees or more than US$10 million in annual revenue requires a paid subscription (Pro, Team, or Business tiers, with Personal free for the exempt categories). **Docker Enterprise** was sold to Mirantis in November 2019 and continues as Mirantis Container Runtime and related products. The **Moby** project (2017) is the upstream open-source project from which Docker Engine is assembled.

> 💡 **Tip:** Licensing risk attaches to the product you install, not to the word "Docker". Engine on a Linux server and Desktop on a laptop are governed by different terms.

## 2. Why This Matters

- **Compliance exposure.** Larger companies using Desktop without a subscription are out of compliance, and audits and vendor questionnaires ask about it.
- **Tooling decisions.** Licensing shaped the market for alternatives (Podman Desktop, Rancher Desktop, Colima, Lima, OrbStack), covered in [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md).
- **Reading old material correctly.** "Docker CE", "Docker EE", "Docker Enterprise", and "Docker Engine - Community" refer to eras and names that no longer map one-to-one to today's products.
- **Budgeting.** Subscription tiers add cost per developer seat; knowing which features matter (SSO, image access management, Scout, registry controls) avoids overspending or under-buying.
- **Supply chain and registry policy.** Docker Hub terms and pull rate limits affect CI design ([§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) and later registry topics).

## 3. Prerequisites and Dependencies

Assumes the difference between Engine and Desktop from [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) and the company and open-source lineage in [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) (dotCloud, Docker Inc., Moby, OCI). Alternatives that sidestep Desktop licensing are compared in [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md). The certification path, which also references editions, is in [§7](Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md). This section is factual and policy-oriented; always confirm current terms and pricing on Docker's official pricing and legal pages, since they change.

## 4. Architecture / Conceptual Diagram

```text
                        "Docker" product map (conceptual)

  Upstream open source                 Distributions
  ┌───────────────────┐    ┌────────────────────────────────────────────┐
  │ Moby project      │───►│ Docker Engine (Apache 2.0, free everywhere)│
  │ (2017 upstream)   │    │  - Linux packages: docker-ce (apt/yum)     │
  └───────────────────┘    └────────────────────────────────────────────┘
          │                 ┌────────────────────────────────────────────┐
          └────────────────►│ Docker Desktop (proprietary)               │
                            │  Engine + VM + GUI + extensions            │
                            │  ┌───────────┬────────────────────────┐    │
                            │  │ Free      │ Paid                   │    │
                            │  │ Personal, │ Pro / Team / Business  │    │
                            │  │ education,│ >250 employees OR      │    │
                            │  │ OSS, small│ >$10M revenue = paid   │    │
                            │  └───────────┴────────────────────────┘    │
                            └────────────────────────────────────────────┘
  Enterprise line (sold 2019) ──► Mirantis Container Runtime
```

- **The engine is the free path**; Desktop is where the licensing rules apply.
- **The threshold is an "OR"**: exceeding either the headcount or the revenue limit triggers the paid requirement.
- **Enterprise features moved companies**: the former Docker Enterprise product line lives on under Mirantis, not Docker Inc.

## 5. Hands-On

### 5.1 Identifying What Is Installed and Which Terms Apply

**Purpose:** Determine whether a machine is running Desktop or a standalone Engine.

```bash
docker version
docker info --format 'Name: {{.Name}}  OS: {{.OperatingSystem}}'
docker context ls
```

```bash
$ docker info --format 'Name: {{.Name}}  OS: {{.OperatingSystem}}'
Name: docker-desktop  OS: Docker Desktop

$ docker info --format 'Name: {{.Name}}  OS: {{.OperatingSystem}}'
Name: build-01  OS: Ubuntu 24.04.1 LTS
```

**Production usage example:** Asset inventories and license audits distinguish Desktop installs (subscription-relevant) from server Engine installs (not).

**Common errors:** Assuming `OS: Docker Desktop` on a Linux laptop is Engine; it is Docker Desktop for Linux and follows Desktop terms.

### 5.2 Checking the Engine Package Source and License

**Purpose:** Confirm you have the official, Apache-2.0 Engine packages.

```bash
apt-cache policy docker-ce | head -5
dpkg -s docker-ce | grep -E "^(Package|Version|Maintainer)"
```

```bash
$ apt-cache policy docker-ce | head -3
docker-ce:
  Installed: 5:28.0.1-1~ubuntu.24.04~noble
  Candidate: 5:28.0.1-1~ubuntu.24.04~noble
$ dpkg -s docker-ce | grep -E "^(Package|Version|Maintainer)"
Package: docker-ce
Maintainer: Docker <support@docker.com>
Version: 5:28.0.1-1~ubuntu.24.04~noble
```

**Production usage example:** Fleet compliance scripts collect package name, version, and source repo to show only Engine (not Desktop) is deployed on servers.

**Common errors:** Old references to `docker-ee` packages point to the discontinued Docker Enterprise line; those repositories are no longer Docker Inc.'s.

### 5.3 Inspecting Registry Rate-Limit Status

**Purpose:** Registry usage terms also changed (pull rate limits for Docker Hub, introduced in late 2020); check how many pulls remain for your identity.

```bash
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep -i ratelimit
```

```bash
ratelimit-limit: 100;w=21600
ratelimit-remaining: 100;w=21600
```

**Production usage example:** CI fleets behind one NAT address share an anonymous quota; authenticating pulls or using a pull-through cache avoids build failures.

**Common errors:** `toomanyrequests: You have reached your pull rate limit` in CI logs. Limits and tiers change, so verify current values in Docker's documentation.

## 6. Production Usage Notes

- **Servers use Engine; developers use Desktop or an alternative.** Keep this split explicit in policy.
- **Track seat counts for Desktop** and decide per company whether a subscription or an alternative runtime is cheaper and acceptable.
- **Use a pull-through registry cache or mirror** for CI so licensing and rate-limit changes at the public registry do not break builds.
- **Pin official-repository Engine versions** and do not depend on the "convenience" of Desktop's bundled Engine version for server parity.
- **Re-check terms periodically.** Pricing, tier names, and included features have changed multiple times.

## 7. Security Considerations

- **Paid tiers bundle governance features**, such as SSO, SCIM, Registry Access Management, and Image Access Management, that restrict what developers can pull, which is a supply-chain control.
- **Registry Access Management** can limit Desktop users to approved registries, reducing exposure to typosquatted or malicious images.
- **Unofficial "free Docker" builds and mirrors** are a supply-chain risk; install only from official repositories.
- **Vulnerability scanning products** (such as Docker Scout) are tied to plans and account settings; verify that scanning coverage is enabled for the images you actually ship.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Audit flags Desktop installs in a large company | No subscription assigned | Purchase seats, or migrate developers to an approved alternative |
| Old tutorial says `apt install docker-ee` | Discontinued Enterprise packages | Use `docker-ce` from the official repo, or the Mirantis product if contracted |
| CI fails with `toomanyrequests` | Anonymous or shared-NAT pull quota exhausted | Authenticate pulls; add a pull-through cache |
| Confusion over "CE" versus "Engine" naming | Renamed in 2019-2020 | Treat docker-ce packages as Docker Engine (Community) |
| Desktop prompts for sign-in or plan | Organization enforces sign-in | Sign in with the corporate account or follow IT policy |

## 9. Best Practices

- Document which runtime each environment uses and why, tied to license terms.
- Keep a written decision on Desktop licensing versus alternatives, with an owner and a review date.
- Prefer Engine on servers; it is free, scriptable, and matches production.
- Mirror or cache base images internally to reduce dependency on public registry quotas.
- Read the current subscription agreement before large rollouts; do not rely on memory or old blog posts.

## 10. Common Anti-Patterns / Mistakes

- **Assuming "Docker is open source, so everything is free."** Desktop is not.
- **Ignoring thresholds until an audit** and then scrambling for seats.
- **Relying on anonymous pulls in CI** at scale.
- **Following pre-2020 guides** that reference Docker Enterprise or "Docker CE" editions as current.
- **Migrating tools solely for cost** without validating compatibility (compose behavior, socket paths, networking) with your workflows.

## 11. Interview Questions

**🎯 Beginner:** _"Is Docker free to use?"_
**Model answer:** Docker Engine is open source under Apache 2.0 and free. Docker Desktop is free for personal use, education, open-source projects, and small businesses, but companies with more than 250 employees or over US$10 million in annual revenue need a paid subscription.
_What the interviewer is probing for:_ Distinguishing Engine from Desktop.

**🎯 Intermediate:** _"What happened to Docker Enterprise Edition?"_
**Model answer:** Docker sold its Enterprise business to Mirantis in November 2019. Docker Inc. refocused on developer tooling (Desktop, Hub, Build, Scout), while Mirantis continues the enterprise runtime and platform as Mirantis Container Runtime. The community packages are now just called Docker Engine.
_What the interviewer is probing for:_ Historical awareness that prevents confusion with outdated docs.

**🎯 Senior:** _"Your company just crossed 300 employees and developers use Docker Desktop. What are your options?"_
**Model answer:** Buy Docker subscriptions for affected seats, using the governance features (SSO, registry controls) as added value; or move to alternatives such as Podman Desktop, Rancher Desktop, Colima, or Lima with Engine or containerd behind them. I would pilot the alternative on a team, checking Compose, bind mounts, socket-dependent tooling, and Kubernetes integration, then compare total cost of migration and support against seat cost.
_What the interviewer is probing for:_ Practical trade-off analysis rather than reflexive answers.

**🎯 Architect:** _"How do you design container tooling policy so licensing or registry-terms changes do not disrupt delivery?"_
**Model answer:** Standardize on OCI images and standard build interfaces so any conformant runtime works; keep servers on Engine or containerd; run an internal registry with pull-through caching and pinned base images; separate developer tooling choice from production runtime; and review vendor terms on a schedule. The OCI standards ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)) are what make this portability real.
_What the interviewer is probing for:_ Vendor-risk thinking anchored in open standards.

## 12. Common Misconceptions

1. **"Docker Engine requires a paid license for companies."** It does not; Desktop does under the stated thresholds.
2. **"Docker Enterprise is still a Docker Inc. product."** It moved to Mirantis in 2019.
3. **"The threshold is employees AND revenue."** It is either condition.
4. **"Using Desktop on Linux avoids the license."** Docker Desktop for Linux is covered by the same Desktop terms.

## 13. 🔑 Key Takeaways

- Engine is Apache 2.0; Desktop is proprietary with a paid requirement above 250 employees or US$10 million revenue.
- Docker Enterprise moved to Mirantis in 2019; "CE" names are historical.
- Licensing drove interest in Desktop alternatives and in registry mirroring.
- Governance features in paid plans can be real security controls.
- Verify current terms and pricing at the source before deciding.

## 14. Related Concepts & What's Next

[§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) compares Docker with Podman, LXC, rkt, and standalone containerd, which are the practical alternatives raised by licensing. [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) covers the install paths whose licensing consequences are discussed here, and [§7](Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md) introduces the DCA certification landscape, whose exam blueprint has also tracked product changes. [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) provides the historical background for Moby and Docker Inc.'s restructuring. Later Parts cover registries, pull-through caches, and image scanning in detail.

**Next Section:** [§7](Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md) — `Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md`

# Section 105 (Part 14): Automated Testing Pyramids for IaC

## 1. Definition

**Plain language:** This Part has covered several distinct testing techniques — formatting checks, `validate`, plan-based assertions, Terratest/`terraform test`, policy engines, CI pipelines, GitOps gating, pre-commit linting — largely one at a time. This final section pulls them together into a single coherent shape: which checks should run constantly and cheaply, which should run less often because they're more expensive, and how that shape mirrors (while also meaningfully differing from) the classic software testing pyramid.

**Precise definition:** An **automated testing pyramid for Infrastructure as Code** is a layered testing strategy where the number of checks and frequency of execution decreases as cost, execution time, and blast radius increase moving up the pyramid: a wide base of **static/local checks** (formatting, linting, `terraform validate`) that run on every keystroke or commit at near-zero cost; a middle layer of **plan-based tests** ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md), native `terraform test` in `command = plan` mode) that run on every PR without touching real infrastructure; a narrower layer of **integration tests** (Terratest, `terraform test` in `command = apply` mode, [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) that apply real, disposable infrastructure and are run less frequently (module-source changes, scheduled) due to cost and time; and a thin top layer of **policy/compliance and manual/exploratory validation** (Sentinel/OPA in CI, [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md), plus manual review of genuinely novel or high-risk changes) applied selectively to the highest-risk changes. Unlike the traditional software testing pyramid — where the base is unit tests of pure functions with no I/O — IaC's base layer necessarily includes checks against a _declared schema of real external systems_ (the provider schema `validate` checks against), because Terraform configuration has no meaningful "pure function" layer entirely detached from the infrastructure it describes.

> 💡 **Tip:** The pyramid shape isn't a stylistic preference — it's a direct consequence of cost asymmetry. A `terraform fmt -check` run costs milliseconds and zero dollars; a real Terratest apply-and-destroy cycle costs minutes and real cloud spend. If your testing strategy inverts this — running expensive integration tests on every commit while treating linting as optional — you'll either bankrupt your CI budget or, more likely, teams will quietly disable the expensive tests out of frustration, leaving you with less coverage than a correctly-shaped pyramid would have given you for the same budget.

## 2. Why This Matters

- **Makes the trade-offs in this entire Part legible as one coherent strategy**, rather than a grab-bag of unrelated tools — the question "should this specific check run on every commit or only nightly" has a principled answer once the pyramid shape is explicit.
- **Prevents both under-testing and wasteful over-testing.** A team with no pyramid thinking either skips expensive-but-valuable integration tests entirely (under-testing, missing real provider-behavior bugs) or runs them on every trivial commit (over-testing, burning CI budget and cloud spend on redundant coverage).
- **Aligns test cost with the actual risk being mitigated.** Cheap, frequent checks (fmt, validate, plan-based) catch the highest-volume, lowest-severity mistakes (typos, obviously wrong values); expensive, infrequent checks (integration tests, policy gates) are reserved for the lower-volume, higher-severity risks (real provider misbehavior, organizational compliance) where the cost is justified.
- **Gives new team members and auditors a mental model for "is our Terraform testing actually adequate."** A team can look at their pyramid shape and immediately identify gaps — e.g., "we have a solid base but nothing above plan-based testing" is a legible, actionable finding.
- **Directly informs CI pipeline design ([§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) and GitOps gating ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)).** Which checks are required-and-blocking versus advisory-and-scheduled is exactly the pyramid's layering decision, made concrete in pipeline configuration.

## 3. Prerequisites and Dependencies

This section is explicitly a synthesis of every prior section in Part 14: [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) (validate and plan-based testing forms the pyramid's base and middle layers), [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md) (Terratest/native `terraform test` forms the integration layer), [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) (Sentinel/OPA forms part of the top layer), [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)–[§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) (CI/GitOps determine when and how each layer actually executes), and [§104](./Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) (pre-commit/tflint forms the earliest, cheapest part of the base). No new tooling is introduced here — this section is purely about the strategic shape those tools should collectively take.

## 4. Architecture / Conceptual Diagram

```text
                              ▲
                             ╱ ╲
                            ╱   ╲     TOP: Policy / Compliance / Manual Review
                           ╱     ╲    - Sentinel/OPA hard-mandatory gates (§101)
                          ╱───────╲   - Manual review of high-risk/novel changes
                         ╱         ╲  Runs on: every PR (policy), selectively (manual)
                        ╱           ╲ Cost: low (policy) to high (manual reviewer time)
                       ╱─────────────╲
                      ╱               ╲   MIDDLE-UPPER: Integration Tests
                     ╱                 ╲  - Terratest / terraform test (command=apply) (§100)
                    ╱                   ╲ Runs on: module-source changes, nightly/scheduled
                   ╱─────────────────────╲ Cost: minutes + real cloud spend
                  ╱                       ╲
                 ╱                         ╲  MIDDLE: Plan-Based Tests
                ╱                           ╲ - terraform plan -detailed-exitcode (§99)
               ╱                             ╲- terraform test (command=plan) (§100)
              ╱───────────────────────────────╲ Runs on: every PR
             ╱                                 ╲ Cost: seconds, no real infra created
            ╱                                   ╲
           ╱─────────────────────────────────────╲  BASE: Static / Local Checks
          ╱                                       ╲ - terraform fmt -check, validate (§99)
         ╱                                         ╲- tflint, pre-commit hooks (§104)
        ╱───────────────────────────────────────────╲ Runs on: every keystroke/commit
                                                        Cost: milliseconds, zero infra
```

- Width at each layer roughly represents both "how many checks live here" and "how often they run" — both shrink moving up, cost and blast-radius awareness both grow.
- Every check in this diagram was introduced individually earlier in this Part; the pyramid is a claim about _relative frequency and required-ness_, not a claim that any of these tools are individually new.
- The "manual review" element at the very top is deliberately included and not automatable — some risk (a genuinely novel architectural change, an unusually high-blast-radius production change) still warrants human judgment no policy engine or test suite substitutes for.

## 5. Hands-On

### 5.1 Mapping Pyramid Layers to CI Trigger Frequency

**Purpose:** Show concretely how pyramid layering translates into which CI jobs run on which trigger, tying the abstract shape to real pipeline configuration.

**Syntax:**

```yaml
# .github/workflows — three separate workflows, one per pyramid tier's trigger cadence
# 1) base + middle layers: every PR
on:
  pull_request:
    paths: ["**.tf"]
# runs: fmt -check, validate, tflint, plan -detailed-exitcode, terraform test (plan-mode)

# 2) integration layer: module-source changes only
on:
  pull_request:
    paths: ["modules/**"]
# runs: Terratest / terraform test (apply-mode) against a disposable test account

# 3) integration layer, broader safety net: nightly schedule
on:
  schedule:
    - cron: "0 3 * * *"
# runs: full Terratest suite against every published module version, catching
# drift in the modules caused by upstream provider changes, not just code changes
```

**Example usage and expected output:**

```text
$ gh run list --workflow=terraform-plan.yml --limit 3
completed  success  PR #201  fmt/validate/tflint/plan       48s
completed  success  PR #200  fmt/validate/tflint/plan       51s
completed  success  PR #199  fmt/validate/tflint/plan       44s

$ gh run list --workflow=terratest-nightly.yml --limit 1
completed  success  scheduled  Terratest full module suite   18m32s
```

**Production usage example:** The dramatic time difference (48 seconds for every PR vs. 18 minutes nightly) is the pyramid made visible in actual CI run history — it's direct evidence the cost/frequency trade-off is being respected rather than every check running on every trigger indiscriminately.

**Common errors:** Configuring the integration-test workflow to trigger on `pull_request` for _every_ `.tf` file change (not scoped to `modules/**`) is a common mistake that inverts the pyramid — every trivial root-module change now pays the cost of a full apply-based integration test suite, defeating the purpose of tiering by trigger.

### 5.2 A Minimal Pyramid Health-Check Script

**Purpose:** Give a team a concrete, auditable way to answer "is our testing pyramid actually shaped correctly," rather than relying on impression.

**Syntax:**

```bash
#!/usr/bin/env bash
# pyramid_audit.sh — reports presence and trigger scope of each layer
echo "Base layer (fmt/validate/lint):"
[ -f .pre-commit-config.yaml ] && echo "  pre-commit config: present" || echo "  MISSING"

echo "Middle layer (plan-based):"
grep -rl "detailed-exitcode" .github/workflows/ >/dev/null \
  && echo "  plan-based CI check: present" || echo "  MISSING"

echo "Integration layer (apply-based):"
find . -name "*.tftest.hcl" -o -name "*_test.go" | grep -q . \
  && echo "  test files found" || echo "  MISSING — no apply-based tests exist"

echo "Policy layer:"
[ -d policies/ ] && echo "  policy directory: present" || echo "  MISSING"
```

**Example usage and expected output:**

```bash
$ ./pyramid_audit.sh
Base layer (fmt/validate/lint):
  pre-commit config: present
Middle layer (plan-based):
  plan-based CI check: present
Integration layer (apply-based):
  MISSING — no apply-based tests exist
Policy layer:
  MISSING
```

**Production usage example:** Running an audit like this across an organization's Terraform repositories surfaces exactly which repos have only the base/middle layers (common — they're the cheapest to adopt) versus which have made the further investment in integration tests and policy gates, informing where to prioritize testing-maturity investment.

**Common errors:** Treating "some file matching `*_test.go` exists" as proof the integration layer is adequate, without checking whether those tests are actually wired into a CI trigger — a test file that exists but never runs anywhere provides zero actual coverage, a subtle but common false-positive in pyramid audits like this one.

### 5.3 A `terraform test` File Deliberately Spanning Two Pyramid Layers

**Purpose:** Show how the native `terraform test` framework itself can express both a plan-only (middle-layer) and apply-based (integration-layer) check in one file, illustrating that the pyramid is about cost/frequency intent, not necessarily separate tooling per layer.

**Syntax:**

```hcl
# tests/tiered.tftest.hcl
run "cheap_plan_check" {
  command = plan   # middle layer: runs on every PR, no real infra

  assert {
    condition     = length(aws_subnet.public) == 3
    error_message = "Expected exactly 3 public subnets"
  }
}

run "expensive_apply_check" {
  command = apply  # integration layer: only run in the nightly workflow

  assert {
    condition     = can(http.get("https://${aws_lb.app.dns_name}"))
    error_message = "Load balancer did not respond after real apply"
  }
}
```

**Example usage and expected output:**

```bash
# PR pipeline: runs only the plan-mode run block via test filtering
$ terraform test -filter=tests/tiered.tftest.hcl -test.run=cheap_plan_check

# Nightly pipeline: runs the full file, including the apply-mode block
$ terraform test tests/tiered.tftest.hcl
```

**Production usage example:** Teams that want a single test file per module (rather than physically separate plan-only and apply-only files) use this pattern — the pyramid tiering lives in _which CI trigger invokes which `run` block_, not in which files exist on disk.

**Common errors:** Not separating cheap and expensive `run` blocks at all, and running the whole file on every PR, silently collapses the pyramid into "everything is integration-tier cost," which is the exact inversion this section warns against.

## 6. Production Usage Notes

- **The pyramid shape is a starting heuristic, not a rigid rule.** A genuinely high-risk module (one managing IAM policies or network security boundaries, say) may justify a wider integration-test layer than a low-risk one — pyramid _shape_ should track actual risk, not be applied uniformly regardless of blast radius.
- **Coverage gaps tend to appear at the top, not the bottom.** Base-layer checks (fmt, validate, lint) are cheap enough that most teams adopt them quickly; integration tests and policy gates require more deliberate investment and are where most organizations' actual testing maturity gaps live — the audit pattern in §5.2 exists specifically to surface this.
- **A pyramid inverted into an "ice cream cone" (heavy manual/integration testing, thin automated base) is a known anti-pattern borrowed directly from the general software testing literature** — it applies to IaC exactly as much as it does to application code, and for the same underlying reason: expensive, slow checks run rarely mean regressions linger uncaught far longer than a cheap, frequent base layer would allow.

## 7. Security Considerations

- The top policy layer ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) is frequently the only layer that checks organizational security rules explicitly (encryption requirements, public-access restrictions) — a pyramid with a thin or missing top layer has a real, not just theoretical, security coverage gap, distinct from correctness coverage.
- Integration tests that apply real infrastructure inherit all the credential and blast-radius considerations from [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md) and [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) — a testing pyramid's integration layer is itself part of the security surface that needs least-privilege scoping, not just a coverage-maximizing convenience.
- A well-shaped pyramid indirectly improves security posture by catching misconfigurations early and cheaply, before they ever reach a real, higher-stakes apply — this is a genuine, if secondary, security benefit of correct pyramid design, not just a velocity optimization.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                           | Likely Cause                                                                                                                     | Resolution Path                                                                                                          |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| CI costs and pipeline duration have grown sharply as the repo scaled              | Integration/apply-based tests running on every PR instead of being scoped to module changes or a scheduled cadence               | Audit trigger scoping per layer (§5.1 pattern); move apply-based tests to a narrower trigger                             |
| Team reports "we have lots of tests but still get surprised by production issues" | Pyramid is base-heavy with a missing or thin integration/policy layer — an "ice cream cone" inversion, or simply a missing top   | Run a pyramid audit (§5.2); deliberately invest in the under-represented layer rather than adding more base-layer checks |
| A `terraform test` file's apply-mode `run` block runs on every PR unintentionally | No filtering/separation between plan-mode and apply-mode `run` blocks by CI trigger                                              | Split expensive `run` blocks into a separately-triggered test file or use `-test.run` filtering as shown in §5.3         |
| Engineers routinely skip or ignore a specific layer's failures                    | That layer's checks are miscalibrated (too noisy, too slow, too disconnected from real risk) relative to its cost, eroding trust | Recalibrate or remove the layer's specific noisy checks rather than letting the whole layer be ignored by habit          |

## 9. Best Practices

- Size each pyramid layer's frequency and required-ness to its actual cost and the risk it mitigates — cheap/frequent at the base, expensive/selective at the top, as a default heuristic adjusted upward for genuinely high-risk modules.
- Periodically audit the actual shape of the testing pyramid in place (per §5.2) rather than assuming coverage exists because tooling was set up once, since coverage silently erodes as triggers get misconfigured or tests go unmaintained.
- Treat the top policy/manual-review layer as non-optional for the organization's highest-risk resource types (IAM, network security boundaries, data stores) even if lower-risk modules only warrant the base and middle layers.

## 10. Common Anti-Patterns / Mistakes

- **The "ice cream cone" inversion**: heavy reliance on slow, expensive, infrequent checks (manual review, rare integration tests) with a thin or missing fast base layer — regressions linger far longer than they would under a correctly-shaped pyramid, and the expensive checks are overloaded trying to catch everything the cheap layer should have caught first.
- **Running every layer on every trigger indiscriminately** ("just run everything on every PR to be safe") — this doesn't actually maximize safety, it maximizes CI cost and pipeline latency to the point teams start ignoring or disabling checks out of frustration, net-reducing real coverage.
- **Treating the pyramid as complete once the tooling exists, without auditing that triggers, ownership, and maintenance are actually keeping each layer functional over time** — a stale integration test suite nobody's looked at in a year provides much less real assurance than its presence in the repository suggests.

## 11. Interview Questions

**🎯 Beginner:** _"Why does an automated IaC testing strategy usually run more checks, more often, at the 'bottom' (formatting, validate) than at the 'top' (integration tests, policy)?"_
**Model answer:** It's a direct consequence of cost. Base-layer checks like `terraform fmt -check` and `validate` cost milliseconds and no real infrastructure, so they can run on every commit with no meaningful downside. Integration tests that actually apply real infrastructure cost real time (minutes) and real cloud spend, so running them on every trivial commit would be wasteful — they're reserved for less frequent triggers, like module-source changes or a nightly schedule, where the cost is justified by the specific risk being checked.
_What the interviewer is probing for:_ Basic grasp of the cost/frequency trade-off as the reason for the pyramid shape, not just memorized layer names.

**🎯 Intermediate:** _"How does the IaC testing pyramid differ from the traditional software testing pyramid (unit → integration → E2E)?"_
**Model answer:** The traditional pyramid's base is unit tests of pure, I/O-free functions — the cheapest possible check, entirely detached from any external system. IaC has no true equivalent: even the cheapest IaC check, `terraform validate`, still checks configuration against a real provider schema (installed locally, but representing a real external API's shape), because Terraform configuration inherently describes external infrastructure rather than pure logic. So IaC's base layer (fmt/validate/lint) is cheap and fast like unit tests, but it's checking schema-consistency against a declared external system, not pure functions — the pyramid shape (cheap/frequent at bottom, expensive/rare at top) is the same, but what occupies the base is conceptually different.
_What the interviewer is probing for:_ Whether the candidate can articulate the actual structural difference, not just recite "IaC has a pyramid too."

**🎯 Senior:** _"A team's CI budget has grown unsustainably as their Terraform monorepo scaled to 40 modules. Diagnose likely causes using the testing pyramid framework, and propose a fix."_
**Model answer:** The most likely cause is that the pyramid has inverted or flattened — apply-based integration tests (Terratest/`terraform test` in apply mode) are probably triggering on every PR across the whole monorepo rather than being scoped to only the specific module(s) actually changed, so a one-line change to module #12 is paying the cost of re-running integration tests for all 40 modules, or at minimum for that module on every trivial commit rather than a coarser schedule. I'd audit CI trigger configuration first (per the pattern in §5.1/§5.2) to confirm scoping — most CI systems support path-based triggering, so integration tests for module N should only run on changes actually touching module N's path, not the whole repo. I'd also introduce a nightly/scheduled full-suite run as a safety net (catching provider-side drift affecting a module even without a code change) instead of trying to get that same coverage from every-PR triggering. This restores the pyramid's shape — narrow, infrequent integration testing scoped to what actually changed — without losing real coverage.
_What the interviewer is probing for:_ Practical diagnostic ability connecting a real operational symptom (CI cost) back to a specific, fixable pyramid-shape problem (trigger scoping), not just abstract pyramid theory.

**🎯 Architect:** _"You're setting IaC testing standards for an organization spanning teams with wildly different risk profiles — a team managing IAM/network security boundaries and a team managing internal dev-environment sandboxes. Should both teams have the same-shaped testing pyramid? Design an approach."_
**Model answer:** No — uniform pyramid shape across teams with genuinely different risk profiles is itself a mistake, treating the pyramid as a checklist rather than a risk-calibrated strategy. I'd establish an organization-wide _minimum_ baseline (every team gets the base layer — pre-commit/fmt/validate/tflint — and the middle plan-based layer as non-negotiable, since both are cheap enough that there's no good reason for any team to skip them) but let the upper layers scale with actual risk. For the IAM/network-security team, I'd mandate a substantial integration-test layer (Terratest asserting real policy behavior, not just plan-time attribute checks) and a hard-mandatory policy layer (Sentinel/OPA denying, not just warning on, risky patterns), plus mandatory manual review for any change touching specific high-risk resource types, enforced via `CODEOWNERS`. For the internal dev-sandbox team, I'd allow a much thinner top — advisory-only policy checks, integration tests reserved for shared modules rather than every disposable environment, and no mandatory manual review beyond normal code review — since the blast radius of a mistake there is genuinely much lower. I'd formalize this as a tiered standard (e.g., "Tier 1: production-security-adjacent" vs. "Tier 2: internal/sandbox") that teams are classified into, rather than either forcing the heavier team's whole pyramid onto the lighter team (wasteful, causes resentment and pyramid-collapse from ignored checks) or leaving the heavier team under-covered by matching the lighter team's minimal shape.
_What the interviewer is probing for:_ Whether the candidate treats the pyramid as a risk-calibration tool applied differentially across an organization, rather than a one-size-fits-all technical standard — genuine platform-engineering governance thinking.

## 12. Common Misconceptions

1. **"More tests at every layer is always better."** Beyond a point, adding checks at the expensive upper layers without corresponding value just inflates CI cost and pipeline latency, often causing teams to start ignoring or disabling checks — net-negative for real coverage.
2. **"The pyramid should look identical for every module/team regardless of risk."** Risk-calibrated pyramid shape (thinner top for low-risk sandboxes, thicker top for security-critical infrastructure) is more correct than uniform application everywhere.
3. **"Having the tooling installed (Terratest configured, policies written) means that layer is actually providing coverage."** A test or policy that exists but isn't correctly wired into a CI trigger, or has gone stale/unmaintained, provides much less real assurance than its mere presence suggests — periodic auditing (§5.2) is necessary, not optional.
4. **"IaC testing pyramids are just the software testing pyramid renamed."** The base layer's character is genuinely different — even the cheapest IaC check (`validate`) is checking against a real external schema, unlike a true unit test of a pure function with no I/O.

## 13. 🔑 Key Takeaways

- The IaC testing pyramid layers cost and frequency together: cheap static checks (fmt/validate/lint) run on every commit, plan-based tests run on every PR, apply-based integration tests run on a coarser trigger (module changes, schedule), and policy/manual review applies selectively to the highest-risk changes.
- The pyramid's shape should be a deliberate, auditable design decision reflected in CI trigger scoping ([§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), not an accident of which tools happened to get adopted first.
- Pyramid shape should scale with actual risk — a uniform shape applied to both high-risk (IAM/network security) and low-risk (dev sandbox) modules is itself a design mistake.
- The "ice cream cone" inversion (heavy expensive/rare testing, thin cheap/frequent base) is a known anti-pattern that applies to IaC exactly as it does to application code.
- Every individual technique in this Part — validate/plan ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)), Terratest/`terraform test` ([§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)), Sentinel/OPA ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)), CI pipelines ([§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), GitOps ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)), pre-commit/tflint ([§104](./Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) — is a specific implementation of one layer of this pyramid; this section is the synthesis, not new tooling.

## 14. Related Concepts & What's Next

This section synthesizes every prior section of Part 14: [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) and [§104](./Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) form the pyramid's base and lower-middle, [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md) forms the integration layer, [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) forms part of the top layer, and [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)–[§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) determine how each layer is actually triggered and enforced in practice. With Part 14 complete, project structure and best-practices coverage continues in Part 15: project structure at scale, including monorepo vs. polyrepo trade-offs that directly affect how CI trigger scoping (§5.1's path-based triggering) is designed, is covered next.

**Next Section:** [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) — `Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md`

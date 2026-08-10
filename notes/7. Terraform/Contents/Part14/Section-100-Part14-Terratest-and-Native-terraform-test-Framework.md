# Section 100 (Part 14): Terratest and the Native terraform test Framework

## 1. Definition

**Plain language:** Plan-based testing ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) can tell you what _would_ change, but it can't tell you whether the infrastructure that actually gets created _works_ — whether a load balancer actually routes traffic, whether a security group actually blocks the port it's supposed to. For that, you need to really apply the configuration against real (usually short-lived, disposable) infrastructure, check that it behaves correctly, and then tear it down. Terratest and Terraform's own native `terraform test` framework are the two dominant ways to write and run that kind of apply-and-assert integration test.

**Precise definition:** **Terratest** is a Go library (from Gruntwork) that provides helper functions to programmatically run `terraform init`/`apply`/`destroy` against real infrastructure from within a Go test function, then make live assertions against the result — HTTP requests against a created endpoint, SSH commands against a created instance, SDK calls to check a resource's real state — using Go's standard `testing` package and `defer` for guaranteed cleanup. **The native `terraform test` framework** (built into Terraform CLI from v1.6+) is HashiCorp's own solution: tests are written in `.tftest.hcl` files using the same HCL syntax as the rest of the configuration, structured as one or more `run` blocks that each either apply the configuration (`command = apply`) or produce a plan only (`command = plan`), followed by `assert` blocks that check conditions against the resulting plan or state — without requiring a separate programming language or test runner.

> 💡 **Tip:** The core trade-off isn't "which is more powerful" — Terratest, being general-purpose Go code, can do almost anything (call arbitrary SDKs, hit HTTP endpoints, orchestrate multi-stage scenarios); native `terraform test` is deliberately more constrained, staying inside HCL and Terraform's own expression language. Teams already comfortable in Go with existing Terratest suites rarely have a reason to rewrite them; teams starting fresh, especially ones who don't want a Go toolchain in their testing story at all, increasingly default to native `terraform test` for anything it can express.

## 2. Why This Matters

- **Plan-based testing has a blind spot: real provider-side behavior.** A `plan` can show a security group rule being created exactly as declared and still not tell you whether that rule actually blocks the traffic it's supposed to at the network layer — only applying and probing real infrastructure proves that.
- **Module correctness needs regression protection.** A shared module ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md), [§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)) consumed by dozens of teams is exactly the kind of code where a subtle change silently breaking downstream consumers is expensive to discover in production — integration tests that apply the module and assert on its outputs/behavior catch regressions before publishing a new version.
- **Native `terraform test` lowers the barrier to entry dramatically.** Not every team has Go expertise; being able to write meaningful tests in the same HCL the rest of the team already knows removes a real adoption barrier that kept testing out of many Terraform codebases for years.
- **Both frameworks support `plan`-only assertions too**, meaning you don't have to pay the cost (time, cloud spend) of a real apply for every test — a hybrid strategy of many cheap plan-only tests and a smaller number of real apply-based integration tests is the norm in mature pipelines, echoing the testing pyramid this Part closes with in [§105](./Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md).
- **Guaranteed teardown matters for cost and blast radius.** Both frameworks are built around the assumption that test-created infrastructure must be reliably destroyed even when assertions fail midway — Terratest's `defer terraform.Destroy(t, opts)` pattern and `terraform test`'s automatic teardown after each `run` block both exist specifically to prevent orphaned real-money infrastructure from failed test runs.

## 3. Prerequisites and Dependencies

This section builds directly on [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)'s plan-based testing techniques — native `terraform test`'s `command = plan` mode is functionally an HCL-native version of the JSON-plan assertions shown there. It also assumes familiarity with modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)), since both frameworks are most commonly used to test modules rather than root configurations, and with the state/apply mechanics from [§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md) and Part 7, since both frameworks apply real configurations against real state. Terratest specifically assumes basic Go familiarity (functions, structs, the `testing` package) — no other Go knowledge is required beyond what's shown here.

## 4. Architecture / Conceptual Diagram

```text
   TERRATEST (Go)                          NATIVE terraform test (HCL)

   go test ./test/...                      terraform test
        │                                       │
        ▼                                       ▼
   func TestVpcModule(t *testing.T) {      run "creates_vpc" {
     opts := &terraform.Options{             command = plan
       TerraformDir: "../examples/vpc",       assert {
     }                                          condition = aws_vpc.main.cidr_block
     defer terraform.Destroy(t, opts)                        == "10.0.0.0/16"
     terraform.InitAndApply(t, opts)         }
                                            }
     vpcId := terraform.Output(t, opts,
                                "vpc_id")   run "instance_is_reachable" {
                                              command = apply
     // live assertion against real AWS      module {
     client := ec2.New(session)                source = "./"
     out, _ := client.DescribeVpcs(...)      }
     assert.Equal(t, "available",            assert {
                     *out...State)             condition = can(
   }                                                        http.get(...))
                                              }
        │                                       │
        ▼                                       ▼
   Real apply → real assertions           Real apply/plan → HCL assert blocks
   (Go SDK calls, HTTP, SSH)              (Terraform expression language)
        │                                       │
        ▼                                       ▼
   defer guarantees terraform destroy     Automatic teardown after each run
   runs even if assertions panic          block, in reverse order
```

- Both tools follow the same fundamental shape: **apply real infrastructure → assert against it → tear it down** — the difference is entirely in the language and assertion vocabulary, not the underlying lifecycle.
- Terratest's assertions can reach arbitrarily far outside Terraform itself (any Go-reachable API, HTTP endpoint, or shell command); native `terraform test` assertions are expressed in Terraform's own expression language against plan/state values and outputs, plus a limited set of built-in functions like `http.get` added specifically to support this use case.
- Both support a `plan`-only mode that skips real infrastructure creation entirely, trading assertion power (you can only check what's _proposed_, not what's _actually true_) for speed and zero cloud cost — this is the cheap end of the testing pyramid covered fully in [§105](./Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md).

## 5. Hands-On

### 5.1 Terratest: Apply, Assert, Destroy

**Purpose:** Write a Go integration test that applies a real module, checks a live property, and guarantees cleanup.

**Syntax:**

```go
package test

import (
    "testing"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/stretchr/testify/assert"
)

func TestVpcModuleCreatesExpectedCidr(t *testing.T) {
    t.Parallel()

    opts := &terraform.Options{
        TerraformDir: "../examples/vpc-basic",
        Vars: map[string]interface{}{
            "cidr_block": "10.0.0.0/16",
        },
    }

    defer terraform.Destroy(t, opts)
    terraform.InitAndApply(t, opts)

    actualCidr := terraform.Output(t, opts, "vpc_cidr_block")
    assert.Equal(t, "10.0.0.0/16", actualCidr)
}
```

**Example usage and expected output:**

```bash
$ go test -v -timeout 30m ./test/...
=== RUN   TestVpcModuleCreatesExpectedCidr
--- PASS: TestVpcModuleCreatesExpectedCidr (94.31s)
PASS
ok      module/test     94.317s
```

**Production usage example:** A shared `vpc` module's repository runs this test suite in CI on every PR that touches module source, against a dedicated disposable test AWS account — protecting every downstream consumer of the module from silent regressions before a new module version is tagged ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)).

**Common errors:** Omitting the `defer terraform.Destroy(t, opts)` line, or placing it after `InitAndApply` instead of immediately after constructing `opts`, means a test that panics or fails an assertion mid-run leaves real infrastructure running indefinitely — `defer` must be registered before the apply that could fail, not after.

### 5.2 Native `terraform test`: Plan-Only Assertions

**Purpose:** Assert on proposed configuration values without paying for a real apply — the cheap, fast end of the framework.

**Syntax:**

```hcl
# tests/vpc_plan.tftest.hcl
variables {
  cidr_block = "10.0.0.0/16"
}

run "vpc_has_expected_cidr" {
  command = plan

  assert {
    condition     = aws_vpc.main.cidr_block == var.cidr_block
    error_message = "VPC CIDR block did not match the input variable"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform test
tests/vpc_plan.tftest.hcl... in progress
  run "vpc_has_expected_cidr"... pass
tests/vpc_plan.tftest.hcl... tearing down
tests/vpc_plan.tftest.hcl... pass

Success! 1 passed, 0 failed.
```

**Production usage example:** Module authors write a plan-only `.tftest.hcl` suite that runs on every commit (fast, no cloud cost) as the first testing gate, reserving a smaller number of `command = apply` tests for a nightly or pre-release pipeline where real infrastructure cost and time are acceptable trade-offs.

**Common errors:** Referencing `var.cidr_block` in an `assert` block without first declaring it in a `variables` block (or passing it via a `run` block's own `variables`) fails with an "undeclared variable" error — test files have their own variable scoping separate from the root module's `.tfvars`.

### 5.3 Native `terraform test`: Full Apply with Multi-Step `run` Blocks

**Purpose:** Chain multiple `run` blocks to apply real infrastructure and assert against actual created resources, including outputs from an earlier `run` feeding into a later one.

**Syntax:**

```hcl
# tests/vpc_apply.tftest.hcl
run "setup" {
  command = apply

  variables {
    cidr_block = "10.0.0.0/16"
  }
}

run "subnet_uses_vpc_cidr_range" {
  command = apply

  variables {
    vpc_id = run.setup.vpc_id
  }

  assert {
    condition     = cidrsubnet(run.setup.vpc_cidr_block, 8, 0) == aws_subnet.public.cidr_block
    error_message = "Subnet CIDR was not carved correctly from the VPC CIDR"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform test -verbose
tests/vpc_apply.tftest.hcl... in progress
  run "setup"... pass
  run "subnet_uses_vpc_cidr_range"... pass
tests/vpc_apply.tftest.hcl... tearing down
tests/vpc_apply.tftest.hcl... pass

Success! 2 passed, 0 failed.
```

**Production usage example:** Multi-`run` test files model realistic multi-resource dependency chains (VPC then subnet then instance) in a single test file, exercising the same dependency graph mechanics ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) the real module relies on, with automatic reverse-order teardown of everything created across all `run` blocks once the file finishes.

**Common errors:** Assuming each `run` block gets a fresh, isolated state — by default, `run` blocks in the same file share accumulated state, so a later block's assertions can be affected by an earlier block's resources still being present; using separate test files (each gets isolated state) is the fix when true isolation is required.

## 6. Production Usage Notes

- **Real apply-based tests cost real money and real time.** A Terratest or `terraform test` `command = apply` suite that spins up actual cloud resources is meaningfully slower (minutes, not seconds) and incurs actual cloud spend — most teams run these on a schedule (nightly) or gated to module-source changes only, not on every commit to every repository.
- **Test infrastructure needs its own isolated account/subscription/project.** Running integration tests against the same account as real production infrastructure risks naming collisions, quota exhaustion, and accidental interference — a dedicated sandbox account, torn down aggressively, is standard practice.
- **Terratest tests commonly wrap Terratest's own retry helpers** (`retry.DoWithRetry`) around eventually-consistent cloud operations — e.g., an instance that's `running` in the API immediately but not yet accepting SSH connections for another 30 seconds — since flaky tests due to eventual consistency are a real and common failure mode, not a bug in the test framework itself.

## 7. Security Considerations

- CI runners executing apply-based integration tests need real, often broad, cloud credentials — the same least-privilege principle for execution roles ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) applies, scoped specifically to the disposable test account rather than production.
- Test fixtures and `.tftest.hcl`/Go test files can accidentally hardcode real secrets or realistic-looking sensitive values for test convenience — treat test code with the same secrets hygiene as production code ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)), since test repositories are just as commonly scanned by attackers as production ones.
- A test suite that fails to tear down (crashed CI runner, killed job) can leave real infrastructure running with real credentials attached — pairing test pipelines with a scheduled "sweep" job that destroys anything tagged as test-origin and older than a threshold is a common safety net against `defer`/teardown failures.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                                                                                 | Resolution Path                                                                                                                                                                 |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Terratest run leaves real infrastructure behind after a failed test | `defer terraform.Destroy` was omitted, placed incorrectly, or the process was killed (not panicked) before defers could run                  | Always register `defer` immediately after `terraform.Options` construction; add a scheduled sweeper job as a backstop                                                           |
| `terraform test` reports "undeclared variable"                      | A variable referenced in an `assert` or `run` block's `variables` wasn't declared in a top-level `variables` block or the module itself      | Declare the variable in the test file's `variables` block or the relevant `run` block                                                                                           |
| Native `terraform test` assertions pass locally but fail in CI      | CI environment lacks credentials/permissions the local developer's session has, causing `command = apply` to fail before assertions even run | Confirm CI execution role has equivalent permissions to the local testing account; check `terraform test` output for the underlying apply error, not just the assertion failure |
| Terratest test is flaky, passing/failing intermittently             | Real cloud resource is eventually consistent (DNS propagation, instance boot time) and the assertion runs before it's ready                  | Wrap the assertion in Terratest's `retry.DoWithRetry` with sensible backoff instead of asserting immediately after apply                                                        |

## 9. Best Practices

- Default to plan-only tests (`command = plan` in native `terraform test`, or JSON-plan assertions per [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) for the bulk of test coverage, reserving real apply-based tests for the smaller set of properties that genuinely can't be verified without real infrastructure.
- Run integration test suites against a dedicated, disposable cloud account/project, never against shared or production-adjacent accounts.
- Always guarantee teardown structurally (Terratest's `defer`, native `terraform test`'s automatic teardown) rather than relying on a final manual `terraform destroy` step that a failed earlier step could skip.

## 10. Common Anti-Patterns / Mistakes

- **Writing only plan-based or unit-style tests and never applying real infrastructure at all.** This misses the entire class of bugs — provider-side rejections, real networking behavior, eventual consistency — that only manifest against real infrastructure; plan-only testing is necessary but not sufficient.
- **Sharing a single long-lived test environment across many parallel test runs instead of provisioning fresh, isolated infrastructure per run.** This produces flaky, order-dependent test failures as concurrent runs collide on the same named resources.
- **Testing only the "happy path" apply and never testing `destroy` or update/replace scenarios.** A module that applies cleanly but fails to destroy cleanly (dependency cycle, IAM permission gap only exercised at delete time) is a real production risk that apply-only test suites never catch.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between Terratest and the native `terraform test` framework, at a high level?"_
**Model answer:** Terratest is a Go library where you write test functions in Go that call Terraform (init/apply/destroy) and make assertions using Go code and any Go-reachable API. The native `terraform test` framework, built into the Terraform CLI itself, lets you write tests directly in HCL, using `.tftest.hcl` files with `run` and `assert` blocks, without needing a separate Go toolchain. Both apply real (or planned) configuration and assert on the result, but Terratest can reach further (arbitrary SDK/HTTP calls) while native `terraform test` stays within Terraform's own expression language.
_What the interviewer is probing for:_ Basic awareness that both exist and roughly why a team would pick one over the other.

**🎯 Intermediate:** _"Why would you write a `command = plan` test instead of a `command = apply` test in native `terraform test`?"_
**Model answer:** A `command = plan` test never actually creates real infrastructure — it only produces a plan and asserts against the proposed changes, similar to the JSON-plan assertions used in plan-based testing. This makes it fast (seconds, not minutes) and free of real cloud cost, at the cost of only being able to verify what's _proposed_, not what's _actually true_ once created. It's the right choice for the bulk of test coverage — checking that inputs produce the expected configuration — reserving the slower, costlier `command = apply` tests for properties that genuinely require real infrastructure to verify, like actual network reachability.
_What the interviewer is probing for:_ Understanding the plan-vs-apply cost/coverage trade-off as a deliberate testing-pyramid decision, not an arbitrary choice.

**🎯 Senior:** _"A Terratest suite for a shared module is flaky — about 1 in 10 runs fails an assertion that checks an EC2 instance is reachable over SSH immediately after apply. How do you diagnose and fix this?"_
**Model answer:** This is very likely an eventual-consistency issue, not a real bug: `terraform apply` returning successfully means the AWS API acknowledged the instance is in a `running` state, but that doesn't guarantee the instance has finished booting, cloud-init has completed, or the SSH daemon has started accepting connections yet. The fix is to wrap the reachability assertion in Terratest's retry helper (`retry.DoWithRetry`) with a reasonable timeout and backoff, rather than asserting immediately after `InitAndApply` returns. I'd also check whether the flakiness correlates with instance type or region (slower boot times) to confirm the eventual-consistency theory rather than assuming it blindly.
_What the interviewer is probing for:_ Practical debugging instinct for a very common real-world Terratest failure mode, and knowledge of the specific tool (`retry.DoWithRetry`) that addresses it.

**🎯 Architect:** _"You're setting testing standards for an organization with 40+ shared Terraform modules maintained by different teams. How do you decide which tests should be plan-only, which should be full apply-based Terratest/`terraform test` suites, and how do you keep cloud spend and CI time under control?"_
**Model answer:** I'd establish a tiered default: every module gets a mandatory plan-only test suite (native `terraform test` `command = plan`) covering input validation, expected resource counts, and output correctness — cheap enough to run on every commit with no cloud cost. A smaller, explicitly-justified set of apply-based integration tests is reserved for properties that can only be verified against real infrastructure — actual network reachability, actual IAM policy enforcement, actual provider-side validation — and those run on a slower cadence (module-source-change-triggered, or nightly) against a dedicated, quota-capped test account, with aggressive automatic teardown and a scheduled sweeper as backstop against orphaned resources. I'd also mandate that no module can be tagged/released ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) without its full test suite passing, making the tiering a release gate rather than an optional nicety. To control spend concretely, I'd track and cap total test-account spend per week and treat a spike as a signal a test is leaking infrastructure, not just a cost line item to shrug off.
_What the interviewer is probing for:_ Organizational-scale thinking about testing strategy as a cost/coverage trade-off with real governance (release gating, spend caps), not just knowledge of the two tools in isolation.

## 12. Common Misconceptions

1. **"Native `terraform test` replaces Terratest entirely."** It covers a large and growing fraction of what Terratest is used for, but Terratest's ability to call arbitrary Go/SDK code still exceeds what HCL's expression language and built-in functions can express for complex scenarios.
2. **"A passing plan-only test means the module works correctly."** It only means the _proposed_ configuration matches expectations — it says nothing about whether the resources, once actually created, behave correctly.
3. **"`defer terraform.Destroy` guarantees cleanup no matter what."** It guarantees cleanup on a Go panic or normal test failure within the same process, but not if the CI runner itself is killed or crashes before the deferred function executes — a scheduled sweeper job is still needed as a backstop.
4. **"Integration tests should run on every single commit like unit tests."** Given their cost (time, cloud spend) most teams deliberately run apply-based integration tests on a coarser trigger (module-source changes, nightly) rather than every commit — cost-aware test cadence is part of correct testing-pyramid design ([§105](./Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md)).

## 13. 🔑 Key Takeaways

- Terratest (Go) and native `terraform test` (HCL) both follow an apply-assert-destroy lifecycle against real or planned infrastructure, differing mainly in language and assertion reach.
- Native `terraform test` supports both `command = plan` (cheap, proposal-only) and `command = apply` (real infrastructure) modes within the same framework.
- Guaranteed teardown — Terratest's `defer`, native `terraform test`'s automatic teardown — is structural, not optional, and should still be backstopped by a scheduled sweeper for crashed runs.
- Apply-based integration tests catch real provider-side and eventual-consistency behavior that plan-based testing ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) structurally cannot.
- Both frameworks are most valuable applied to shared modules, where a regression has the widest blast radius across consuming teams.

## 14. Related Concepts & What's Next

[§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) covered the plan-based testing this section's plan-only test modes build directly on. [§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md) cover the module structure both frameworks are most commonly applied to test. [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) introduces a third testing layer — policy-as-code — that operates on the same plan data these frameworks can also inspect. [§105](./Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md) places both frameworks into a complete testing pyramid alongside static analysis and manual review.

**Next Section:** [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) — `Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md`

# Section 85 (Part 11): Helm vs. Kustomize vs. Raw Manifests — Decision Framework

## 1. Definition

**Plain language:** [§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md)–[§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md) covered Helm's package/template/release model in depth. [§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md) covered Kustomize's patch-based, template-free alternative. [§32](../Part4/Section-32-Part4-YAML-Manifest-Authoring-Kubectl-Apply-Workflow.md) covered raw manifests and the `kubectl apply` workflow underlying both. None of the three is universally correct — each is the right tool for a different combination of team size, application complexity, and operational maturity. This section is the synthesis: a concrete framework for choosing between them, and for recognizing when to migrate from one to another as needs grow.

**Precise definition:** The choice between **raw manifests**, **Kustomize**, and **Helm** is fundamentally a trade-off between **simplicity** and **expressive power** across three axes: templating capability (none, for raw and Kustomize's base layer, vs. full Go templating in Helm), packaging/distribution (Helm's chart-and-repository model vs. Kustomize's and raw manifests' reliance on Git alone), and lifecycle management (Helm's release/revision/rollback tracking vs. Kustomize's and raw manifests' reliance on Git history and GitOps reconciliation for equivalent behavior). In practice, the decision is rarely "pick one forever" — many organizations run raw manifests for the simplest internal tools, Kustomize for first-party application overlays across environments, and Helm for anything distributed externally or composed of third-party dependencies (databases, message queues) pulled from a public chart repository.

## 2. Why This Matters

- **Choosing the wrong tool for a given situation creates real, compounding cost** — adopting Helm's full templating machinery for a single internal tool with one environment is unnecessary complexity, while hand-maintaining raw manifests across five near-identical environments for a growing platform team is exactly the duplicated-effort problem [§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md)'s overlays exist to solve.
- **The three tools are not mutually exclusive within one organization** — a mature platform commonly uses Helm to consume third-party charts (databases, ingress controllers) while using Kustomize or raw manifests for first-party application code, and recognizing this composability prevents an unproductive all-or-nothing framing.
- **This section is the natural close of Part 11's packaging arc**, and directly sets up [§86](./Section-86-Part11-Operators-Operator-Pattern-CRDs.md)'s Operators — a mechanism that goes beyond even Helm's templating to encode operational logic (not just object rendering) directly into a controller, the next step up in expressive power after this section's three options.

🔑 **Key Takeaway:** Raw manifests, Kustomize, and Helm sit on an increasing scale of expressive power and operational overhead — raw manifests for the simplest, single-environment cases; Kustomize for first-party, multi-environment overlays without templating complexity; Helm for anything needing packaging, distribution, or third-party dependency composition — and a mature organization typically uses more than one of the three simultaneously rather than standardizing on exactly one.

## 3. Prerequisites and Dependencies

Synthesizes [§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md) (Helm Fundamentals), [§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md) (Writing Helm Charts), and [§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md) (Kustomize) — this section assumes full familiarity with all three, plus [§32](../Part4/Section-32-Part4-YAML-Manifest-Authoring-Kubectl-Apply-Workflow.md) as the raw-manifest baseline every comparison in this section is measured against.

## 4. Architecture Diagram

```text
                          INCREASING EXPRESSIVE POWER / OPERATIONAL OVERHEAD
   ┌──────────────────────┐     ┌──────────────────────────────┐     ┌─────────────────────────────┐
   │   RAW MANIFESTS      │     │     KUSTOMIZE                │     │        HELM                 │
   │        (§32)         │     │        (§84)                 │     │      (§82-§83)              │
   │                      │     │                              │     │                             │
   │  Plain YAML,         │     │  Plain YAML base +           │     │  Go-templated YAML +        │
   │  kubectl apply       │     │  overlay patches             │     │  values.yaml + chart        │
   │  directly            │ ──► │  (no template syntax)        │ ──► │  packaging/repository       │
   │                      │     │                              │     │                             │
   │  No parameterization │     │  Structural customization    │     │  Full parameterization +    │
   │  No packaging        │     │  No packaging/distribution   │     │  distribution + release/    │
   │  No release tracking │     │  No release/revision history │     │  revision/rollback tracking │
   └─────────┬────────────┘     └──────────────┬───────────────┘     └─────────────┬───────────────┘
             │                                 │                                   │
             ▼                                 ▼                                   ▼
      Best fit: a handful       Best fit: first-party app, several     Best fit: third-party dependencies
      of objects, one           near-identical environments,           (databases, ingress controllers),
      environment, low          no need for packaging/                 wide internal distribution, or
      change frequency          distribution beyond the repo           complex conditional logic

      ┌──────────────────────────────── COMPOSABILITY, NOT EXCLUSIVITY ────────────────────────────────┐
      │  A single platform commonly runs:                                                              │
      │    - Helm for third-party charts (Redis, ingress-nginx, cert-manager)                          │
      │    - Kustomize for first-party app overlays across dev/staging/prod                            │
      │    - Kustomize can even post-process rendered Helm output (`helm template | kustomize build -`)|
      └────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **The three columns are not a strict progression every team must climb** — a small team with one environment and no third-party dependencies has no obligation to adopt Kustomize or Helm at all; raw manifests remain entirely sufficient and are the simplest option to operate and debug.
- **The "composability, not exclusivity" band is the most commonly missed insight** — many teams frame this as a single organization-wide tooling decision, when in practice the right answer is frequently "both, for different purposes."
- **`helm template | kustomize build -`** is a real, occasionally used pattern letting Kustomize's patching apply on top of Helm's rendered output — useful when a third-party chart's own `values.yaml` doesn't expose a specific field a patch can reach instead.

## 5. Hands-On

### 5.1 A Concrete Decision Checklist

**Purpose:** Give a practical, ordered set of questions to work through when choosing a tool for a specific application or component.

**Syntax:** Work through these questions in order; the first "yes" typically settles the choice.

```text
1. Is this a third-party dependency (database, ingress controller, service mesh)
   distributed by its maintainer as a chart?
     → YES: Use Helm. Reinventing a Redis or cert-manager chart from raw
       manifests duplicates maintenance the upstream project already does.

2. Does this application need to be distributed and installed by OTHER teams
   or external customers, with configurable parameters?
     → YES: Use Helm. Packaging, versioning, and a values.yaml contract are
       exactly the distribution problem Helm (§82) solves.

3. Is this a first-party application deployed across several structurally
   similar environments (dev/staging/prod, or multiple regions)?
     → YES: Use Kustomize. Overlay-based patching (§84) avoids duplicating
       the shared manifest structure per environment, with no template syntax
       to maintain.

4. Is this a small number of objects, one environment, low change frequency,
   with no distribution or multi-environment need at all?
     → YES: Raw manifests (§32) remain entirely sufficient — added tooling
       here is complexity without a corresponding benefit.
```

**Production usage example:** A platform team commonly answers "yes" to question 1 for its Redis/PostgreSQL/ingress-nginx dependencies (Helm), "yes" to question 3 for its own first-party services deployed across three environments (Kustomize), and "yes" to question 4 for a single internal cron-job utility with no environment variation at all (raw manifest) — all three coexisting in the same platform.

**Common errors:** Treating this as a one-time, org-wide tooling mandate ("we are a Helm shop") rather than a per-component decision — the most common resulting mistake is either hand-rolling Helm charts for simple, single-environment internal tools that never needed templating, or fighting Kustomize's patch model to express complex conditional logic (a feature flag changing five interdependent fields at once) that a Helm chart's `if`/`with` template logic ([§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md)) handles far more directly.

### 5.2 Migrating Raw Manifests to Kustomize Without Rewriting Them

**Purpose:** Show that adopting Kustomize from an existing raw-manifest baseline ([§32](../Part4/Section-32-Part4-YAML-Manifest-Authoring-Kubectl-Apply-Workflow.md)) requires no manifest rewriting at all — only adding a `kustomization.yaml`.

```yaml
# Existing raw manifests, unchanged from their §32 form:
# deployment.yaml, service.yaml

# New file: kustomization.yaml (the only new artifact required)
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
```

```bash
$ kubectl apply -k .
deployment.apps/myapp created
service/myapp created
```

**Production usage example:** This is the typical, low-risk first step for a team migrating off pure raw manifests — the existing manifests become a Kustomize base with zero modification, and overlays are added incrementally afterward only once genuine multi-environment duplication starts to hurt, rather than as an upfront rewrite.

**Common errors:** Attempting a "big bang" migration to a full base/overlay structure with multiple environments on day one, rather than starting from this minimal single-`kustomization.yaml` step — the incremental path lets a team validate the tool with its existing manifests before investing in overlay design.

### 5.3 Composing Helm and Kustomize Together

**Purpose:** Show the `helm template | kustomize build` pattern for the case where a third-party chart's `values.yaml` doesn't expose a needed field.

```bash
# Render a third-party chart's output, then let a local Kustomize overlay
# patch a field the chart's own values.yaml doesn't expose
$ helm template ingress-nginx ingress-nginx/ingress-nginx -f values.yaml \
    > rendered/ingress-nginx-base.yaml

$ kustomize build overlays/add-annotation/ | kubectl apply -f -
```

**Production usage example:** A team needing a specific `PodDisruptionBudget` annotation the upstream `ingress-nginx` chart doesn't parameterize can render the chart once, treat the output as a Kustomize base, and layer a small patch on top — avoiding a chart fork purely to add one field the upstream project hasn't exposed.

**Common errors:** Relying on this pattern as a long-term substitute for actually requesting the missing parameter upstream (or forking the chart properly) — a `helm template | kustomize build` pipeline built around one specific rendered snapshot can silently drift out of sync the next time the upstream chart version is bumped, since the patch was written against that specific rendered output's structure.

## 6. Production Usage Notes

- **The decision is rarely permanent** — a component that started as a raw manifest commonly graduates to a Kustomize base once a second environment is added, and a Kustomize-managed first-party app occasionally graduates to a full Helm chart once it needs to be distributed to other teams or external customers.
- **Tooling standardization within a single organization has real value even when the "correct" answer varies per component** — settling on "Helm for third-party, Kustomize for first-party" as a documented, organization-wide convention avoids each team independently re-litigating this decision framework from scratch.
- **GitOps controllers ([§88](./Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md)) natively support all three approaches** — ArgoCD and Flux can reconcile raw manifests, Kustomize overlays, and Helm charts equally well from the same Git repository, so the choice of packaging tool doesn't constrain the choice of delivery mechanism.

## 7. Security Considerations

- **Third-party Helm charts and Kustomize bases both carry the same supply-chain trust concern** ([§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md), [§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md)) — the decision framework in this section doesn't change the need to review any external configuration source (chart or base) for RBAC objects, privileged Pod specs, or other security-relevant content before adopting it.
- **Raw manifests offer the most direct auditability for security review**, since there's no templating or patching indirection between what's reviewed and what's applied — a factor worth weighing for the most security-sensitive, lowest-change-frequency components even when Kustomize or Helm might otherwise seem attractive.
- **Whichever tool is chosen, secrets management ([§80](../Part10/Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md)) must be handled the same way** — none of the three tools' native mechanisms (Helm's `values.yaml`, Kustomize's `secretGenerator`, or a raw Secret manifest) should carry plaintext secret values in version control; all three need external integration with Vault, Sealed Secrets, or External Secrets Operator.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                        | Cause                                                                                         | Fix                                                                                                                                                                         |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Team is fighting Kustomize patches to express complex conditional logic        | The use case has outgrown structural patching and genuinely needs template-level conditionals | Migrate the component to a Helm chart, where `if`/`with`/`range` logic ([§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md)) expresses this directly |
| A single internal tool has an unnecessarily elaborate Helm chart               | Helm was adopted by default/convention rather than because the use case needed it             | Downgrade to a raw manifest or a minimal Kustomize base — added tooling isn't justified by a single environment                                                             |
| `helm template \| kustomize build` patch silently breaks after a chart bump    | The overlay's patch was written against one specific rendered snapshot that has since changed | Re-verify the patch against the new rendered output after every upstream chart version bump; consider requesting the field upstream instead                                 |
| Organization has no consistent convention and every team decides independently | No documented decision framework or convention was ever agreed on and circulated              | Adopt and document an explicit convention (e.g., "Helm for third-party, Kustomize for first-party") organization-wide                                                       |

## 9. Best Practices

- Default to raw manifests for the simplest, single-environment, low-change-frequency components — don't adopt tooling complexity before it's actually needed.
- Reach for Kustomize once genuine multi-environment duplication starts to hurt for first-party applications, migrating incrementally (base first, overlays added as needed) rather than all at once.
- Reach for Helm specifically for third-party dependencies distributed as charts, or when a component itself needs to be distributed/parameterized for consumption by other teams or customers.
- Document the organization's convention explicitly, so the decision isn't independently re-litigated by every team for every new component.

## 10. Common Anti-Patterns / Mistakes

- **Standardizing on exactly one of the three tools organization-wide "for consistency," even where it's a poor fit** — forcing Helm's templating overhead onto a trivial single-environment tool, or fighting Kustomize's patch model to express logic a Helm chart would handle directly.
- **Treating the tool choice as permanent and irreversible**, rather than something a component can reasonably graduate between (raw manifest → Kustomize → Helm) as its needs grow.
- **Building a long-lived `helm template | kustomize build` pipeline as a permanent workaround** for a missing chart parameter, rather than either requesting the parameter upstream or accepting the ongoing maintenance cost of the rendered-snapshot patch.

## 11. Interview Questions

**🎯 Beginner:** _"When would you choose Kustomize over Helm for a simple internal application?"_
**Model answer:** If the application is first-party, deployed across a handful of structurally similar environments (dev/staging/production), and doesn't need to be packaged for distribution to other teams or external users, Kustomize is usually the better fit — its base/overlay model handles the environment-specific differences (replica counts, image tags, resource limits) through plain YAML patches, with no template syntax to learn or maintain. Helm's additional machinery — chart packaging, a values schema, a repository — solves a distribution and parameterization problem that a purely internal, first-party application with a handful of environments usually doesn't actually have.
_What the interviewer is probing for:_ Whether the candidate can match tool capability to actual need, rather than defaulting to whichever tool is more popular or feature-rich.

**🎯 Intermediate:** _"Your organization installs several third-party dependencies (Redis, an ingress controller, cert-manager) and also maintains ten first-party applications. What tooling approach would you recommend?"_
**Model answer:** I'd recommend Helm specifically for the third-party dependencies — they're already distributed as maintained charts, and reimplementing their manifests by hand (via raw YAML or a Kustomize base) means taking on maintenance the upstream project already handles, including tracking upstream changes and security patches. For the ten first-party applications, I'd default to Kustomize, since they're internally owned, likely deployed across similar environment sets, and don't need chart packaging or external distribution — a shared base per application with per-environment overlays handles that cleanly without introducing template syntax the team then has to maintain. This isn't an all-or-nothing choice — both tools coexist naturally in the same organization, applied to the class of problem each is actually suited for.
_What the interviewer is probing for:_ Recognition that the decision is per-component, not organization-wide, and that third-party vs. first-party ownership is a strong signal for which tool fits.

**🎯 Senior:** _"A team is fighting to express a feature flag that needs to conditionally change five interdependent fields across two objects, using Kustomize patches. What would you advise, and why?"_
**Model answer:** This is a signal the use case has outgrown Kustomize's structural patching model — Kustomize patches express "here's the value this field should have," not conditional branching logic, so expressing "if this flag is set, change these five interdependent fields consistently across two objects" tends to produce either a proliferation of near-duplicate overlay variants or fragile, hard-to-follow JSON 6902 patches. I'd recommend migrating that specific component to a Helm chart, where Go template's `if`/`with` conditionals ([§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md)) can express the five-field, cross-object conditional directly and legibly in one place, with the flag itself becoming a single `values.yaml` boolean. This doesn't mean abandoning Kustomize for the rest of the organization's first-party applications — it's a signal to graduate this one component specifically, based on its now-outgrown complexity, not a reason to standardize everything on Helm.
_What the interviewer is probing for:_ Ability to recognize the specific technical signal (conditional, cross-object logic) that indicates a tool mismatch, and to recommend a targeted migration rather than an organization-wide overreaction.

**🎯 Architect:** _"Design the packaging and delivery strategy for a platform with 60 first-party services, a dozen third-party dependencies, and a requirement that any change reach production only through a reviewed, auditable pipeline."_
**Model answer:** I'd adopt Helm as the consumption mechanism for all third-party dependencies, pinned to explicit chart versions ([§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md)) and reviewed as a supply-chain input before adoption. For the 60 first-party services, I'd standardize on Kustomize with a shared base-plus-per-environment-overlay structure per service, using `components:` ([§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md)) to share genuinely cross-cutting concerns (a common monitoring sidecar patch, for instance) across services without duplicating patch YAML 60 times over — reserving Helm for any specific first-party service that later needs genuine external distribution or complex conditional templating logic the overlay model can't express cleanly, migrating it individually rather than moving the whole fleet. Every rendered output — whether from Kustomize `build` or `helm template` — would flow through the same CI pipeline: schema/policy validation ([§116](../Part15/Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)) as a required PR check, human review of the rendered diff, and actual cluster reconciliation performed exclusively by a GitOps controller ([§88](./Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md)), never a human running `kubectl apply`/`helm upgrade` directly against production. RBAC ([§74](../Part10/Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md)) around who can merge changes to the Git repository — not who can run cluster commands directly — becomes the actual access-control boundary for production changes under this model, which is what makes the "reviewed, auditable pipeline" requirement structurally true rather than merely a documented policy.
_What the interviewer is probing for:_ Ability to design a coherent, scaled delivery architecture spanning multiple packaging tools, correctly assigning each tool to the class of problem it fits, and tying the whole thing together through GitOps-enforced review rather than ad hoc per-team tooling choices.

## 12. Common Misconceptions

1. **"An organization must standardize on exactly one of Helm, Kustomize, or raw manifests."** All three commonly coexist in the same organization, each applied to the class of component it fits best — third-party dependencies, first-party multi-environment apps, and simple single-environment tools respectively.
2. **"Kustomize is strictly simpler than Helm and therefore always the better default."** Kustomize's patch model genuinely struggles with complex conditional, cross-object logic that Helm's template conditionals express directly — the "simpler" tool isn't simpler for every use case.
3. **"Once a component adopts a packaging tool, that choice is permanent."** Components commonly graduate between raw manifests, Kustomize, and Helm as their needs (multi-environment duplication, external distribution, conditional complexity) grow.
4. **"`helm template | kustomize build` is a permanent, safe way to patch third-party charts indefinitely."** It's a workaround tied to one specific rendered snapshot that can silently drift out of sync on the next upstream chart version bump — it needs ongoing verification, not a set-and-forget assumption.

## 13. 🔑 Key Takeaways

- Raw manifests ([§32](../Part4/Section-32-Part4-YAML-Manifest-Authoring-Kubectl-Apply-Workflow.md)), Kustomize ([§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md)), and Helm ([§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md)–[§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md)) sit on an increasing scale of expressive power and operational overhead, each fitting a different combination of environment count, distribution need, and logic complexity.
- Third-party dependencies distributed as charts almost always favor Helm; first-party, multi-environment applications with no distribution need almost always favor Kustomize; simple, single-environment components need neither.
- The three tools are composable, not mutually exclusive — a single organization commonly runs all three simultaneously for different classes of component.
- Conditional, cross-object logic that Kustomize's patch model struggles to express cleanly is the clearest signal a specific component should graduate to Helm.
- GitOps controllers ([§88](./Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md)) reconcile all three approaches equally well, so the packaging-tool decision doesn't constrain the delivery-mechanism decision.

## 14. Related Concepts & What's Next

This section synthesized [§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md) (Helm Fundamentals), [§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md) (Writing Helm Charts), and [§84](./Section-84-Part11-Kustomize-Bases-Overlays-Patches.md) (Kustomize) into a concrete, per-component decision framework, closing Part 11's core packaging-and-templating arc. [§86](./Section-86-Part11-Operators-Operator-Pattern-CRDs.md), next, introduces Operators and the Operator pattern together with Custom Resource Definitions (CRDs) — a further step up in expressive power beyond even Helm's templating, encoding operational logic (not just manifest rendering) directly into a custom controller that manages an application's full lifecycle natively within the cluster.

**Next Section:** [§86](./Section-86-Part11-Operators-Operator-Pattern-CRDs.md) — `Section-86-Part11-Operators-Operator-Pattern-CRDs.md`

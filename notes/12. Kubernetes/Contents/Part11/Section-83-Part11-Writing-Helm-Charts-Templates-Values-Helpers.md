# Section 83 (Part 11): Writing Helm Charts: Templates, Values, Helpers

## 1. Definition

**Plain language:** §82 treated a chart's `templates/` directory as a black box that somehow turns a `values.yaml` file into rendered manifests. This section opens that box: writing the actual Go templates, structuring values so they're safe and discoverable, and factoring out repeated logic into reusable helpers.

**Precise definition:** A Helm chart's **templates** are ordinary Kubernetes manifest YAML files annotated with **Go template** syntax (`{{ }}` action delimiters), rendered against a per-release **context** — `.Values` (from `values.yaml` merged with `--set`/`-f` overrides), `.Release` (name, namespace, revision), `.Chart` (name, version), and `.Files`/`.Capabilities` for less common cases. **`values.yaml`** supplies the default parameters a template references, typically structured hierarchically (`image.repository`, `image.tag`, `resources.limits.cpu`) so overrides can target a specific nested field without redefining the whole structure. **Helpers** are named, reusable template snippets defined in a special `_helpers.tpl` file (the leading underscore tells Helm not to render it as a standalone manifest) and invoked elsewhere via `{{ include "chartname.labels" . }}`, avoiding copy-pasted boilerplate — standard label sets and name-truncation logic being the most common examples.

## 2. Why This Matters

- **Templates are what actually makes a chart reusable across environments** — the same `deployment.yaml` template renders correctly for dev (1 replica, no resource limits) and production (5 replicas, strict limits) purely by changing the values fed into it, with zero duplication of the manifest structure itself.
- **Helper functions are the difference between a chart that's maintainable at scale and one riddled with subtly inconsistent copy-pasted label blocks** — a single `_helpers.tpl` definition for standard labels, referenced everywhere via `include`, means a labeling convention change is a one-line edit instead of a multi-file find-and-replace.
- **This is the deepest technical content in Part 11 before the decision framework (§85)** — understanding exactly how templates render is what lets an engineer debug a broken chart (via `helm template` and `helm lint`) rather than treating Helm as unexplainable magic.

🔑 **Key Takeaway:** A chart's templates are Kubernetes YAML manifests with embedded Go template actions rendered against `.Values`/`.Release`/`.Chart` context; `values.yaml` supplies the hierarchical default parameters those actions reference, and `_helpers.tpl` factors out repeated logic (standard labels, name truncation) into named, `include`-able snippets — together turning one parameterized template set into correctly rendered manifests for every environment.

## 3. Prerequisites and Dependencies

Builds directly on §82 (Helm Fundamentals — Charts, Releases, Repositories), assuming familiarity with the install/upgrade/rollback lifecycle and the Chart.yaml/values.yaml/templates/ directory structure introduced there. Also assumes familiarity with Deployment, Service, and ConfigMap manifest structure (§24, §27, §28, §41, Part 4/Part 6) as the concrete objects being templated.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────┐
│  values.yaml (defaults)          -f prod-values.yaml (override)   │
│  replicaCount: 1                  replicaCount: 5                 │
│  image:                            image:                         │
│    repository: myapp                tag: "2.3.0"                  │
│    tag: "latest"                                                  │
└───────────────────────┬────────────────────────┬──────────────────┘
                        │  merged (override wins)│
                        ▼                        ▼
              ┌───────────────────────────────────────────┐
              │            RENDER CONTEXT                 │
              │  .Values.replicaCount   → 5               │
              │  .Values.image.tag      → "2.3.0"         │
              │  .Release.Name          → "prod-app"      │
              │  .Release.Namespace     → "production"    │
              │  .Chart.Name            → "mychart"       │
              └──────────────────────┬────────────────────┘
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  templates/deployment.yaml                                                │
│  ---                                                                      │
│  metadata:                                                                │
│    name: {{ .Release.Name }}-mychart                                      │
│    labels:                                                                │
│      {{- include "mychart.labels" . | nindent 4 }}   ◄── calls helper     │
│  spec:                                                                    │
│    replicas: {{ .Values.replicaCount }}                                   │
│    template:                                                              │
│      spec:                                                                │
│        containers:                                                        │
│          - image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"│
│                                                                           │
│  templates/_helpers.tpl                                                   │
│  {{- define "mychart.labels" -}}                                          │
│  app.kubernetes.io/name: {{ .Chart.Name }}                                │
│  app.kubernetes.io/instance: {{ .Release.Name }}                          │
│  {{- end -}}                                                              │
└──────────────────────┬────────────────────────────────────────────────────┘
                       │ helm template / helm install (renders, then applies)
                       ▼
              Final rendered Deployment manifest, ready to apply
```

- **`_helpers.tpl`'s leading underscore is what tells Helm not to try rendering it as a standalone manifest** — it exists purely to hold `define` blocks referenced via `include` elsewhere in `templates/`.
- **`include` (not Go's built-in `template` action) is used almost universally in charts** because `include` returns its output as a string that can be piped through further functions like `nindent` for correct YAML indentation — `template` cannot be piped.
- **Override precedence flows right to left in the diagram**: `-f prod-values.yaml` values win over `values.yaml` defaults for any key present in both, and `--set` flags on the command line win over both.

## 5. Hands-On

### 5.1 Structuring `values.yaml` and Referencing It in a Template

**Purpose:** Show idiomatic hierarchical values and the corresponding template references.

**Syntax:**

```yaml
# values.yaml
replicaCount: 1

image:
  repository: myapp
  tag: "latest"
  pullPolicy: IfNotPresent

resources:
  requests: { cpu: "100m", memory: "128Mi" }
  limits: { cpu: "250m", memory: "256Mi" }

service:
  type: ClusterIP
  port: 80
```

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-mychart
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      containers:
        - name: mychart
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
```

**Production usage example:** A production `prod-values.yaml` overrides only what differs — `replicaCount: 5` and `image.tag: "2.3.0"` — while inheriting every other default (resource limits, pull policy) unchanged from `values.yaml`, keeping the environment-specific override file short and reviewable.

**Common errors:** Forgetting `{{- toYaml .Values.resources | nindent 12 }}`'s exact indentation level produces YAML that's syntactically wrong only after rendering — `helm template` locally before committing is the way to catch this, since the raw template file itself looks fine to the eye.

### 5.2 Writing and Using a `_helpers.tpl` Helper

**Purpose:** Show a real, commonly used helper — standard labels — and how it's invoked.

```yaml
# templates/_helpers.tpl
{{- define "mychart.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "mychart.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
```

```yaml
# templates/deployment.yaml (excerpt)
metadata:
  name: { { include "mychart.fullname" . } }
  labels: { { - include "mychart.labels" . | nindent 4 } }
```

**Example usage and expected output:**

```bash
$ helm template myrelease ./mychart | grep -A4 "^  labels:"
  labels:
    app.kubernetes.io/name: mychart
    app.kubernetes.io/instance: myrelease
    app.kubernetes.io/version: "1.0.0"
    app.kubernetes.io/managed-by: Helm
```

**Production usage example:** Every object template in the chart — Deployment, Service, ConfigMap, Ingress — calls the same `mychart.labels` helper, so a later decision to add a `team:` label organization-wide is a single-line edit to `_helpers.tpl` rather than a multi-file, error-prone find-and-replace across every template.

**Common errors:** Using Go's bare `template` action instead of `include` when the output needs further piping (e.g., `nindent`) — `template` writes its output directly and cannot be chained through a pipe, producing a template parse error that's confusing to a first-time chart author.

### 5.3 Validating a Chart Before Install: `helm lint` and `helm template`

**Purpose:** Show the pre-install validation loop analogous to §32's `--dry-run=server`/`kubectl diff` discipline.

```bash
# Lint checks chart structure and common template mistakes
$ helm lint ./mychart
==> Linting ./mychart
[INFO] Chart.yaml: icon is recommended
1 chart(s) linted, 0 chart(s) failed

# Render templates locally without touching any cluster
$ helm template myrelease ./mychart -f prod-values.yaml > rendered.yaml

# Validate against the live cluster's admission chain without installing
$ helm install myrelease ./mychart -f prod-values.yaml --dry-run --debug
```

**Production usage example:** CI pipelines for chart repositories run `helm lint` and `helm template` (often piping the rendered output into `kubeval` or `kube-linter`, §116, for schema and policy validation) as required checks on every pull request touching a chart — catching template errors and policy violations before a release is ever attempted against a real cluster.

**Common errors:** Relying on `helm lint` alone and skipping `helm template`/`--dry-run` — lint catches structural chart problems (missing required fields, chart metadata issues) but not runtime rendering bugs that only surface once real `.Values` are substituted in, such as a missing key causing a `nil pointer evaluating interface {}` error.

## 6. Production Usage Notes

- **`helm template` is the fastest, cluster-free way to inspect exactly what a chart will produce** for a given values file — run it routinely during chart development rather than iterating via repeated real installs.
- **Use `required` and default-value functions (`default "x" .Values.y`) deliberately** — a template that silently renders `image: ":latest"` because `.Values.image.tag` was omitted is far harder to debug than one that fails fast with `required "image.tag is required" .Values.image.tag`.
- **Chart dependencies (subcharts, declared in `Chart.yaml`'s `dependencies:` block)** let a chart compose other charts (a Redis subchart bundled inside an application chart, for instance) — `helm dependency update` fetches and vendors them into `charts/` before a render or install.

## 7. Security Considerations

- **Templates can render arbitrary Kubernetes objects, including RBAC (Roles, RoleBindings) and SecurityContext fields** — a chart's templates deserve the same review scrutiny as any manifest, since a malicious or careless chart could template an overly permissive ClusterRoleBinding or a privileged Pod spec just as easily as a benign Deployment.
- **`required` guards on security-sensitive values** (e.g., forcing an explicit `runAsNonRoot` decision rather than silently defaulting) turn a missing security setting into a build-time chart failure instead of a silently insecure default reaching production.
- **`.Files.Get`, used to embed file contents (certificates, configuration files) directly into rendered manifests**, should never be used to embed secrets in plaintext — pair with the same secrets-management integration (§80, Part 10) used elsewhere, not raw file embedding.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Cause                                                                                  | Fix                                                                                                       |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `nil pointer evaluating interface {}` during install                    | A template references a `.Values` key that doesn't exist in the values file being used | Add a `default` fallback or a `required` guard; verify with `helm template` using the exact values file   |
| Rendered YAML has broken indentation only visible after `helm template` | Incorrect `nindent`/`indent` argument on a piped helper or `toYaml` call               | Run `helm template` locally and diff the output; adjust the indent count to match the surrounding context |
| A labeling or naming convention needs to change across every object     | Labels/names were copy-pasted per-template instead of factored into `_helpers.tpl`     | Refactor into a shared `define` block in `_helpers.tpl`, referenced via `include` everywhere              |
| `helm lint` passes but install still fails                              | Lint validates chart structure, not runtime rendering against real values              | Always follow lint with `helm template`/`--dry-run` using the actual target values file                   |

## 9. Best Practices

- Structure `values.yaml` hierarchically (`image.repository`, `image.tag`, not flat `imageRepository`, `imageTag`) so overrides can target nested fields cleanly.
- Factor any block of YAML repeated across two or more templates into a `_helpers.tpl` `define`, referenced via `include`, not copy-paste.
- Use `required "message" .Values.x` for any value with no safe default, so missing configuration fails the render loudly instead of producing a silently broken object.
- Run `helm lint` and `helm template` (ideally piped into a manifest linter, §116) as required CI checks on every chart change, mirroring the `--dry-run=server`/`kubectl diff` discipline from §32.

## 10. Common Anti-Patterns / Mistakes

- **Copy-pasting the same label block or naming logic into every template file** instead of factoring it into a single `_helpers.tpl` definition, guaranteeing drift the first time one copy is updated and another isn't.
- **Letting a missing `.Values` key silently render an empty or default-zero-value field** rather than using `required` to fail the render explicitly — deferring the failure from chart-authoring time to a confusing runtime symptom.
- **Skipping local `helm template` validation and iterating exclusively via real `helm install` attempts against a live cluster**, turning every small template fix into a slow, cluster-round-trip debugging cycle.

## 11. Interview Questions

**🎯 Beginner:** _"What's the purpose of `_helpers.tpl` in a Helm chart?"_
**Model answer:** `_helpers.tpl` holds named, reusable template snippets defined with Go template's `define` action — most commonly things like a standard label set or a name-truncation helper. The leading underscore tells Helm not to try rendering the file as a standalone Kubernetes manifest on its own; instead, other templates in the chart reference its definitions via `{{ include "chartname.labels" . }}`. This avoids copy-pasting the same block of YAML into every template file in the chart.
_What the interviewer is probing for:_ Basic understanding of why `_helpers.tpl` exists and how `include` is used to consume it, not just that "it's for helpers."

**🎯 Intermediate:** _"Why is `include` generally preferred over Go's built-in `template` action inside a Helm chart?"_
**Model answer:** `include` returns its rendered output as a string value, which means it can be piped through additional template functions afterward — most commonly `nindent`/`indent` to fix up YAML indentation for wherever the helper's output is being inserted. Go's native `template` action, by contrast, writes its output directly to the surrounding output stream and cannot be chained through a pipe at all — trying to pipe a `template` call is a template syntax error. Since correctly indenting a helper's multi-line YAML output into its calling context is almost always necessary, `include` is the practical default in real charts, with `template` reserved for the rare case where no further processing of the output is needed.
_What the interviewer is probing for:_ Concrete, mechanical understanding of the `include` vs `template` distinction, not just "include is the modern way."

**🎯 Senior:** _"A chart's `helm lint` passes cleanly, but `helm install` fails in production with a nil pointer error. How do you debug this, and why didn't lint catch it?"_
**Model answer:** `helm lint` validates chart structure and common metadata issues (Chart.yaml completeness, basic template syntax) but does not actually render templates against a specific set of real values — it can pass even when a template references a `.Values` key that's absent from the values file actually being used in production. I'd reproduce the failure locally with `helm template <release> ./chart -f <the-exact-production-values-file>`, which renders using the real values and surfaces exactly which key is `nil` when the template tries to dereference a field on it. The fix is either adding a sane `default` fallback for that key or, if there's genuinely no safe default, wrapping it in a `required "descriptive message" .Values.x` guard so future omissions fail at render time with a clear message instead of a bare nil pointer error days or weeks later during an actual production install.
_What the interviewer is probing for:_ Understanding that lint and template-rendering validation are different, complementary checks, plus a concrete, reproducible debugging workflow rather than guessing at the fix.

**🎯 Architect:** _"You're standardizing chart authoring across 15 internal teams. What conventions and tooling would you mandate to keep charts maintainable and safe at that scale?"_
**Model answer:** I'd mandate a shared base of `_helpers.tpl` conventions — standard label sets, name-truncation helpers, common annotations — published as a library chart teams depend on rather than each team reinventing their own, so a labeling or annotation standard change propagates through a single dependency bump rather than 15 separate edits. Every `values.yaml` would follow an enforced hierarchical schema (validated via a values JSON Schema file, which Helm supports natively) so overrides are predictable across charts, and any value without a safe default would be required to use `required` rather than silently rendering an empty or zero-value field. CI for every chart repository would run `helm lint`, `helm template` against each supported environment's values file, and pipe the rendered output through a policy/schema linter (§116) before any chart is published to the internal repository (§82) — mirroring the review discipline §32 established for raw manifests. Finally, I'd require security-sensitive templates (RBAC objects, SecurityContext defaults) to go through the same review process as hand-written manifests, since a chart's templates can render exactly the same privileged objects a raw YAML file can, and chart authorship shouldn't be treated as lower-risk just because it's parameterized.
_What the interviewer is probing for:_ Ability to design chart-authoring governance — shared helpers, values schemas, mandatory validation tooling, and security review — as a coherent program across many teams, not just knowledge of individual template functions.

## 12. Common Misconceptions

1. **"`helm lint` fully validates that a chart will install correctly."** It checks chart structure and common issues, not actual rendering against a specific values file — `helm template`/`--dry-run` is required to catch runtime rendering bugs.
2. **"`template` and `include` are interchangeable."** `include` returns a pipeable string and is required whenever the output needs further processing (like `nindent`); `template` writes directly and cannot be piped.
3. **"A missing `.Values` key just renders as empty, which is harmless."** It can silently produce a broken or insecure object (an empty image tag, a missing SecurityContext field) — `required` guards convert this into an explicit, fail-fast error instead.
4. **"Copy-pasting a label block between two templates is fine since it's 'just labels'."** It guarantees drift the moment one copy is updated and the other isn't — any block repeated across templates belongs in `_helpers.tpl`.

## 13. 🔑 Key Takeaways

- Templates are Kubernetes YAML with embedded Go template actions, rendered against `.Values`/`.Release`/`.Chart` context — `.Values` comes from `values.yaml` merged with any `-f`/`--set` overrides.
- `_helpers.tpl` holds reusable `define` blocks invoked via `include`, which (unlike bare `template`) is pipeable — essential for correctly indenting helper output via `nindent`.
- `required "message" .Values.x` converts a missing, security- or correctness-critical value into an explicit render-time failure instead of a silently broken default.
- `helm lint` validates chart structure; `helm template`/`--dry-run` validates actual rendering against real values — both are necessary, neither alone is sufficient.
- Any block of YAML repeated across two or more templates belongs in a shared helper, not copy-pasted, to avoid convention drift.

## 14. Related Concepts & What's Next

This section opened the black box §82 left closed — showing exactly how a chart's `templates/`, `values.yaml`, and `_helpers.tpl` combine to render environment-specific manifests, and how to validate that rendering (`helm lint`, `helm template`) before it ever reaches a cluster. §84, next, introduces Kustomize — a templating-free alternative that achieves environment-specific customization through structural overlays and patches on plain YAML rather than Go template logic, giving the direct point of contrast §85's decision framework will need.

**Next Section:** §84 — `Section-84-Part11-Kustomize-Bases-Overlays-Patches.md`

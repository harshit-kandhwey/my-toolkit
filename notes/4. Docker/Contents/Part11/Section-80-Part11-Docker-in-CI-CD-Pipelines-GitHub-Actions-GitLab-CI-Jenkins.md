# Section 80 (Part 11): Docker in CI/CD Pipelines: GitHub Actions, GitLab CI, Jenkins

## 1. Definition

**Plain language:** A CI/CD pipeline is a script that runs on someone else's machine every time code changes. Docker shows up in it in two distinct roles: as the **environment** the job runs in (a container that holds the compiler and test tools) and as the **product** the job builds, tests and publishes (an image). Most pipeline confusion comes from mixing these two roles up.

**Precise definition:** In CI, Docker is used in four patterns:

1. **Job container:** the CI system starts a container from a chosen image and runs the job's steps inside it (`container:` in GitHub Actions, `image:` in GitLab CI, `agent { docker { ... } }` in Jenkins). No Docker daemon is needed inside the job.
2. **Service containers:** sidecar containers (database, cache, message broker) started next to the job and reachable by hostname or localhost.
3. **Image build:** the job runs `docker build` or `docker buildx build`, which needs a reachable BuildKit/Docker daemon. This is where the hard design choices live (see [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
4. **Image publish:** the job authenticates to a registry and pushes tagged images ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)).

Hosted runners (GitHub-hosted `ubuntu-latest`, GitLab.com shared runners) provide a fresh VM or container per job, so no state survives between runs unless you explicitly cache it.

> 💡 **Tip:** Ask two questions of every CI step: "does it need a Docker daemon?" and "where does its cache live?" Most pipeline design follows from those two answers.

## 2. Why This Matters

- CI is where an image is first built reproducibly. A "works on my machine" image that cannot be built in CI is not releasable.
- Pipelines hold the most powerful credentials in an organization (registry push, cloud deploy). A badly designed Docker step (privileged DinD, socket mount, secrets in build args) is a common route to supply-chain compromise.
- Build time is the main cost: cold caches turn a 90-second build into a 15-minute one, multiplied by every push.

## 3. Prerequisites and Dependencies

Requires building images ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), layer caching ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), BuildKit features ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)) and registry authentication ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)). Multi-platform builds use buildx ([§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)). Tagging conventions are in [§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md). The daemon/client split that makes remote builders possible is explained in [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md).

## 4. Architecture / Conceptual Diagram

```text
  git push / PR / tag
        │
        ▼
  ┌──────────────────────── CI orchestrator ─────────────────────────┐
  │ GitHub Actions │ GitLab CI │ Jenkins   (schedules jobs, holds     │
  │                                         secrets, OIDC identity)   │
  └───────────────┬──────────────────────────────────────────────────┘
                  │ dispatches job to a runner / agent
                  ▼
  ┌──────────────── Runner (VM or host, ephemeral preferred) ────────┐
  │                                                                   │
  │   Job steps ──► docker CLI ──► Docker daemon / BuildKit           │
  │                                   │  (local, DinD service,        │
  │                                   │   or remote builder)          │
  │        ┌──────────────────────────┤                               │
  │        ▼                          ▼                               │
  │   service containers        build cache                           │
  │   (postgres, redis)         (local, gha, registry, s3)            │
  └───────────────────────────────────┬──────────────────────────────┘
                                      │ push (short-lived credentials)
                                      ▼
                              Container registry ──► deploy / promote

  Typical stage order:
  lint ► unit test ► build image ► scan ► integration test ► push ► deploy
```

- **Daemon location** is the key decision: the runner's own daemon, a DinD sidecar, or a remote BuildKit builder. [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md) compares them.
- **Cache location** decides speed: on an ephemeral runner, the local layer cache is empty every run, so it must be exported and imported ([§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).

## 5. Hands-On

### 5.1 GitHub Actions: Build, Test and Push to GHCR

GitHub-hosted `ubuntu-latest` runners already have Docker Engine installed, and each job gets a fresh VM, so the daemon is local and disposable.

```yaml
# .github/workflows/image.yml
name: image
on:
  push:
    branches: [main]
    tags: ["v*.*.*"]
  pull_request:

permissions:
  contents: read
  packages: write        # only what the job needs

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=sha,format=short

      - uses: docker/login-action@v3
        if: github.event_name != 'pull_request'
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

Notes on this workflow:

- `docker/metadata-action` derives tags and OCI labels from the Git event, so you never hand-write tag logic.
- `permissions:` narrows the automatic `GITHUB_TOKEN`. `packages: write` is required to push to GHCR.

### 5.2 GitHub Actions: Job Container and Service Containers

Run tests inside a pinned toolchain image with a database sidecar, no `docker` command in your steps at all:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    container: node:22-bookworm        # job runs inside this image
    services:
      db:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: ci-only-password
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      DATABASE_URL: postgres://postgres:ci-only-password@db:5432/postgres
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
```

Because the job itself runs in a container, the service is reachable by its label (`db`) on a shared network. If the job ran directly on the VM, you would instead map ports and use `localhost`. The `options` string accepts any `docker create` flag, which is how health checks are attached ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)).

### 5.3 GitLab CI: Docker-in-Docker with TLS

GitLab runners using the Docker executor start each job in a container. To build images you give the job a DinD sidecar:

```yaml
# .gitlab-ci.yml
stages: [build]

build-image:
  stage: build
  image: docker:27
  services:
    - docker:27-dind
  variables:
    DOCKER_HOST: tcp://docker:2376
    DOCKER_TLS_CERTDIR: "/certs"
    DOCKER_TLS_VERIFY: "1"
    DOCKER_CERT_PATH: "/certs/client"
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
  script:
    - docker build --pull -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA" .
    - docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA"
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
```

Requirements and notes:

- The runner must be registered with `privileged = true` in `config.toml`; DinD cannot start without it. This is the main security cost ([§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- `DOCKER_TLS_CERTDIR: "/certs"` makes the `dind` service generate certificates and share them with the job through a volume; the client then talks to port 2376 over TLS. Skipping TLS (`tcp://docker:2375`) exposes an unauthenticated daemon on the job network.
- `$CI_REGISTRY_USER`, `$CI_REGISTRY_PASSWORD` and `$CI_REGISTRY_IMAGE` are predefined; the password is a short-lived job token.

### 5.4 Jenkins: Declarative Pipeline with Docker Agents

Jenkins needs the Docker Pipeline plugin (`docker-workflow`) and a node that has the Docker CLI and daemon access.

```groovy
// Jenkinsfile
pipeline {
  agent none
  options { timeout(time: 30, unit: 'MINUTES') }

  stages {
    stage('Test') {
      agent { docker { image 'node:22-bookworm' } }   // job container
      steps { sh 'npm ci && npm test' }
    }

    stage('Build and Push') {
      agent { label 'docker-builder' }                // node with a daemon
      when { branch 'main' }
      steps {
        script {
          def img = docker.build("registry.example.com/team/app:${env.GIT_COMMIT.take(8)}")
          docker.withRegistry('https://registry.example.com', 'registry-creds') {
            img.push()
          }
        }
      }
    }
  }
}
```

Notes:

- `agent { docker { ... } }` starts the container, mounts the workspace and runs steps inside; the Jenkins agent user's UID may differ from the image's user, which causes workspace permission errors (see section 8).
- `agent none` at the top plus per-stage agents prevents an executor being held idle while a stage waits.

## 6. Production Usage Notes

- **Tag by commit SHA first, promote later.** Build once per merge, tag with the immutable SHA and promote the same digest ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md), [§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)).
- **Ephemeral runners.** One job per runner, destroyed afterwards, so a compromised job cannot poison the next one or leave cached credentials behind.
- **Credentials via OIDC.** Prefer short-lived tokens issued by the CI platform's identity (GitHub OIDC to AWS/GCP/Azure, GitLab ID tokens) over long-lived registry passwords stored as secrets ([§68](../Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)).
- **Gate publishing on tests and scans** ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)); disk and rate-limit hygiene: authenticate pulls ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)) and prune self-hosted runners ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

## 7. Security Considerations

- **Privileged DinD gives the job root-equivalent access to the runner host.** Any pipeline author who can edit the CI file can escape to the host. Use it only on isolated, ephemeral, single-tenant runners, or choose a daemonless/rootless builder.
- **Mounting `/var/run/docker.sock`** is equivalent to root on the host; details in [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md).
- **Secrets in builds.** Do not pass secrets via `--build-arg` or `ENV`; they persist in image history. Use BuildKit secret mounts ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md), [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Supply chain.** Pin actions and plugins by SHA or version, generate SBOM and provenance attestations, and sign images ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| GitLab DinD: `docker: error during connect ... certificate` or hang on `tcp://docker:2375` | TLS variable mismatch between client and dind | Set `DOCKER_TLS_CERTDIR: "/certs"` and `DOCKER_CERT_PATH`/`DOCKER_TLS_VERIFY` consistently |
| GitLab DinD: `privileged mode required` / service fails to start | Runner not configured `privileged = true` | Enable on a dedicated runner, or switch to a daemonless builder |
| `denied: permission_denied: write_package` on GHCR push | `GITHUB_TOKEN` lacks `packages: write`, or the package belongs to another repo | Add `permissions: packages: write` and link the package to the repo |
| `toomanyrequests: You have reached your pull rate limit` | Anonymous Docker Hub pulls from shared IPs | `docker login` before pulls, use a mirror or pull-through cache |
| Build is always cold, no cache hits | Ephemeral runner with no cache import | Add `cache-from`/`cache-to` ([§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)) |
| Jenkins: `EACCES: permission denied` writing workspace in docker agent | Container user UID differs from Jenkins agent UID | Run with `args '-u root'` only if unavoidable; better set matching UID or use `chmod` on a writable subdirectory |

## 9. Best Practices

- Prefer ephemeral, single-use runners; isolate any runner that offers a Docker daemon.
- Export a BuildKit cache explicitly on ephemeral runners.

## 10. Common Anti-Patterns / Mistakes

- Rebuilding the image separately for each environment (staging, production), so what was tested is not what ships.
- Embedding registry passwords in the pipeline file, or in a `--build-arg`.
- Running PR builds from forks on self-hosted runners with deployment credentials.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between running a CI job inside a Docker container and building a Docker image in a CI job?"_
**Model answer:** A job container is the environment the steps run in: the CI system starts a container from an image such as `node:22` and executes the build and test commands in it, which pins the toolchain version. Building an image is the job's output: a step runs `docker build` to produce an artifact. The first needs no Docker daemon inside the job; the second does, because `docker build` needs a daemon or BuildKit to talk to. A pipeline can do both: test in a Node container, then build and push an image on a runner with a daemon.
_What the interviewer is probing for:_ Distinguishing Docker as environment from Docker as product, and knowing that building images requires a reachable daemon.

**🎯 Intermediate:** _"Your GitHub Actions image build takes 12 minutes on every push even though only application code changes. Why, and what do you change?"_
**Model answer:** GitHub-hosted runners are fresh VMs, so the local layer cache is empty each run and every layer rebuilds. Two fixes: first, order the Dockerfile so dependency manifests are copied and installed before the source `COPY`, so source edits only invalidate the last layers. Second, export and import the BuildKit cache with `docker/build-push-action` using `cache-from: type=gha` and `cache-to: type=gha,mode=max` (or a registry cache). Also use `setup-buildx-action` since the `gha` cache backend requires a buildx builder with the docker-container driver. Verify by checking for `CACHED` lines in the log and compare wall time.
_What the interviewer is probing for:_ Understanding ephemeral-runner cache loss and the two-part fix (Dockerfile ordering plus external cache).

**🎯 Senior:** _"A GitLab team wants to build images on shared runners. They propose privileged DinD because it is what the docs show. Evaluate and recommend."_
**Model answer:** Privileged DinD isolates build state per job, but a privileged container is effectively root on the runner host, so anyone who can edit `.gitlab-ci.yml` can escape and read other jobs' secrets. On shared multi-tenant runners that is unacceptable. Options: dedicated single-tenant ephemeral autoscaled runners so the blast radius is one VM; rootless BuildKit or another daemonless builder needing no `privileged`; or a remote BuildKit service in an isolated build cluster. If DinD stays, require TLS, pin versions, restrict which projects may use the runner tag and protect variables to protected branches. I would recommend ephemeral dedicated runners first and rootless builders as the target state.
_What the interviewer is probing for:_ Threat-modeling the runner, knowing the alternatives, and giving a staged recommendation rather than a binary answer.

**🎯 Architect:** _"Design the container CI/CD platform for 300 repositories across teams: runners, caching, credentials, promotion and guardrails."_
**Model answer:** Autoscaled, ephemeral, one-job-per-instance runner pools split by trust: an untrusted pool for PRs with no secrets, and a trusted pool for protected branches and tags. Builds run on rootless or remote BuildKit builders so no job gets a privileged daemon. Caching is layered: a registry-backed BuildKit cache per repository, a pull-through mirror against Hub rate limits, and cache writes restricted to trusted branches. Credentials are short-lived, repository-scoped tokens obtained through OIDC, with no long-lived secrets in the CI variable store. A shared versioned pipeline template encodes the standard flow: lint, test, build once, scan, SBOM and provenance, sign, push by digest. Promotion moves the same digest ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)), never a rebuild. Guardrails: signature-verifying admission policy, scan thresholds as required checks, pinned actions, CODEOWNERS review of pipeline config, and metrics on build time and cache hit rate.
_What the interviewer is probing for:_ Trust-tiered runner design, secretless credentials, build-once-promote-many, and organization-wide enforcement through templates and policy.

## 12. Common Misconceptions

- "CI needs the Docker daemon in every job." Only jobs that build or run images do; job and service containers are started by the CI system.
- "Docker-in-Docker is sandboxed, so it is safe." The standard DinD setup requires privileged mode, which weakens isolation.
- "The layer cache just works in CI." Ephemeral runners start empty; the cache must be exported and imported.
- "`docker login` secrets are safe because CI masks them in logs." Masking is string matching and does not protect against transformation or against code that exfiltrates the secret.

## 13. 🔑 Key Takeaways

- Docker in CI plays two roles: job environment and build product; only building needs a daemon.
- Decide daemon location (local, DinD, remote or daemonless builder) based on trust and isolation, not convenience ([§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- Ephemeral runners start with no cache; export and import BuildKit cache and order the Dockerfile for it.
- Build once, tag with the commit SHA, test and push that digest, promote without rebuilding.
- Use short-lived OIDC credentials, least-privilege `permissions`, and keep PR builds secret-free.
- Privileged DinD and socket mounts are root-equivalent on the runner host.
- Pin actions, plugins and base images; scan and sign before publishing.

## 14. Related Concepts & What's Next

Related: Dockerfile build mechanics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), cache invalidation ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), BuildKit secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)), multi-platform pipelines ([§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)), registry authentication ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)), vulnerability scanning ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)). Later in this part: automated build-and-push pipelines ([§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), integration testing with ephemeral containers ([§83](Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)), GitOps promotion ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)) and CI caching ([§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)). Next, [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md) compares the two ways of giving a job a Docker daemon and what each costs in security.

**Next Section:** [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md) — `Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md`

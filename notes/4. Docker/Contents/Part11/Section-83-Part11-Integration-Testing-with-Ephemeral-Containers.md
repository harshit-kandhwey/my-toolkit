# Section 83 (Part 11): Integration Testing with Ephemeral Containers

## 1. Definition

**Plain language:** Instead of testing against a shared, long-lived database or a mock, you start a real, disposable copy of each dependency (Postgres, Redis, Kafka, a mock API) in containers for the duration of a test run, then throw it away.

**Precise definition:** An *ephemeral test environment* is a set of containers created on demand by the test run itself or by a wrapper (`docker compose`, Testcontainers, a CI `services:` block), with these properties: (1) **isolated** (unique project/network names, no fixed host ports), (2) **deterministic** (pinned image tags or digests, seeded data), (3) **self-readying** (the test waits on a health or log signal, not a `sleep`), and (4) **self-cleaning** (containers, networks and volumes are removed on success, failure, and cancellation). *Integration tests* here means tests that exercise your code against real infrastructure components over real protocols, as opposed to unit tests with in-memory fakes.

> 💡 **Tip:** The goal is "production-shaped but disposable". Test the same database engine and major version you run in production, not SQLite standing in for Postgres.

## 2. Why This Matters

- Mocks drift from reality. A real Postgres catches SQL dialect, locking, migration and index behavior that fakes never will.
- Shared test databases create flaky tests: leftover rows, parallel runs stepping on each other, "works after somebody cleans staging".
- Ephemeral environments make tests reproducible on a laptop, in CI, and in a PR pipeline with the same definition ([§41](../Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md), [§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).
- They are the gate that sits between "built" and "pushed" in an image pipeline ([§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), and the way to test **the image itself**, not just the source tree.
- Poorly written ephemeral tests leak containers, ports and disk, so cleanup discipline is part of the skill ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

## 3. Prerequisites and Dependencies

Requires Compose basics ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), [§38](../Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md), [§40](../Part5/Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)), readiness mechanics ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), networking and port publishing ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md), [§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), and volumes/tmpfs ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)). In CI the test runner's access to a daemon follows [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md). Understanding `docker run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)) and lifecycle ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)) is assumed.

## 4. Architecture / Conceptual Diagram

```text
  Three ways to get ephemeral dependencies

  A) Compose-driven (black-box test of a built image)
  ┌─────────────────────────────────────────────────────────────┐
  │ docker compose -p it-$RUN_ID up --wait ──► network it-123   │
  │   ┌────────┐  ┌────────┐  ┌──────────────┐                  │
  │   │ db     │  │ cache  │  │ app (image   │◄── under test    │
  │   │ health │  │ health │  │  just built) │                  │
  │   └────────┘  └────────┘  └──────┬───────┘                  │
  │                                  ▲                          │
  │   ┌────────────────┐  HTTP       │                          │
  │   │ tests container├─────────────┘                          │
  │   └────────────────┘                                        │
  │ docker compose -p it-$RUN_ID down -v  (always, even on fail)│
  └─────────────────────────────────────────────────────────────┘

  B) Library-driven (Testcontainers; tests start what they need)
  ┌───────────────┐  Docker API   ┌────────────┐   ┌──────────────┐
  │ test process  ├──────────────►│ dockerd    ├──►│ postgres:16  │ random host port
  │ (JUnit/pytest │◄──────────────┤            │   └──────────────┘
  │  /go test)    │  host:port    │            │   ┌──────────────┐
  └───────┬───────┘               │            ├──►│ Ryuk reaper  │ removes leftovers
          │                       └────────────┘   └──────────────┘ if tests crash
          └── waits for readiness strategy, then runs tests

  C) CI services block (platform-managed sidecars)
  job container ──► service containers on a job-scoped network (hostname = alias)

  Lifecycle:  create ► start ► WAIT (health/log/port) ► seed ► test ► collect logs ► destroy
```

- **Unique identity per run:** `-p it-$RUN_ID` or random container names prevent parallel jobs colliding.
- **Random host ports:** publish `127.0.0.1::5432` (container port only) and read the assigned port, instead of hard-coding `5432`.
- **Reaper:** Testcontainers' Ryuk sidecar removes labelled resources if the test JVM or process dies, which `try/finally` cannot guarantee.

## 5. Hands-On

### 5.1 One-Off Ephemeral Dependency with `docker run`

```bash
CID=$(docker run -d --rm \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=app \
  -p 127.0.0.1::5432 \
  --health-cmd "pg_isready -U postgres -d app" \
  --health-interval 1s --health-retries 30 \
  postgres:16.4-alpine)

until [ "$(docker inspect -f '{{.State.Health.Status}}' "$CID")" = "healthy" ]; do sleep 1; done
PORT=$(docker port "$CID" 5432/tcp | head -n1 | sed 's/.*://')
echo "postgres ready on 127.0.0.1:$PORT"

DATABASE_URL="postgres://postgres:test@127.0.0.1:$PORT/app" ./run-tests.sh
docker stop "$CID"      # --rm removes it
```

```text
postgres ready on 127.0.0.1:49153
```

`--rm` plus `docker stop` leaves nothing behind. `-p 127.0.0.1::5432` publishes on a random loopback-only port, so parallel runs do not collide and nothing is exposed on the LAN. Wrap the test line in `trap 'docker stop "$CID" >/dev/null' EXIT` so the container is stopped even when tests fail.

### 5.2 Compose Test Stack with Health-Gated Startup

```yaml
# compose.test.yaml
services:
  db:
    image: postgres:16.4-alpine
    environment:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: app
    tmpfs:
      - /var/lib/postgresql/data       # RAM-backed: fast and automatically ephemeral
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d app"]
      interval: 2s
      timeout: 3s
      retries: 20

  cache:
    image: redis:7.4-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      retries: 15

  app:
    image: ${APP_IMAGE:?set APP_IMAGE to the image under test}
    environment:
      DATABASE_URL: postgres://postgres:test@db:5432/app
      REDIS_URL: redis://cache:6379
    depends_on:
      db:    { condition: service_healthy }
      cache: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/healthz"]
      interval: 2s
      retries: 20

  tests:
    build: ./tests
    profiles: ["test"]
    environment:
      BASE_URL: http://app:8080
    depends_on:
      app: { condition: service_healthy }
```

```bash
export APP_IMAGE=registry.example.com/team/app:sha-9b2f6c0
export COMPOSE_PROJECT_NAME="it-${CI_JOB_ID:-$$}"

docker compose -f compose.test.yaml --profile test up \
  --build --abort-on-container-exit --exit-code-from tests
RC=$?
docker compose -f compose.test.yaml logs --no-color > compose-logs.txt || true
docker compose -f compose.test.yaml --profile test down -v --remove-orphans
exit $RC
```

```text
it-123-db-1     | database system is ready to accept connections
it-123-tests-1  | 14 passed in 3.21s
it-123-tests-1 exited with code 0
```

`--exit-code-from tests` makes the Compose exit status the test result; `--abort-on-container-exit` stops the stack when the test container finishes. Capturing logs **before** `down` preserves evidence for failures. Using `up --wait` instead (without a test container) waits for all services to be healthy and returns, handy when the tests run on the host.

### 5.3 Testcontainers in Code (Python)

```python
import pytest
from testcontainers.postgres import PostgresContainer
import sqlalchemy

@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("postgres:16.4-alpine") as c:   # waits for readiness
        yield c                                             # removed on exit

def test_insert(pg):
    engine = sqlalchemy.create_engine(pg.get_connection_url())
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("create table t(id int)"))
        conn.execute(sqlalchemy.text("insert into t values (1)"))
        assert conn.execute(sqlalchemy.text("select count(*) from t")).scalar() == 1
```

```text
tests/test_db.py .                                                    [100%]
1 passed in 4.87s
```

Equivalent libraries exist for Java (the original), Go, Node, .NET and Rust. The library maps a random host port, applies a wait strategy (log message, health check or port), and registers the container with the Ryuk reaper. Scope containers per session or module, not per test, to keep suites fast, and reset state between tests with transactions or truncation.

## 6. Production Usage Notes

- **Build the image, test the image:** run the integration suite against the exact image the pipeline will push ([§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), referencing it by tag or digest in the compose file. Testing source code and then shipping a different artifact defeats the purpose.
- **Readiness over sleeps:** `depends_on: condition: service_healthy`, `docker compose up --wait`, or library wait strategies. A `sleep 10` is a flaky test waiting to happen ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)).
- **Pin versions:** `postgres:16.4-alpine` or a digest, not `latest`; update intentionally via Renovate so a test failure means your change broke it, not an upstream release.
- **Evidence on failure:** upload `docker compose logs`, `docker inspect` output and any service-generated files as CI artifacts before teardown. Use `if: always()` / `after_script`.

## 7. Security Considerations

- **Bind to loopback:** publish test ports as `127.0.0.1::PORT`; a bare `-p 5432:5432` exposes a database with a trivial password on every interface of the runner, a real risk on self-hosted machines ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- **Test credentials only:** never point test stacks at production secrets or copies of production data. If you need realistic data, use synthetic or anonymized fixtures.
- **Image provenance:** pin and scan test dependencies too; a compromised `latest` of a database image runs in your CI with network access ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Do not mount the socket into test containers casually:** Testcontainers needs the Docker API, which is root-equivalent on that daemon ([§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)). Keep this to isolated, ephemeral runners.
- **Run the app under test as in production:** non-root user, read-only root filesystem and dropped capabilities ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)). Integration tests are the cheapest place to discover that the hardened image cannot write to `/tmp` or bind port 80.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `connection refused` on first test | Test ran before the dependency was ready (container "started" is not "ready") | Health check plus `condition: service_healthy`, `up --wait`, or library wait strategy |
| Works locally, fails in CI | Different image versions, fixed ports, or CI job inside a container using `localhost` | Pin tags; use service aliases inside containers, mapped ports from the host |
| `port is already allocated` | Hard-coded host port with parallel jobs or a leaked container | Random ports (`127.0.0.1::5432`), unique project names, cleanup trap |
| `pull access denied` / rate limit | Anonymous Hub pulls from shared runner IPs | Authenticated pulls, mirror, pre-pulled images |
| Tests pass but containers remain | Teardown skipped on failure or cancellation | `trap ... EXIT`, `if: always()`, Ryuk reaper, scheduled prune |
| Database tests see stale data | Reused volume or non-isolated schema between tests | tmpfs/ephemeral storage, `down -v`, transaction rollback or per-test schema |
| Testcontainers: `Could not find a valid Docker environment` | No daemon or wrong `DOCKER_HOST` in the runner | Provide a daemon (DinD or runner socket), set `DOCKER_HOST` |
| Testcontainers: mapped host unreachable from sibling | Test process inside a container uses `localhost` | Set `TESTCONTAINERS_HOST_OVERRIDE` to the docker host address, or attach to a shared network |

## 9. Best Practices

- Define the test stack in version-controlled code (compose file or Testcontainers fixture) so local and CI runs are identical.
- Test **the built image** and the **production engine versions**.
- Wait on **health**, never on time.
- Unique project names, no `container_name`, no fixed host ports, loopback-only publishing.
- Make teardown unconditional: `trap`, `finally`, `always()`, and a leak check.
- Collect **logs and artifacts before teardown**.
- Keep data **synthetic and seeded**; reset by rollback/truncate between tests, recreate between runs.
- Pin versions and update them deliberately.

## 10. Common Anti-Patterns / Mistakes

- `sleep 30` instead of a readiness check.
- Sharing one long-lived "test" database among developers and CI.
- Using `:latest` for dependencies, so the suite breaks without any code change.
- Hard-coding `localhost:5432` and then failing under parallel runs or when the suite is itself containerized.
- Cleanup only on the success path, leaving failed-run containers and volumes behind.
- Testing source rather than the image, then shipping an image whose entrypoint, user, or file permissions were never exercised.

## 11. Interview Questions

**🎯 Beginner:** _"Why use a real database in a container for integration tests instead of mocking it?"_
**Model answer:** A mock only returns what you told it to, so it can hide real problems such as SQL syntax differences, constraint violations, transaction behavior, or migration failures. A containerized database is the same engine you run in production, started fresh for the test run and deleted afterward, so tests are realistic and isolated, and nobody's leftover data affects the result. It is cheap to create with `docker run` or Compose, and the same definition works on any developer machine and in CI.
_What the interviewer is probing for:_ The value of production-like dependencies and the "ephemeral" concept (fresh, isolated, disposable).

**🎯 Intermediate:** _"Your integration tests fail intermittently with `connection refused` right after `docker compose up -d`. Explain the cause and fix it properly."_
**Model answer:** `up -d` returns as soon as containers are started, not when the processes inside accept connections; Postgres may still be initializing. Adding `sleep` is brittle. The proper fix is to define a health check on each dependency (`pg_isready`, `redis-cli ping`, an HTTP `/healthz`) and gate on it: `depends_on` with `condition: service_healthy` for service ordering, and `docker compose up --wait` (or a library wait strategy in Testcontainers) so the test process begins only after everything reports healthy. Also set a sensible `retries`/`interval` so slow CI machines do not flap, and make the application retry connections at startup, since production has the same race.
_What the interviewer is probing for:_ Started vs. ready, health-check-based orchestration, and robust startup design.

**🎯 Senior:** _"Run 40 CI pipelines in parallel on the same set of self-hosted runners, each needing its own Postgres and Redis. What goes wrong with a naive compose file and how do you fix it?"_
**Model answer:** A naive file has `container_name:` values and fixed host ports like `5432:5432`, so the second pipeline fails with name or port conflicts, or worse, connects to another job's database and produces cross-contamination. Fixes: remove `container_name`, set a unique `COMPOSE_PROJECT_NAME` per job (for example `it-$CI_JOB_ID`) so networks, containers and volumes are namespaced, publish ports as `127.0.0.1::5432` and discover them with `docker compose port`, or avoid publishing and run the tests in a container on the project's network. Make teardown unconditional with `down -v --remove-orphans`, add a post-job leak check, and a scheduled janitor that prunes resources by label and age to catch cancelled jobs. Limit CPU and memory per stack so 40 stacks cannot starve the host, pre-pull pinned images, and ideally run each job on an ephemeral runner so isolation is guaranteed by the VM, not just naming.
_What the interviewer is probing for:_ Concurrency hazards in shared daemons, resource namespacing, cleanup guarantees, and capacity thinking.

**🎯 Architect:** _"Define a company-wide standard for integration testing with containers across Java, Python and Go services, including CI on Kubernetes-based runners without privileged pods."_
**Model answer:** Set a contract rather than a single tool: tests must run with one command locally and in CI, against pinned production-matching dependency versions, with health-gated startup, no fixed ports, and guaranteed cleanup. For in-process tests, adopt Testcontainers per language with a shared catalog of approved, pinned dependency images and wait strategies, mirrored in an internal registry. For black-box tests of built images, provide a shared Compose template and a reusable pipeline step that builds, tests by digest, uploads logs, and enforces a leak check. Because Kubernetes runners cannot give pods a Docker daemon without privilege, provide one of: a remote, isolated daemon service per job (Testcontainers Cloud or an in-house Sysbox/Kata-based sandbox), rootless Docker in a hardened runner pool, or Kubernetes-native service sidecars and ephemeral namespaces for dependencies. Govern with versions managed via Renovate, per-team resource quotas, an image scanning policy for test dependencies, and metrics on suite duration and flake rate. Trade-offs: remote daemons add cost and network latency; sidecars are less flexible than Compose; a strict standard needs an escape hatch with review.
_What the interviewer is probing for:_ Platform thinking: portability across languages and runners, security constraints (no privileged pods), standardization versus flexibility, and operational metrics.

## 12. Common Misconceptions

- "`docker compose up -d` means the services are ready." It means they started.
- "Ephemeral means the data is deleted automatically." Only if no named volume or bind mount persists it; use `down -v` or `tmpfs`.
- "Testcontainers needs Docker-in-Docker." It needs access to *a* Docker API, which can be a normal host daemon or a remote one.
- "`depends_on` alone waits for readiness." Only with `condition: service_healthy`.
- "`localhost` works the same everywhere." Inside a container it refers to that container, not the host or sibling services.

## 13. 🔑 Key Takeaways

- Ephemeral = isolated, pinned, health-gated, and unconditionally cleaned up.
- Wait on health checks (`service_healthy`, `up --wait`, wait strategies), never `sleep`.
- Parallel safety: unique project names, no `container_name`, random loopback ports.
- Test the built image against production-matching dependency versions.
- Use `tmpfs`, small pinned images and session scope for speed.
- Collect logs before teardown; verify no containers, networks or volumes leaked.
- Docker API access for test libraries is root-equivalent; keep it on isolated runners ([§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).

## 14. Related Concepts & What's Next

Related: health checks and dependency ordering ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), Compose profiles ([§38](../Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)), CI environments ([§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)), the build-and-push flow this stage guards ([§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), and pruning ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)). Next, [§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md) covers how a tested, signed image digest is promoted through environments with GitOps.

**Next Section:** [§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md) — `Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md`

# Section 121 (Part 16): Scenario-Based Production Troubleshooting Questions

This bank targets "here's a broken production system, walk me through diagnosing it live" questions. Every model answer below explicitly applies §87's structured troubleshooting methodology step by step — narrating the diagnostic process in order, not jumping straight to the eventual conclusion — because demonstrating _how_ you reason under an active incident is the actual point of a scenario question, distinct from a knowledge-recall question.

## 1. Application and Service-Layer Scenarios

**Scenario:** _"A web service is returning intermittent 502 errors under load. Walk me through your diagnosis."_

**Model answer:** Following §87's methodology, I'd start by establishing scope and gathering facts before touching anything — is this every request or a fraction, is it correlated with a specific time window or load level, is it one host or the whole fleet? A 502 specifically means the reverse proxy/load balancer got no valid response from the upstream, so the first branch point is application-layer versus infrastructure-layer: I'd check the application's own logs (§85) first for errors, exceptions, or slow requests around the timestamps of the 502s — if the app logged nothing unusual at all for those windows, that's a strong signal the upstream never received or never finished the request, pointing toward infrastructure rather than application logic. Next I'd check basic resource saturation on the affected host(s) — load average and CPU (§81), since a request that never gets CPU time to be serviced looks exactly like this symptom, and memory (§82), since an application close to being OOM-killed or heavily swapping produces the same intermittent failure pattern. If resources look fine, I'd move to connection and socket state with `ss` (§55) — checking for exhausted connection pools, sockets stuck in `SYN-RECV` or accumulating in `TIME-WAIT`, or the backlog queue for the app's listening socket being full, since a full accept queue causes exactly this "request arrives, times out before the app picks it up" behavior under load. I'd also check whether the 502 rate correlates with a specific upstream worker count or process pool size — a common root cause is the application's own worker/thread pool being undersized for the load, so requests queue past the load balancer's timeout even though the app isn't crashing. I'd only propose a fix once I'd isolated which of these layers was actually implicated, rather than guessing.
_What this probes for:_ Whether the candidate follows an ordered elimination process (logs → resources → connection state → application configuration) instead of guessing at a fix, and correctly identifies that "502" specifically implicates the upstream/proxy boundary rather than defaulting straight to "the app has a bug."

_Diagnostic steps in order:_

1. Establish scope — fraction affected, time correlation, one host vs. fleet-wide.
2. Check application logs (§85) for errors/slowness at the exact 502 timestamps.
3. Check host resource saturation — load/CPU (§81), memory (§82).
4. Check socket/connection state with `ss` (§55) — pool exhaustion, backlog, `TIME-WAIT` buildup.
5. Correlate with worker/thread pool sizing before proposing a fix.

**Scenario:** _"A service that was working fine yesterday is now failing to start after a routine deployment. How do you diagnose it?"_

**Model answer:** I'd start with the most direct evidence available rather than speculating about what the deployment changed: `systemctl status` on the unit (§66) to see the actual failure state, followed immediately by `journalctl -u <service>` (§68) for the specific error the service or systemd logged on the failed start attempt — this alone often names the exact problem (missing dependency, config syntax error, permission issue, port already in use). If the logs are inconclusive, I'd diff what actually changed in the deployment — new unit file, new config, new binary/version, new environment variables (§71) — against the previous known-good state, since "routine deployment" plus "broken start" strongly suggests the deployment introduced the regression rather than an unrelated coincidence. I'd check dependency ordering next (`After=`/`Requires=` in the unit file, §67) in case the deployment changed something the service depends on being available first. If the service depends on a port or resource, I'd verify nothing else is holding it (a stuck previous process instance, or a port conflict). Throughout, I'd resist restarting things repeatedly hoping it resolves itself — that destroys the evidence trail the logs would otherwise preserve, which §87 flags as a common way root cause becomes unrecoverable after the fact.
_What this probes for:_ Going straight to authoritative sources (`systemctl status`, `journalctl`) rather than guessing, correlating the failure with what specifically changed in the deployment, and recognizing that repeated blind restarts destroy diagnostic evidence.

_Diagnostic steps in order:_

1. `systemctl status` on the unit, then `journalctl -u <service>` for the exact failure reason.
2. Diff the deployment's actual changes (unit file, config, binary, env vars, §71) against known-good.
3. Check dependency ordering (`After=`/`Requires=`, §67) for a newly-broken assumption.
4. Verify no stale process or conflicting service is holding a required port or resource.
5. Avoid repeated blind restarts that would destroy the evidence trail.

## 2. Network and Access Scenarios

**Scenario:** _"A host suddenly can't resolve DNS for external hostnames, but internal hostnames still resolve fine. Walk through your diagnosis."_

**Model answer:** The fact that internal resolution still works is the most important clue and immediately narrows the search — it rules out the resolver process being fully down and rules out a total network-layer outage, since some resolution path is clearly still functioning. Following §53's DNS troubleshooting flow, I'd first check `/etc/resolv.conf` to confirm which nameservers the host is actually configured to query, and `/etc/nsswitch.conf` to confirm the hosts/DNS resolution order hasn't been altered — if internal hostnames resolve via `/etc/hosts` or an internal-only resolver while external ones go through a different (possibly now-unreachable) upstream nameserver, that split explains the symptom directly. Next I'd test the external nameserver's reachability directly with `dig` or `curl` against its IP, bypassing the resolver library, to distinguish "the nameserver is unreachable" from "the nameserver is reachable but not answering" from "the query never leaves the host at all." If the nameserver is unreachable, I'd check routing and firewall rules (§54) for anything that changed recently — an updated `iptables`/`nftables` rule or a security-group change that started blocking outbound port 53 would produce exactly this symptom while leaving internal name resolution (which may not need to leave the host or subnet at all) unaffected. I would not assume the DNS server itself is broken until I'd confirmed the host can actually reach it at the network layer first.
_What this probes for:_ Using the internal-works/external-fails split as a genuine diagnostic clue rather than noise, checking configuration (`resolv.conf`, `nsswitch.conf`) before assuming server-side failure, and correctly separating "can't reach the resolver" from "resolver reachable but not resolving."

_Diagnostic steps in order:_

1. Treat internal-works/external-fails as a scoping clue, not noise.
2. Check `/etc/resolv.conf` and `/etc/nsswitch.conf` for the configured resolution path.
3. Test the external nameserver's IP directly with `dig`/`curl`, bypassing the resolver library.
4. Check firewall/routing rules (§54) for a recent change blocking outbound port 53.
5. Confirm reachability before concluding the nameserver itself is broken.

**Scenario:** _"SSH access to a production host is suddenly refused. Walk through your diagnosis, considering every layer that could be responsible."_

**Model answer:** "Refused" is itself a clue worth pausing on before diagnosing further — a connection actively refused (versus timing out) generally means something at the destination is responding negatively rather than the packet vanishing, so I'd start there. Per §56/§90's SSH troubleshooting and hardening context, I'd work outward from the host: first, is `sshd` itself actually running (via any out-of-band access I have — console, cloud provider serial access, or another host that can reach it) — a crashed or failed-to-restart `sshd` after a config change is a common and simple explanation, and `journalctl -u sshd` would show it immediately if reachable another way. If `sshd` is running, I'd check `/etc/ssh/sshd_config` for a recent change — an overly strict `AllowUsers`/`AllowGroups`, a changed `ListenAddress`, or a bad `Match` block can lock out exactly the access pattern being attempted while leaving the daemon technically up. Next I'd check the firewall layer (§54) — a new `iptables`/`nftables`/security-group rule that started blocking port 22, possibly from an unrelated hardening change applied fleet-wide, would produce this exact symptom across multiple hosts at once, which is itself a useful clue (one host vs. many narrows whether this is host-specific or fleet-wide policy). I'd also specifically check for a `fail2ban` lockout (§90) — if the connecting IP recently failed authentication repeatedly (a stale credential, a monitoring tool misconfigured to keep retrying with bad keys), `fail2ban` would legitimately and correctly be blocking it, which looks identical to "SSH is broken" from the client side but has a completely different fix (unban the IP, fix the underlying repeated-auth-failure source) than a config or firewall problem. I'd work through these in order — daemon state, then `sshd_config`, then firewall, then `fail2ban` — rather than assuming any single one without evidence.
_What this probes for:_ Systematically covering every plausible layer (daemon crash, config lockout, firewall, fail2ban) rather than fixating on the first hypothesis, and recognizing that "refused" versus "times out" is itself diagnostic information.

_Diagnostic steps in order:_

1. Note "refused" vs. "timed out" as itself diagnostic before investigating further.
2. Confirm via out-of-band access whether `sshd` is actually running.
3. Check `sshd_config` for a recent lockout-causing change (`AllowUsers`, `ListenAddress`, `Match` blocks).
4. Check the firewall layer (§54) for a new rule blocking port 22, and whether it affects one host or many.
5. Check for a `fail2ban` lockout (§90) tied to recent repeated authentication failures.

## 3. Resource and Storage Scenarios

**Scenario:** _"Disk I/O latency spiked and an application became unresponsive. How do you find the cause?"_

**Model answer:** Following §83's disk I/O diagnostic flow within §87's broader methodology, I'd first confirm the symptom quantitatively rather than trusting the vague "unresponsive" report — `iostat -x` to check `%util`, average queue size, and `await` time on the relevant device, which tells me whether the disk itself is actually saturated versus the application being stuck for an unrelated reason that merely looks like an I/O problem from the outside. If the device is genuinely saturated, I'd use `iotop` to identify which process is generating the I/O — this is often the fastest way to separate "the application itself is doing excessive I/O" from "something else on the same host, like a backup job, log rotation, or another tenant's process, is competing for the same disk." I'd check `df`/`du` (§84) at the same time in case the actual issue is a nearly-full filesystem, since some filesystems suffer serious performance degradation as they approach capacity, which presents as an I/O-latency problem but has a completely different root cause and fix (free space) than a genuinely overloaded disk. If a specific process is identified as the I/O source, I'd check whether that's expected application behavior under the current load or a regression — a recent code or configuration change that turned an in-memory operation into a disk-bound one, or a missing index that turned a database query into a full scan, are common root causes I'd specifically ask about rather than treating the I/O spike as an unexplained act of nature. Throughout, I'd keep the unified performance model (§80) in mind — I would not stop at "disk I/O is high" without also checking whether high I/O wait is itself elevating load average and starving other work of CPU, since these resources interact rather than failing independently.
_What this probes for:_ Using `iostat`/`iotop`/`df` in the right order to move from "is this really disk-bound" to "which process" to "why," rather than assuming the vague symptom description immediately confirms disk I/O as the cause without verification.

_Diagnostic steps in order:_

1. Confirm the symptom quantitatively with `iostat -x` (`%util`, queue size, `await`).
2. Identify the responsible process with `iotop`, separating the app from competing processes on the same host.
3. Check `df`/`du` (§84) in case a near-full filesystem, not raw I/O saturation, is the real cause.
4. Determine whether the I/O source is expected load or a regression (missing index, new disk-bound code path).
5. Check whether elevated I/O wait is also starving CPU, since resources interact (§80).

**Scenario:** _"A host's memory usage has been climbing steadily for days and the OOM killer just terminated an important process. Walk through your diagnosis of the underlying cause."_

**Model answer:** I'd first confirm what actually happened before investigating why, checking `dmesg`/`journalctl` for the OOM killer's own log entry — it records which process was selected and the memory state at the time, which is authoritative ground truth rather than something to infer secondhand. Per §82's memory analysis and §87's methodology, I'd next use `free` and `/proc/meminfo` to understand the current memory breakdown — how much is genuinely used by processes versus page cache (which the kernel reclaims under pressure and generally isn't the real problem) versus swap usage, since a host thrashing in swap presents very differently from one with a genuine process-level leak. Given the "climbing steadily for days" pattern specifically, I'd suspect a memory leak in a long-running process rather than a sudden spike, so I'd look at per-process RSS growth over time (via historical monitoring data if available, §86, or `ps`/`smem` snapshots if not) to identify which process's memory footprint is monotonically increasing rather than fluctuating with load — a fluctuating footprint that tracks request volume is normal; one that only ever grows regardless of load is the signature of a leak. Once I've identified the leaking process, the immediate mitigation (restart it, ideally with monitoring to catch the next OOM event well before it recurs) is separate from the actual fix, which requires whoever owns that service's code to find and patch the leak — I'd make sure the incident isn't considered closed just because the immediate symptom (the OOM kill) stopped recurring after a restart bought temporary headroom.
_What this probes for:_ Correctly separating page cache from genuinely leaked memory, using the multi-day growth pattern as a specific clue pointing to a leak rather than a load spike, and not confusing "the immediate symptom stopped" with "the root cause is fixed."

_Diagnostic steps in order:_

1. Confirm the OOM event itself via `dmesg`/`journalctl` before investigating a cause.
2. Break down `free`/`/proc/meminfo` into process usage, page cache, and swap.
3. Look at per-process RSS growth over days to confirm a monotonic leak vs. load-correlated fluctuation.
4. Mitigate immediately (restart the leaking process) while treating that as separate from the actual code fix.
5. Keep the incident open until the underlying leak is patched, not just until the OOM stops recurring.

## 4. Fleet-Wide and Capacity Scenarios

**Scenario:** _"A fleet-wide alert fires showing elevated error rates across many hosts at the same moment. How do you diagnose something that's hitting the whole fleet simultaneously rather than one host?"_

**Model answer:** A simultaneous, fleet-wide onset is itself the most important clue — per §87's methodology, I'd treat "many hosts, same moment" as evidence pointing away from a single host's hardware or local state and toward something shared: a shared dependency (a database, a downstream service, a shared config/secret store), a fleet-wide change (a deployment, a config push, a certificate expiring simultaneously everywhere), or an upstream network/DNS issue affecting every host identically. I'd check first whether the timing lines up exactly with any recent fleet-wide change — a deployment rollout, a configuration management run, a certificate rotation — since coincidental timing this precise is a strong signal of causation rather than an unrelated simultaneous failure. If nothing correlates with a recent change, I'd check the shared dependency each affected host talks to (§85's centralized logging would show whether errors cluster around calls to one specific downstream service) rather than investigating each host individually, since investigating N hosts independently for a problem with one shared root cause wastes time proportional to fleet size for no additional insight. I'd also check whether the alert itself is accurate — a monitoring or alerting pipeline bug can itself produce a false fleet-wide signal, which is worth ruling out early rather than chasing a phantom incident.
_What this probes for:_ Whether the candidate recognizes that simultaneous fleet-wide symptoms point to a shared cause rather than N independent host problems, and correctly starts the investigation at the shared dependency or recent fleet-wide change rather than per-host inspection.

_Diagnostic steps in order:_

1. Treat "many hosts, same moment" as evidence of a shared cause, not N coincidental independent failures.
2. Check for exact timing correlation with a recent fleet-wide change (deploy, config push, cert rotation).
3. Check the shared downstream dependency every affected host talks to, via centralized logs (§85).
4. Rule out a false alert from the monitoring pipeline itself before chasing a phantom incident.
5. Avoid investigating each host independently when the pattern already points to one shared root cause.

**Scenario:** _"Capacity metrics look fine on paper — CPU, memory, and disk are all comfortably under their thresholds — but the service still visibly degrades every time there's a traffic spike. How do you diagnose this?"_

**Model answer:** This is a case where the standard resource metrics (§80/§81/§82) are telling the truth but aren't measuring the actual bottleneck, so I'd widen the investigation rather than re-checking the same three metrics harder. Per §87's methodology, I'd look at concurrency and queueing limits that don't show up in CPU/memory graphs at all — application-level connection pool size, thread/worker pool size, database connection limits, and OS-level limits like open file descriptors (`ulimit`) or the network stack's listen backlog — any of which can saturate and cause queuing/rejection while the host's raw CPU and memory sit comfortably idle. I'd check `ss` (§55) for connections stuck in a particular state during the spike, and check the application's own internal queue depth or thread-pool utilization metrics if they exist, since a request queuing behind an undersized worker pool produces exactly this symptom (visible user-facing degradation, invisible host-level resource pressure). I'd also check whether the degradation correlates with a downstream dependency's own capacity limit — the service in question might be perfectly healthy while it's actually waiting on a database or external API that's the one actually saturating during the spike, which requires checking that dependency's own metrics rather than assuming the problem is local.
_What this probes for:_ Recognizing that "resource metrics look fine" doesn't rule out a bottleneck — concurrency limits, connection pools, and downstream dependencies are common causes of exactly this pattern, and a candidate who only knows to check CPU/memory/disk will get stuck here.

_Diagnostic steps in order:_

1. Accept that CPU/memory/disk being fine doesn't rule out a bottleneck — widen scope rather than re-checking the same metrics.
2. Check concurrency limits invisible to resource graphs — connection pools, worker/thread pools, file-descriptor ulimits, listen backlog.
3. Check `ss` (§55) for connection-state buildup specifically during the spike window.
4. Check the application's own internal queue-depth/pool-utilization metrics if instrumented.
5. Check whether a downstream dependency, not the host itself, is the actual saturation point.

## 5. Quick-Reference Cross-Index

| #   | Scenario (short form)                                     | Group                         | Primary roadmap ties    |
| --- | --------------------------------------------------------- | ----------------------------- | ----------------------- |
| 1   | Intermittent 502s under load                              | Application and Service-Layer | §55, §81, §82, §85, §87 |
| 2   | Service fails to start after routine deployment           | Application and Service-Layer | §66, §67, §68, §71, §87 |
| 3   | External DNS fails, internal DNS still works              | Network and Access            | §53, §54, §87           |
| 4   | SSH access suddenly refused                               | Network and Access            | §54, §56, §90, §87      |
| 5   | Disk I/O latency spike, application unresponsive          | Resource and Storage          | §80, §83, §84, §87      |
| 6   | Steady multi-day memory growth ending in an OOM kill      | Resource and Storage          | §82, §86, §87           |
| 7   | Fleet-wide error-rate alert, many hosts at once           | Fleet-Wide and Capacity       | §85, §87                |
| 8   | Degradation under load despite "healthy" resource metrics | Fleet-Wide and Capacity       | §55, §80, §81, §82, §87 |

## 6. Key Takeaways

- Every diagnostic answer in this bank follows an explicit ordered sequence (gather facts → narrow scope → test a specific hypothesis → confirm before fixing) per §87 — jumping straight to a fix without narrating the process is exactly what these questions are designed to catch.
- Symptom framing itself is often diagnostic — "refused" vs. "timed out," "internal resolves but external doesn't," "climbing over days" vs. "sudden spike," "many hosts at once" vs. "one host" — each points the investigation in a specific, different direction before any command is even run.
- The right diagnostic order typically moves from cheap, authoritative, non-destructive checks (logs, `systemctl status`, `iostat`) toward more specific hypothesis testing, and never starts with a destructive or state-changing action (restarting a service, banning an IP) before the evidence justifies it.
- Several scenarios have multiple plausible root causes at different layers (SSH refusal: daemon, config, firewall, or fail2ban) — a strong answer checks each layer in order rather than fixating on the first guess.
- A simultaneous fleet-wide symptom points to a shared cause, not N independent host problems, and "resource metrics look fine" does not rule out a concurrency-level or downstream-dependency bottleneck.
- "The symptom stopped" is not the same as "root cause is fixed" — a restarted leaking process or a rebooted thrashing host is a mitigation, not a resolution, and the diagnostic process should be explicit about that distinction.

## 7. Related Concepts & What's Next

These scenarios apply §87's structured troubleshooting methodology and §83/§85's diagnostic tooling to fresh scenarios distinct from §88's five incident case studies (disk full, memory leak, fork bomb, network saturation, zombie apocalypse) — read together, §88 and this section cover a broad spread of realistic production failure modes without duplicating each other. §122 (next, and the final section of Part 16) shifts from technical diagnosis to the behavioral and hiring-manager-style questions that surround these same incidents — how you communicate about and learn from exactly this kind of troubleshooting work.

**Next Section:** §122 — `Section-122-Part16-Hiring-Manager-Behavioral-Technical-Crossover-Questions.md`

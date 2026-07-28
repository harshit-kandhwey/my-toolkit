# Section 87 (Part 11): Structured Troubleshooting Methodology and Runbooks

## 1. Overview: Tools Without a Method Are Just Noise

§80–§86 built up a substantial toolkit — CPU, memory, disk, and network analysis commands, logging tooling, and syscall/CPU-cycle-level tracing. None of that tooling, on its own, tells an engineer what order to reach for it in, when to stop looking at one resource and check another, or when to stop diagnosing entirely and just follow a known procedure. This section is the organizing layer on top of §81–§86's tools: a structured method for approaching an unfamiliar problem, and the discipline that turns a one-off diagnosis into a reusable runbook for next time.

## 2. Why Structured Methodology Beats Ad-Hoc Investigation Under Pressure

It's a common instinct, especially under production pressure with people waiting for an answer, to feel like a structured method is a luxury — that stopping to think through a framework is slower than just diving in and trying things. In practice the opposite is usually true, and it's worth being explicit about why:

- **Ad-hoc investigation re-checks the same things repeatedly.** Without a checklist or framework, it's easy to look at CPU, get distracted, look at something unrelated, come back to CPU again ten minutes later having forgotten what was already ruled out — structure prevents this kind of circular, wasted motion.
- **Ad-hoc investigation jumps to conclusions from partial evidence.** Seeing one elevated metric and immediately declaring it "the cause" without checking whether it's actually correlated with the reported symptom, or whether it's a normal-for-this-workload baseline, leads to fixing the wrong thing while the real cause continues.
- **A repeatable method is faster specifically because it's not random.** It might feel more deliberate and slower in the first sixty seconds, but a method that systematically narrows the problem space converges on the actual cause faster than an unstructured search that has no way to know when it's covered everything.

The rest of this section builds out the concrete method — the USE method (3) as the resource-level framework, top-down/bottom-up (4) as a framing for where to start, and hypothesis-driven testing (5) as the discipline that governs each individual step.

## 3. The USE Method: Utilization, Saturation, Errors

The **USE method** — coined by Brendan Gregg — is a systematic checklist for characterizing the health of any resource: for every resource in the system, ask three questions:

- **Utilization** — how busy is this resource, as a percentage of its capacity over a time interval? (CPU: percent non-idle time. Disk: percent of time doing I/O. Network interface: percent of link bandwidth in use.)
- **Saturation** — is there a backlog or queue building because demand exceeds what the resource can currently service? (CPU: run queue length / load average beyond core count. Disk: I/O queue depth. Network: packet drops due to buffer overflow.)
- **Errors** — are there actual error events, distinct from mere slowness? (Disk: read/write errors. Network: interface errors, retransmits, checksum failures. Memory: ECC errors, though this is less commonly checked at the OS level.)

The reason this ordering and framing matters: **utilization alone is an incomplete picture**. A CPU sitting at 60% utilization looks "fine" by a naive read, but if the run queue shows several processes waiting for a core (saturation), the system is already contending, even at moderate utilization — and utilization figures alone would miss it entirely. Conversely, near-100% utilization on a resource with an empty queue and no waiting processes might be entirely healthy if it's simply completing all demand within budget. USE forces checking saturation and errors, not just the utilization number that's easiest to glance at.

**Applying USE with §81–§84's actual tools, resource by resource:**

| Resource | Utilization                                       | Saturation                                                                    | Errors                                                           |
| -------- | ------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| CPU      | `top`/`mpstat` non-idle percentage (§81)          | Load average vs. core count, run-queue column in `vmstat` (§81)               | Rare at OS level; more relevant in specialized hardware contexts |
| Memory   | `free` used vs. total, `/proc/meminfo` (§82)      | Swap activity, OOM Killer invocations (§82)                                   | `dmesg`/journal entries for memory-related kernel errors         |
| Disk I/O | `iostat` `%util` (§83)                            | `iostat` queue depth / await time, `iotop` for per-process contribution (§83) | `dmesg`/SMART data for actual read/write failures                |
| Network  | `sar`/`iftop`/`nload` bandwidth utilization (§84) | Interface drop counters, `ss` retransmit stats (§84)                          | Interface error counters via `ip -s link` or `ethtool -S`        |

Walking every resource through all three questions, rather than fixating on the first metric that looks elevated, is what makes USE a genuine method rather than just a list of commands to run.

> 💡 **Tip:** USE is deliberately resource-first, not symptom-first — it's the systematic sweep to run when the top-down entry point (4) hasn't yet pointed at an obvious culprit, or as a final confirmation pass even after a hypothesis has formed, to make sure a plausible-looking cause isn't actually a coincidental correlation.

## 4. Top-Down vs. Bottom-Up: Two Valid Entry Points

Not every investigation starts from the same place, and neither starting point is inherently superior — the right one depends on what information is available first.

- **Top-down (symptom-first)** starts from what was reported — a user complaint, an alert, a monitoring dashboard showing elevated latency on a specific endpoint — and works downward: which service handles that endpoint, which host(s) it runs on, and only then which resource on that host might explain it. This is the natural entry point when an incident starts from monitoring or a user report, since that's the information actually in hand.
- **Bottom-up (resource-first)** starts from the lowest-level resource metrics — running the USE sweep (3) across CPU/memory/disk/network on a suspect host without yet knowing which specific symptom to attribute it to — and works upward toward which service or request pattern the anomaly actually affects. This is the natural entry point when a host itself is flagged as unhealthy (by fleet-wide monitoring, for instance) before any specific user-facing symptom has been reported.

In practice a real investigation often moves in both directions during the same incident — starting top-down from a reported symptom, narrowing to a host, then switching to bottom-up USE sweeping on that host once there, before coming back up to confirm the resource finding actually explains the originally reported symptom (rather than being an unrelated coincidence discovered along the way).

## 5. Hypothesis-Driven Testing: Change One Thing, Verify, Then Move On

A genuinely important production discipline, easy to state and easy to abandon under pressure: **form a specific, falsifiable hypothesis about the cause, change exactly one thing to test it, and verify the result before moving to the next idea** — rather than making several changes at once or trying fixes without a clear expectation of what should happen if the hypothesis is correct.

Why this matters in practice:

- **Changing multiple things at once destroys attribution.** If three configuration changes go out together and the symptom resolves, there's no way to know which one (or which combination) actually mattered — which means the same problem can recur later with no confirmed fix on record, and unrelated changes may have introduced new risk for no benefit.
- **A hypothesis with no clear falsification criterion isn't testable.** "Maybe it's the network" is not a hypothesis a specific action can confirm or rule out; "if this is TCP retransmission-driven, `ss -i` should show elevated retransmit counts on affected connections" is — it names the exact check that would prove or disprove it before any change is even made.
- **Verifying before moving on prevents false confidence.** A change that coincides with the symptom subsiding isn't the same as a change confirmed to have caused the improvement — especially for intermittent issues, where the symptom might have resolved on its own regardless of the change made.

This discipline is what keeps top-down/bottom-up investigation (4) and USE sweeps (3) from turning into an unfocused fishing expedition — the frameworks narrow where to look, and hypothesis-driven testing governs what to actually do once a specific suspect is identified.

## 6. Runbooks: The Artifact This Methodology Produces

Everything in 2–5 is the process for **diagnosing something new** — a problem that hasn't been seen before, or at least hasn't been documented. A **runbook** is the opposite case: a documented, repeatable procedure for a **known, recurring** problem, written once (typically as the output of applying this section's methodology the first time a problem occurs) and then followed directly on subsequent occurrences without re-deriving the diagnosis from scratch.

The distinction matters operationally:

- **This section's methodology is for the unknown.** USE sweeps, top-down/bottom-up framing, and hypothesis testing are tools for narrowing down a cause nobody has documented yet.
- **A runbook is for the known.** Once a specific recurring failure mode is understood — a particular service's memory growth pattern that needs a scheduled restart, a specific disk-fill pattern from a known noisy log source, a known network flap tied to a specific upstream dependency — the runbook captures the diagnostic checks and remediation steps directly, so the next person (or the same person, months later, without full context loaded) doesn't need to rediscover the reasoning.

**Why maintaining runbooks matters for on-call sustainability:** on-call work is fundamentally more sustainable when recurring problems have a documented, followable procedure rather than depending on whichever engineer happens to remember how it was solved last time. Runbooks reduce the cognitive load of an on-call shift (following a checklist under a 3 a.m. page is far less error-prone than re-deriving a diagnosis half-awake), and they're a direct knowledge-transfer mechanism — a new team member can handle a known recurring issue competently on day one if a runbook exists for it, rather than needing months of tribal-knowledge accumulation. A team that only ever diagnoses from scratch, never converting a solved problem into a documented runbook, is paying the full diagnostic cost every single time the same issue recurs — a cost that scales with how often the problem repeats, which structured runbook maintenance converts into a one-time investment instead.

**What a useful runbook entry typically contains**, at minimum:

| Field                         | Purpose                                                                                                     |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Symptom / trigger             | What alert, error, or observation should cause someone to reach for this runbook                            |
| Diagnostic steps              | Exact commands to run to confirm this is indeed the known issue, not a superficially similar one            |
| Remediation steps             | The exact, tested sequence of actions to resolve it                                                         |
| Owning team / escalation path | Who to page if the runbook's steps don't resolve it                                                         |
| Last verified date            | When someone last confirmed the runbook still matches reality — the field most likely to go stale unnoticed |

That last field matters as much as the procedure itself, for exactly the reason the Warning below explains.

> ⚠️ **Warning:** A runbook that's gone stale — written against an older version of a service, referencing a tool or host that no longer exists, or based on a root cause that was only partially understood at the time — can be more dangerous than no runbook at all, because on-call engineers under pressure tend to trust and follow a documented procedure without re-verifying its assumptions. Runbooks need periodic review as part of ongoing operational hygiene, not a write-once artifact.

## 7. Hands-On: Running a USE Sweep Against an Unfamiliar Host

**Purpose:** Apply the USE method (3) as a concrete, repeatable checklist against a host with an unknown or unreported problem — the bottom-up entry point from 4 — using nothing but §81–§84's tools in one deliberate pass rather than jumping between them at random.

```bash
# CPU: utilization, saturation, errors
mpstat 1 5
uptime          # load average vs. nproc for saturation
nproc

# Memory: utilization, saturation, errors
free -h
vmstat 1 5      # si/so columns for swap saturation
dmesg | grep -i 'out of memory'

# Disk: utilization, saturation, errors
iostat -xz 1 5  # %util for utilization, avgqu-sz/await for saturation
dmesg | grep -iE 'error|fail' | grep -i sd

# Network: utilization, saturation, errors
sar -n DEV 1 5
ip -s link      # drop/error counters per interface
```

**Expected output:** A structured pass across all four resources, each checked for all three USE dimensions rather than stopping at the first elevated number — for example, `mpstat` showing moderate CPU utilization alongside `uptime`'s load average well above `nproc`'s core count is the saturation signal that utilization alone would have missed.

**Production usage example:** This sweep is the concrete bottom-up half of an investigation that started top-down from a vague "host X seems unhealthy" alert with no specific symptom attached yet — running it once, systematically, and recording which resource (if any) shows both elevated utilization and saturation is far faster than alternating between tools reactively as each new thought occurs.

**Common errors:** Stopping at the first tool that shows an elevated number without checking the other three resources — a CPU-bound-looking symptom can coexist with (or actually be caused by) disk saturation forcing processes into uninterruptible sleep, which raises load average without raising CPU utilization in the way it first appears to.

**Troubleshooting:** If no resource shows a clear USE signal despite a real reported symptom, the bottleneck may be at the application layer (a slow downstream dependency, a lock, a connection pool) rather than a host-level resource at all — that's the point at which §86's `strace`/`perf` tracing tools, or an APM view if available, become the right next step rather than continuing to re-run the same USE sweep.

## 8. Common Misconceptions

1. **"Structured methodology is slower than just diving in."** It feels more deliberate in the first moments of an investigation, but it converges on the actual cause faster than unstructured searching precisely because it doesn't re-check the same things repeatedly or chase coincidental correlations (2).
2. **"High utilization always means a resource is the bottleneck."** Utilization alone is incomplete — the USE method's saturation and error dimensions exist specifically because a resource can look busy without actually queuing work, or can be genuinely contended even at moderate utilization if saturation is present (3).
3. **"Top-down and bottom-up are competing approaches — pick the correct one."** They're complementary entry points suited to different starting information, and real investigations frequently use both in sequence within the same incident (4).
4. **"A runbook and a troubleshooting method are the same thing."** A runbook is the documented output for a specific known, recurring problem; the methodology in 2–5 is for diagnosing something that hasn't been solved and documented yet — conflating the two leads to either over-documenting one-off problems or under-documenting genuinely recurring ones (6).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What are the three things the USE method asks about a resource?"_
**Model answer:** Utilization (how busy is it as a percentage of capacity), Saturation (is there a backlog/queue building because demand exceeds capacity), and Errors (are there actual error events, distinct from slowness). Applying all three to CPU, memory, disk, and network is more reliable than looking only at utilization, since a resource can be saturated and contended even without extreme utilization, or can be highly utilized without actually being a problem.
_What the interviewer is probing for:_ Correct recall of the three dimensions and understanding why utilization alone is insufficient.

**🎯 Intermediate:** _"Walk me through how you'd apply the USE method to a report that an application feels 'slow' with no other detail."_
**Model answer:** I'd start top-down from the symptom — confirm what "slow" actually means (which operation, how slow compared to baseline) and identify the host(s)/service(s) involved — then switch to bottom-up USE sweeps on those hosts: CPU utilization and run-queue saturation via `top`/`vmstat`, memory usage and swap/OOM activity via `free`/`/proc/meminfo`, disk `%util` and queue depth via `iostat`, and network utilization/drops via `sar`/`ss`. I'd check all three dimensions per resource rather than stopping at the first elevated utilization number, since I want to rule out saturation-without-high-utilization scenarios too. Once a resource shows a clear utilization-plus-saturation signal, I'd form a specific hypothesis about why and test it with one change at a time before declaring it the root cause.
_What the interviewer is probing for:_ Ability to actually combine top-down entry with a systematic bottom-up USE sweep, not just recite the acronym.

**🎯 Senior:** _"Why is changing one thing at a time during an incident considered a discipline worth enforcing, even when pressure is high to fix things fast?"_
**Model answer:** Because under pressure the temptation to make several plausible changes simultaneously is strong, but it destroys attribution — if the symptom resolves after three simultaneous changes, there's no confirmed understanding of which one mattered, which means the fix isn't actually verified and the problem can recur with no reliable remediation on record. It also risks introducing unrelated changes' side effects with no diagnostic benefit gained. Enforcing one-change-at-a-time with explicit verification before the next step is slower per-step but produces an actually-confirmed root cause and fix, which is what eventually becomes the input to a runbook (6) — an unconfirmed multi-change "fix" can't reliably be turned into a repeatable procedure for next time.
_What the interviewer is probing for:_ Understanding that this discipline isn't just methodological purism — it directly enables reliable runbook creation and prevents recurrence with no known fix.

**🎯 Architect:** _"How do you decide when a solved problem should become a runbook, and how do you keep runbooks from becoming a liability?"_
**Model answer:** I'd convert a diagnosis into a runbook once a problem shows signs of being recurring rather than one-off — either it's already happened more than once, or its root cause (a known resource-exhaustion pattern, a known dependency's failure mode) is structurally likely to recur even if this is the first occurrence. The runbook should capture the specific diagnostic checks that confirmed the cause and the exact remediation steps, written so someone without full incident context can follow it under pressure. To prevent staleness from becoming a liability, I'd tie runbook review into regular operational hygiene — revisiting runbooks when the underlying service or infrastructure changes materially, and explicitly flagging any runbook that hasn't been exercised or reviewed in a long time as needing re-validation before being trusted blindly during the next occurrence, since a stale runbook followed uncritically under pressure can be actively worse than reasoning from scratch.
_What the interviewer is probing for:_ Judgment about when documentation investment is worthwhile, and awareness that runbooks carry their own maintenance burden and failure mode if neglected.

## 10. Key Takeaways

- Structured troubleshooting methodology outperforms ad-hoc investigation under pressure precisely because it avoids re-checking the same things and jumping to conclusions from partial evidence (2).
- The USE method (Utilization, Saturation, Errors) applied to every resource — CPU, memory, disk, network, using §81–§84's tools as the concrete instruments — avoids the trap of trusting utilization alone (3).
- Top-down (symptom-first) and bottom-up (resource-first) are complementary entry points, not competing approaches — real investigations often use both within a single incident (4).
- Hypothesis-driven testing — one change at a time, verified before moving on — preserves attribution and is what makes a diagnosis reliable enough to eventually become a runbook (5).
- A runbook documents a repeatable procedure for a known, recurring problem — distinct from this section's methodology, which is for diagnosing something new — and needs ongoing review to avoid becoming a stale, falsely trusted liability (6).

## 11. Related Concepts & What's Next

This section provides the full depth behind the USE method §80 first introduced at the start of this Part, and it's the organizing framework for every tool §81–§86 covered — CPU/memory/disk/network analysis, logging, and tracing are the concrete instruments this methodology directs toward a specific investigation. §88 (next, the final section of this Part) applies this exact methodology to five concrete, worked incident case studies — disk full, memory leak, fork bomb, network saturation, and a zombie-process pileup — turning the abstract method into applied practice.

**Next Section:** §88 — `Section-88-Part11-Incident-Case-Studies.md`

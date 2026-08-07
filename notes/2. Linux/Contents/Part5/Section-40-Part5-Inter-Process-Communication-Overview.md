# Section 40 (Part 5): Inter-Process Communication (IPC) Overview

## 1. Why IPC Exists at All

[§34](./Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md) established the process model this section leans on directly: every process gets its own isolated virtual address space, and by default one process cannot read or write another process's memory at all — that isolation is a deliberate safety and stability property of the kernel, not an oversight. Two processes crashing into each other's memory would be catastrophic for reliability, so the kernel enforces the wall by default.

The problem is that cooperating processes routinely need to exchange data anyway — a shell pipeline where one program's output becomes another's input, a web server handing a connection off to a worker, two daemons coordinating state. **Inter-Process Communication (IPC)** is the umbrella term for the kernel-provided mechanisms that deliberately punch a controlled hole through that isolation, on purpose, so processes can exchange data without the kernel giving up the safety of isolated memory as the default.

This section stays **conceptual** — the goal is to know what each mechanism is, roughly how it behaves, and when it's the right tool, not to write syscall-level code against any of them. Two of the mechanisms covered here — shell pipes and network sockets — get substantial hands-on depth elsewhere in this roadmap ([§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md)–[§50](../Part6/Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) and [§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)–[§58](../Part7/Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) respectively); this section is what ties them together conceptually before that hands-on depth arrives.

> 💡 **Tip:** Every IPC mechanism in this section is really answering the same underlying question — "how do two processes with separate memory spaces move bytes from one to the other, and does the kernel do the copying for them?" — just with different tradeoffs around who can talk to whom, whether the channel persists, and how fast the transfer is.

## 2. Anonymous Pipes: The One You Already Use Daily

The most common form of IPC on any Linux system is one nearly every reader has already typed without necessarily framing it as IPC: the shell pipe.

```bash
$ ls | grep ".log"
```

The `|` character wires the standard output of `ls` directly to the standard input of `grep`, via a kernel-managed buffer called a **pipe**. Neither program is aware of the other by name — `ls` just writes to file descriptor 1 as always, `grep` just reads from file descriptor 0 as always, and the shell has arranged for those descriptors to point at opposite ends of the same kernel buffer instead of the terminal.

**Key properties of an anonymous pipe:**

- **Unidirectional** — data flows one way, write-end to read-end. Two-way communication between the same pair of processes needs two pipes (or a different mechanism entirely).
- **Related processes only** — an anonymous pipe has no name in the filesystem; it exists only as a pair of file descriptors, which means only a process and its descendants (created via `fork()`, [§34](./Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)) can hold the other end. A completely unrelated process, started independently, has no way to discover or connect to it.
- **In-memory, kernel-buffered** — the data never touches disk; it lives in a fixed-size kernel buffer, and a writer blocks once that buffer fills until a reader drains some of it (this is exactly why `ls | grep` can start filtering output before `ls` has finished listing everything — the two run concurrently, throttled against each other by the pipe's buffer).
- **Ephemeral** — the pipe exists only as long as both ends are open; once every process holding either end exits, the pipe and any buffered data are gone.

This is the shell-level mechanic behind everything [§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md)–[§50](../Part6/Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) covers in depth — redirection, multi-stage pipelines, `xargs` chains. This section names the underlying kernel object; Part 6 is where you build fluency actually using it.

## 3. Named Pipes (FIFOs): Pipes With a Filesystem Identity

An anonymous pipe's biggest limitation — only related processes can use it — is exactly what a **named pipe**, also called a **FIFO** (First In, First Out), removes. A FIFO is created explicitly and given a real path in the filesystem:

```bash
$ mkfifo /tmp/mypipe
$ ls -l /tmp/mypipe
prw-r--r-- 1 user user 0 Jul 26 10:00 /tmp/mypipe
```

Note the leading `p` in the permission string — that's a distinct file _type_ ([§17](../Part3/Section-17-Part3-Filesystem-Hierarchy-Standard.md)/Part 3's filesystem hierarchy coverage touches on special file types), not a regular file. It occupies zero bytes on disk; opening it for reading and writing behaves like an anonymous pipe underneath, with the same in-memory kernel buffer and blocking behavior — the only thing `mkfifo` actually adds is a **name any unrelated process can open by path**.

```bash
# Terminal A — blocks until a reader opens the other end
$ echo "hello" > /tmp/mypipe

# Terminal B — completely unrelated process, no common ancestor needed
$ cat /tmp/mypipe
hello
```

**What a FIFO does and doesn't give you:**

- It removes the "must be related processes" restriction of an anonymous pipe — any process that can see the path can open it.
- It's still fundamentally a pipe otherwise — still unidirectional, still an in-memory kernel buffer with no persistence of the data itself (the FIFO file persists in the filesystem as a named entry, but nothing written through it is stored anywhere — data not currently being read is just sitting in the kernel buffer, same as an anonymous pipe).
- Opening a FIFO for writing blocks until some process opens it for reading, and vice versa — a common beginner surprise, since it looks like an ordinary file but behaves nothing like one on open.

> ⚠️ **Warning:** A FIFO's persistent filesystem _entry_ is easy to mistake for persistent _data_ — it is not a queue or a log you can write to now and read from later whenever convenient. If nothing has the read end open when data is written, the writer simply blocks; there is no buffering-to-disk fallback the way a real message queue (6) would provide.

## 4. Sockets: Local and Network, Briefly Distinguished

A **socket** is a more general, bidirectional communication endpoint than a pipe, and it comes in two flavors that matter to distinguish here even though only one gets full depth in this roadmap:

- **Unix domain sockets** — local-only, addressed by a filesystem path (much like a FIFO), used for IPC between processes on the same host. They're bidirectional (unlike a pipe) and support both stream (reliable, ordered byte stream) and datagram (discrete message) modes. This is the mechanism behind things like Docker's `/var/run/docker.sock` — the Docker CLI and daemon talk over a Unix domain socket, not a pipe, precisely because they need two-way request/response traffic, not a one-way stream.
- **Network (Internet domain) sockets** — addressed by an IP address and port rather than a filesystem path, and capable of communicating across a network to a different host entirely, not just between processes on the same machine. TCP and UDP sockets are the foundation essentially all network communication on Linux is built on.

The conceptual distinction worth retaining here: a Unix domain socket and a network socket present a very similar programming interface, but a Unix domain socket is inherently local-machine-only and generally faster (the kernel can shortcut the full network stack since there's no actual network involved), while a network socket is what's required the moment communication needs to cross a host boundary. **Full depth on sockets — addressing, TCP vs. UDP, the three-way handshake, ports — is Part 7 ([§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)–[§58](../Part7/Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md))**, specifically the networking fundamentals and diagnostics sections; this section's job is only to place sockets on the map as an IPC mechanism and flag that "local IPC" and "network communication" are the same underlying abstraction used two different ways.

## 5. Shared Memory: The Fastest Mechanism, With a Catch

Every mechanism covered so far — pipes, FIFOs, sockets — moves data by having the kernel copy bytes from one process's buffer to another's. **Shared memory** takes a different approach entirely: instead of copying data through the kernel, the kernel maps the _same physical memory pages_ into the address spaces of multiple processes simultaneously. Once mapped, one process writing to that region is immediately visible to every other process with it mapped — no copy, no kernel mediation on each read/write, just direct memory access.

On Linux, `/dev/shm` is the most visible everyday example — a `tmpfs`-backed ([§18](../Part3/Section-18-Part3-Filesystem-Types.md)) filesystem where files are actually backed by RAM rather than disk, commonly used as a shared-memory-via-files convenience:

```bash
$ df -h /dev/shm
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           2.0G     0  2.0G   0% /dev/shm
```

**Why this is the fastest IPC mechanism available:** every other mechanism in this section involves at least one copy operation mediated by the kernel — data goes from a process's memory into a kernel buffer, then out again into the destination process's memory. Shared memory has zero copies after the initial mapping is set up; both processes are reading and writing the exact same physical RAM.

**The catch, and it's a real one:** the kernel provides the shared region and nothing else — no coordination, no locking, no notion of "whose turn it is to write." Two processes writing to the same shared memory region concurrently, without their own explicit synchronization (semaphores, mutexes, or some other agreed-upon locking scheme layered on top), produce a **race condition** — the exact class of bug this speed advantage trades for. Shared memory is fast precisely because the kernel stays out of the way, which means all the correctness work the kernel would otherwise have handled (ordering, exclusion) becomes the application's responsibility instead.

> ⚠️ **Warning:** "Fastest" is not "safest" or "simplest" — shared memory is the mechanism most likely to produce subtle, hard-to-reproduce corruption bugs if synchronization is done carelessly, because nothing about the mechanism itself prevents two processes from stepping on each other's writes mid-update. Reach for it when profiling has actually identified copy overhead as a bottleneck, not as a default choice.

## 6. Message Queues and Semaphores: The Classic System V Primitives (Conceptual Only)

Two other IPC primitives are worth knowing exist, at a purely conceptual level, because they show up in older codebases, in interview questions about IPC, and in the historical **System V IPC** family alongside System V shared memory:

- **Message queues** — a kernel-managed, persistent queue of discrete, typed messages that processes can send to and receive from, independent of whether the receiving process is running at the moment a message is sent (unlike a pipe or FIFO, which requires both ends to be actively connected). This addresses the exact gap the Warning in [§3](../Part1/Section-03-Part1-Open-Source-Licensing-GPL-Governance.md) called out for FIFOs — a message queue genuinely buffers messages until a reader is ready for them.
- **Semaphores** — not a data-transfer mechanism at all, but a synchronization primitive: a kernel-managed counter that processes can atomically increment/decrement, used to coordinate access to a shared resource (frequently shared memory, [§5](../Part1/Section-05-Part1-Major-Distribution-Families.md)) without races. This is the "explicit synchronization" [§5](../Part1/Section-05-Part1-Major-Distribution-Families.md)'s Warning said shared memory requires — semaphores are one classic way to provide it.

Both exist in a POSIX-standardized form as well as the older System V form, and both are genuinely still used in specific contexts (database engines and some daemons use message queues and semaphores directly). This roadmap does not go deeper than this conceptual mention — full API-level treatment is outside DevOps/SRE scope as defined in this roadmap's assumption line, and the practical takeaway is simply: know these exist as the classic answer to "buffered, disconnected message passing" and "coordinating access to shared state," respectively, without needing to write code against either.

## 7. Comparison Table

| Mechanism                  | Speed                                          | Complexity                                        | Related processes only? | Persists across process restarts?             | Typical use case                                                                                                                                                                                          |
| -------------------------- | ---------------------------------------------- | ------------------------------------------------- | ----------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anonymous pipe (`\|`)      | Fast (kernel buffer, one copy)                 | Very low — shell handles it transparently         | Yes                     | No — dies with both ends                      | Shell pipelines, simple parent/child data flow ([§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md)–[§50](../Part6/Section-50-Part6-Regular-Expressions-For-Linux-Administration.md)) |
| Named pipe (FIFO)          | Fast (same as anonymous pipe underneath)       | Low — `mkfifo` plus normal file I/O               | No                      | Name persists; data does not                  | Unrelated local processes needing a simple one-way stream                                                                                                                                                 |
| Unix domain socket         | Fast (bypasses full network stack)             | Moderate — socket API, bidirectional              | No                      | No — ends when both sides close               | Local daemon/client request-response (e.g., Docker's socket)                                                                                                                                              |
| Network socket             | Slower (full network stack, possibly WAN)      | Higher — addressing, connection handling (Part 7) | No                      | No                                            | Cross-host communication of any kind ([§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)–[§58](../Part7/Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) full depth)  |
| Shared memory              | Fastest (zero-copy)                            | Highest — caller must implement synchronization   | Configurable            | Data persists only while mapped/backed        | High-throughput data sharing where copy overhead is measured and matters                                                                                                                                  |
| Message queue (SysV/POSIX) | Moderate (kernel-managed, some copy)           | Moderate                                          | No                      | Yes — queue persists independent of readers   | Buffered, decoupled message passing between processes                                                                                                                                                     |
| Semaphore                  | N/A — synchronization primitive, not transport | Moderate — correct usage requires care            | Configurable            | Yes — kernel-managed until explicitly removed | Coordinating safe access to a shared resource (often shared memory)                                                                                                                                       |

## 8. Common Misconceptions

1. **"A shell pipe and a named pipe are basically different things."** They're the same underlying kernel mechanism — an in-memory, unidirectional buffer — differing only in how the two ends find each other: an anonymous pipe's ends are inherited via `fork()` between related processes, a FIFO's ends are opened independently via a shared filesystem path (2–3).
2. **"Shared memory is always the right choice because it's the fastest."** Speed comes at the cost of the kernel providing zero built-in safety — every other mechanism in this section has the kernel enforcing at least some ordering or exclusion as a side effect of copying data through it; shared memory has none of that, and incorrect synchronization produces race conditions that are often intermittent and hard to reproduce (5).
3. **"A FIFO buffers data like a queue, so I can write to it now and read later."** A FIFO has no storage of its own — writing blocks until a reader is actively attached, and any data not immediately consumed simply sits in the same bounded kernel buffer an anonymous pipe uses. Actual disconnected buffering is what a message queue provides instead (3, 6).
4. **"Unix domain sockets and network sockets are unrelated technologies that happen to share a name."** They share the same programming abstraction and much of the same API surface; the practical difference is addressing (filesystem path vs. IP+port) and scope (local-machine-only vs. capable of crossing hosts), not a fundamentally different mechanism (4).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What does `ls | grep foo` actually do at the OS level?"_
**Model answer:** The shell creates an anonymous pipe — a kernel-managed, in-memory buffer with a read end and a write end — before starting both programs. It arranges `ls`'s standard output (file descriptor 1) to point at the pipe's write end and `grep`'s standard input (file descriptor 0) to point at the pipe's read end, then runs both processes, which are related to each other via the shell that forked them. `ls` writes as if writing to the terminal, `grep` reads as if reading from the terminal, and neither program needs to know the other exists — the kernel buffer and the shell's descriptor wiring do all the work.
_What the interviewer is probing for:_ Whether "pipes" is just shell syntax to the candidate, or whether they understand there's a real kernel object and file-descriptor redirection underneath it.

**🎯 Intermediate:** _"When would you reach for a named pipe (FIFO) instead of a regular anonymous pipe?"_
**Model answer:** Anonymous pipes only work between a process and its descendants, because the file descriptors are inherited via `fork()` — there's no way for two independently launched, unrelated processes to find each other's pipe. A FIFO solves exactly that by giving the pipe a name in the filesystem via `mkfifo`, so any process that can open that path can connect to either end, regardless of process ancestry. I'd use one when I need simple one-way streaming between processes that don't share a parent — for example, a monitoring script writing events that an unrelated log-shipper process consumes — while accepting that it's still just a pipe underneath: unidirectional, no persistence of unread data, and both ends have to be open concurrently for it to work.
_What the interviewer is probing for:_ Correctly identifying the actual limitation FIFOs solve (relatedness, not speed or capability) rather than a vague "it's a more powerful pipe."

**🎯 Senior:** _"Why is shared memory the fastest IPC mechanism, and what does that speed cost you?"_
**Model answer:** Every other mechanism — pipes, FIFOs, sockets, message queues — moves data by having the kernel copy it from the sending process's memory into a kernel-managed buffer, then copy it again out into the receiving process's memory. Shared memory skips both copies: the kernel maps the same physical pages into multiple processes' address spaces, so a write by one process is immediately visible to another with no kernel mediation on the actual read/write operations, just on the initial mapping setup. The cost is that the kernel provides no ordering or exclusion guarantees on that shared region at all — it's just memory two processes happen to both be touching. If both write concurrently without their own synchronization, typically a semaphore protecting the region, you get a race condition. So the speed is real, but it shifts responsibility for correctness entirely onto the application, which is exactly the tradeoff every other IPC mechanism avoids by paying the copy cost.
_What the interviewer is probing for:_ Understanding zero-copy as the actual mechanism behind the speed claim, not just "shared memory is fast," and correctly identifying synchronization as the tradeoff rather than some vague notion of "it's more complex."

**🎯 Architect:** _"You're designing two services on the same host that need to exchange a high volume of data with low latency. Walk through how you'd choose between the IPC mechanisms available."_
**Model answer:** I'd start from the actual requirements rather than reaching for the fastest option by default. If the two services are simple request/response and don't need a persistent connection, a Unix domain socket is the natural default — bidirectional, well-understood API, and it avoids the full network stack overhead of a TCP socket since both ends are local, while still giving me a clean abstraction I don't have to build synchronization on top of myself. If the exchange is genuinely one-directional streaming and one side is a descendant of the other, an anonymous pipe is simpler still. I'd only reach for shared memory if profiling actually showed the copy overhead of a socket or pipe was the bottleneck — high volume alone doesn't automatically justify it, because the correctness burden (explicit synchronization via semaphores, careful attention to partial writes and memory ordering) is real engineering cost that pays off only when the copy cost was genuinely the limiting factor. I'd also consider whether these two services might later need to run on separate hosts — if that's plausible, starting with a network socket over localhost, even at some latency cost now, avoids an architecture that has to be redesigned the moment they're no longer co-located, whereas Unix domain sockets and shared memory are both hard local-only commitments.
_What the interviewer is probing for:_ Requirements-first reasoning rather than defaulting to "fastest wins," and awareness that IPC mechanism choice has architectural consequences (portability across hosts) beyond raw throughput.

## 10. Key Takeaways

- IPC exists because process memory isolation ([§34](./Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)) is deliberate and default — cooperating processes need explicit, kernel-provided mechanisms to exchange data on purpose, safely.
- Anonymous pipes (`|`) are unidirectional, in-memory, kernel-buffered channels usable only between related processes — the exact mechanism behind every shell pipeline ([§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md)–[§50](../Part6/Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) builds hands-on fluency on top of this).
- Named pipes (FIFOs, `mkfifo`) are the same underlying pipe mechanism given a filesystem path, removing the relatedness restriction but not adding real persistence — unread data still just sits in a bounded kernel buffer.
- Sockets are bidirectional; Unix domain sockets are local-only and faster than network sockets, which can cross host boundaries — full networking depth (addressing, TCP/UDP, diagnostics) is Part 7, [§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)–[§58](../Part7/Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md).
- Shared memory (`/dev/shm`, tmpfs-backed) is the fastest mechanism because it eliminates kernel-mediated copying entirely, but it provides zero built-in synchronization — races are the direct cost of that speed.
- Message queues and semaphores (System V/POSIX) round out the classic IPC set — message queues provide genuine disconnected buffering that FIFOs lack, semaphores provide the synchronization shared memory needs — both covered here at concept level only.
- Mechanism choice is a tradeoff across speed, complexity, whether processes must be related, and whether the channel needs to cross host boundaries — not a single "best" answer independent of the actual requirement.

## 11. Related Concepts & What's Next

This section closes Part 5 ([§33](./Section-33-Part5-What-A-Process-Is.md)–[§40](./Section-40-Part5-Inter-Process-Communication-Overview.md), Process and Job Management) by tying its process-model foundation — isolated memory, the fork/exec/wait lifecycle from [§34](./Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md), and the process visibility tools from [§34](./Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)'s `ps`/`top` coverage, where a pipeline's `ls` and `grep` are visible as two distinct, connected processes — into the mechanisms processes use to deliberately cooperate across that isolation. The shell pipe introduced conceptually here (2) is the exact feature Part 6 builds real fluency on top of, starting with redirection and pipes in depth; and the socket concept sketched only briefly here (4) is developed into full networking depth — addressing, TCP/UDP, diagnostics, and more — in Part 7. **Part 6 ([§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md), Shell, Scripting, and Text Processing) is next**, beginning with a shell overview before moving into the redirection and pipe mechanics this section only introduced at the conceptual level.

**Next Section:** [§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md) — `Section-41-Part6-Shells-Overview.md`

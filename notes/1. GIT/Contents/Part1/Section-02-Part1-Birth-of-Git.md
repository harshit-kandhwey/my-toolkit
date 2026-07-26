# Section 2 (Part 1): The Birth of Git

## 1. The Precipitating Crisis: Linux Kernel & BitKeeper (2002–2005)

**Background.** From the kernel project's start in 1991 through 2002, Linus Torvalds managed contributions the way most open-source projects did: emailed patches, applied by hand, with no VCS at all. As contributor count grew into the hundreds, this became unmanageable — tracking who wrote what, merging divergent lines of work, and maintaining a clean history by email was not scaling.

**BitKeeper adoption (2002).** The kernel team adopted BitKeeper, a proprietary distributed VCS built by BitMover, Inc. BitMover granted free-of-charge licenses to open-source developers, including Linus, under specific conditions — notably that those developers would not work on competing VCS tools while using it for free.

**The break (April 2005).** A kernel contributor, Andrew Tridgell, worked on reverse-engineering the BitKeeper network protocol (via a tool that inspected its client-server exchanges), which BitMover considered a violation of the free-use terms. BitMover withdrew free access for kernel developers entirely. This left the kernel project — the single largest and most demanding open-source collaboration on earth at the time — with no version control system overnight.

## 2. Linus's Requirements — and Why Nothing Else Qualified

Linus evaluated existing tools and rejected all of them. His requirements, later stated repeatedly in talks and mailing-list posts, were uncompromising:

1. **Speed at kernel scale.** Thousands of files, tens of thousands of commits, hundreds of contributors. Diffing, branching, and merging had to be near-instant, not "acceptable."
2. **Fully distributed.** No central server dependency — the exact BitKeeper social/technical failure mode had to be structurally impossible to repeat.
3. **Strong integrity guarantees.** He explicitly wanted it to be _impossible_ for history to be silently corrupted or maliciously tampered with — a direct response to being a high-value target as the maintainer of critical global infrastructure.
4. **Cheap, trivial branching and merging.** The kernel's actual workflow is a tree of maintainer trees (subsystem maintainers merge into Linus's tree), so merging had to be a first-class, cheap, frequent operation, not a rare, dreaded one.
5. **Non-linear development at scale.** Thousands of parallel, divergent lines of work needed to be trackable and mergeable without central coordination.

He evaluated **Monotone** specifically (§1.6.2) — it had the right philosophical shape (distributed, content-addressed) — and found it too slow for kernel-sized repositories, largely due to using a general-purpose SQL database for storage rather than a purpose-built format.

**Decision:** build a new tool from scratch. Linus began work on **April 3, 2005**. A self-hosting version — Git capable of managing its own source history — was running within about **10 days**. The kernel itself moved onto Git by June 2005. Linus handed primary maintainership to **Junio Hamano** shortly after, who remains Git's lead maintainer today.

## 3. Why "Git"?

Linus's own explanation, widely quoted: _"I'm an egotistical bastard, and I name all my projects after myself. First 'Linux', now 'git'."_ ("git" is British slang for an unpleasant or foolish person.) A commonly cited, only-half-joking backronym is "Global Information Tracker." There is no single official technical meaning — the name is deliberately irreverent, consistent with the tool's terse, unglamorous command surface.

## 4. Design Philosophy — The Principles That Explain Every Later Design Decision

These four pillars are worth memorizing verbatim, because nearly every "why does Git do it _this_ way" question traces back to one of them.

### 4.1 Speed

Every core operation — commit, diff, branch, merge, log traversal — was designed to be local and fast, avoiding network calls and avoiding expensive computation on the common path. This is _why_ Git stores full snapshots instead of computing diffs at commit time (computing a diff is more expensive than storing a pointer to unchanged content — detailed in §5), and _why_ branches are simple 41-byte file pointers rather than full copies (§6).

### 4.2 Simplicity of the underlying data structure, even at the cost of a harder-to-learn interface

Git's actual data model — a content-addressed graph of four object types (§5) — is small and elegant. Linus explicitly modeled it on **filesystem thinking**: a commit is conceptually a snapshot of a directory tree, the same mental model as a filesystem snapshot. However, the _user-facing commands_ that manipulate this simple model are famously inconsistent and were bolted on organically over years — this is a widely acknowledged, real design tension, not a myth, and is precisely why Git has a reputation for a steep learning curve despite an elegant core. You are being taught the internals first (Section 4–7) specifically so the commands in Section 8 onward stop feeling arbitrary.

### 4.3 Distributed by design, not by feature

Distribution was not an add-on; it was the entire point (§2.2, item 2). Every clone contains full history and full capability. There is no privileged operation that only a "server" can perform — a design position that flows directly from the BitKeeper trauma.

### 4.4 Strong integrity guarantees via cryptographic hashing

Every object — every file snapshot, every directory listing, every commit — is identified by a **SHA-1** hash of its own content (transitioning toward SHA-256, covered in §32). Because a commit's hash incorporates the hashes of everything it points to (including its parent commit), **the entire history back to the first commit is cryptographically chained**: changing any byte anywhere in history changes that object's hash, which changes every hash that references it, all the way forward. Corruption or tampering is detectable, not just theoretically possible to detect but automatically flagged by Git's own consistency checks (`git fsck`, §29–30). This is the direct technical answer to Linus's integrity requirement, and it's why Git's data structure is frequently described as a **Merkle tree / Merkle DAG** — a term you should recognize; we build it precisely, object by object, in Section 5.

> ⚠️ **Common confusion to preempt:** SHA-1 hashing in Git was **never primarily a security/encryption feature** in the sense of hiding content — anyone with repo access can read every object. Its purpose is **integrity verification and content addressing**, not confidentiality. Do not conflate the two in an interview answer.

## 5. Explicit Design Trade-offs Linus Made

A senior-level understanding requires knowing what was _sacrificed_, not just what was gained:

| Chose                                                    | Over                                        | Rationale                                                                                                                                                                      |
| -------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Snapshots per commit                                     | Storing diffs per commit                    | Snapshots make "what did the whole project look like at commit X" a direct lookup, not a replay of every diff since the beginning — critical at kernel scale and history depth |
| A minimal, low-level "plumbing" toolkit exposed to users | A single polished high-level interface only | Enabled the ecosystem of tools and scripts to be built on top (and, honestly, reflects that Git was built by and for kernel developers comfortable with low-level tools first) |
| Command-line-first, Unix-philosophy tool                 | An integrated GUI application               | Matched its origin as infrastructure for the most CLI-native developer community in existence; GUIs came later as third-party or bolted-on layers                              |
| Eventual-consistency, no locking                         | File-locking / pessimistic concurrency      | Matches the copy-modify-merge philosophy (§1.5.2) required for thousands of independent contributors who cannot coordinate locks in real time                                  |

## 6. From Kernel Tool to Industry Standard — Adoption Timeline

| Period           | Milestone                                                                                                                                                                                                                                                      |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **2005**         | Git created; Linux kernel migrates onto it                                                                                                                                                                                                                     |
| **2005**         | Junio Hamano takes over as lead maintainer                                                                                                                                                                                                                     |
| **2008**         | **GitHub** launches, wrapping Git in a social, web-based collaboration platform (pull requests, issue tracking, forks) — this is the single biggest driver of Git's mainstream adoption outside the kernel world                                               |
| **2010–2013**    | Major open-source ecosystems (Ruby/Rails community, countless language package ecosystems) standardize on Git + GitHub; **GitLab** (2011) and **Bitbucket** (2008, initially Mercurial-only, added Git support 2011) provide alternative/self-hosted platforms |
| **2013–2015**    | Large enterprises begin large-scale migration off SVN/TFVC/ClearCase onto Git                                                                                                                                                                                  |
| **2016**         | **Microsoft** — historically an SVN/TFVC shop internally — commits publicly to Git, including engineering **VFS for Git** to make the Windows codebase (hundreds of GB) usable on Git (§26, §32)                                                               |
| **2018**         | Microsoft acquires GitHub                                                                                                                                                                                                                                      |
| **2018–present** | Git becomes the assumed default in virtually every hiring pipeline, CI/CD platform, and DevOps toolchain; developer surveys consistently show it used by the overwhelming majority of professional developers                                                  |

> 💡 **Tip:** Notice the pattern — Git's _technical_ adoption (2005) and its _mainstream_ adoption (post-2008) are separated by GitHub. This is a genuinely important distinction for a "why did Git win" interview answer: Git won partly on technical merit against Mercurial and Bazaar, but its total market dominance is inseparable from the platform ecosystem (GitHub especially) built around it. Mercurial, arguably comparably well-designed, never got an equivalent breakout platform effect at the same scale, and that mattered as much as any CLI difference.

## 7. Why Git Won Over Mercurial Specifically

This is a frequent senior/architect interview question, so it deserves a direct, honest answer rather than "Git is just better":

- **Technical parity, mostly.** Both are distributed, both use content-addressed-ish models (Mercurial's internals differ in detail but solve the same problems), both support fast local branching. Neither is simply "faster" in a way that explains 10x adoption differences.
- **GitHub effect.** GitHub chose Git, not Mercurial, and became the dominant social coding platform. Network effects (where your collaborators and open-source dependencies already are) compound quickly.
- **CLI philosophy diverged.** Git exposes a lower-level, more "here are the primitives" interface; Mercurial deliberately prioritized a cleaner, more consistent command surface. In practice the ecosystem/platform effect outweighed Mercurial's usability advantage.
- **Corporate backing at scale.** Facebook/Meta invested heavily in Mercurial internally (and built Sapling on it, per §1.8) but did not open that investment into a competing public hosting platform the way GitHub did for Git.
- **Google** used both at different points, and Google Code (which supported both) shut down in 2016, removing one more Mercurial-hosting option from the ecosystem.

> 🎯 **Interview tip:** A senior answer to "why did Git win?" names the platform/network-effect argument explicitly. A junior answer just claims Git is technically superior — which is not a fully accurate claim and signals shallow research if stated as fact.

## 8. Interview Questions — This Section's Material

**[Beginner] Q1. Who created Git, and why?**
**Model answer:** Git was created by Linus Torvalds in April 2005 to manage the Linux kernel's source code, after the kernel project lost free access to the proprietary BitKeeper VCS it had been using. Torvalds needed a tool that was extremely fast even at the kernel's huge scale, fully distributed with no dependency on a central server, and built with strong guarantees that history could not be silently corrupted or tampered with — requirements no existing tool met at the time. A working, self-hosting version was ready in about ten days, and the kernel itself moved onto Git within a couple of months.

**[Intermediate] Q2. What specific event caused the kernel project to abandon BitKeeper?**
**Model answer:** The kernel team used BitKeeper for free under license terms from BitMover that restricted developers from working on competing version control tools. In April 2005, a kernel contributor, Andrew Tridgell, worked on reverse-engineering BitKeeper's network protocol, which BitMover viewed as a breach of those terms, and BitMover responded by revoking free access for kernel developers. This left the project with no VCS and directly triggered Torvalds building Git from scratch.

**[Senior] Q3. Explain how Git's integrity model works and why it mattered specifically for the Linux kernel.**
**Model answer:** Every object Git stores — file content, directory structure, commit metadata — is identified by a cryptographic hash (originally SHA-1, transitioning to SHA-256) computed from its own content. A commit's hash is derived partly from the hash of its parent commit, so the entire history forms a hash-linked chain — technically a Merkle DAG. Changing any historical object, even one byte in a file from years ago, changes that object's hash, which cascades and changes every commit hash after it. This makes silent, undetected tampering with history structurally very hard, and any corruption or manipulation is detectable via consistency checks like `git fsck`. This mattered acutely for the kernel because it is critical global infrastructure and a natural target: Torvalds explicitly wanted a system where a compromised mirror or malicious contributor couldn't quietly inject altered history that looked legitimate. I'd be careful to note this is an integrity/tamper-evidence property, not encryption — repository content isn't hidden from anyone with access, and by itself hash-chaining doesn't stop a well-resourced attacker who can persuade everyone to accept a new, differently-signed history; that's what commit signing (§28) adds on top.

**[Architect] Q4. Git and Mercurial were both created in April 2005 by different authors solving the same problem, with broadly comparable technical designs. Why does Git have vastly greater market share today?**
**Model answer:** The gap isn't well explained by "Git is technically better" — both are distributed VCS with fast local operations and comparable core capabilities. What actually diverged is ecosystem and platform effects. GitHub launched in 2008 specifically on Git and became the dominant social coding platform — pull requests, open-source discovery, and portfolio/resume presence all concentrated there, creating strong network effects: developers and companies go where their collaborators and dependencies already are. Mercurial had serious backing too — Meta invested heavily and built internal tooling and later Sapling on Mercurial's model — but that investment never produced an equivalent public platform to compete with GitHub's gravity, and one significant Mercurial-supporting host, Google Code, shut down in 2016. Secondary factors include Git's lower-level CLI appealing to the kernel-developer community it originated in, versus Mercurial's more deliberately consistent UX — but I'd weight the platform/network-effect argument far more heavily than any CLI difference in explaining the actual adoption gap.

## 9. Common Misconceptions

1. **"Git was created by GitHub."** Git (2005) predates GitHub (2008) by three years and is an independent open-source project with no corporate ownership; GitHub is a hosting company that later built a business around it (and was later acquired by Microsoft in 2018).
2. **"SHA-1 in Git means your code is encrypted/secure."** It provides integrity/tamper-evidence, not confidentiality. Anyone with read access sees everything.
3. **"Git won because it's simply the best-designed tool."** Partly true technically, but incomplete — platform/network effects (GitHub) are a major, often underweighted, part of the real answer.
4. **"BitKeeper was open-source and Git just replaced an inferior free tool."** BitKeeper was commercial/proprietary; the free tier for open-source developers came with usage restrictions, and it was the withdrawal of that free tier — not a technical failing — that precipitated Git's creation. (BitKeeper was later open-sourced in 2016, well after Git had already won.)

## 10. 🔑 Key Takeaways

- Git was born in ~10 days in April 2005, created by Linus Torvalds after BitKeeper's free-use license for Linux kernel developers was revoked following the Tridgell reverse-engineering incident.
- Four design pillars explain nearly every subsequent design decision: **speed**, **a simple filesystem-like data model** (even though the command UX is admittedly inconsistent), **distribution by design**, and **integrity via cryptographic hash-chaining (a Merkle DAG)**.
- Git's dominance is a combination of genuine technical soundness _and_ the GitHub platform effect from 2008 onward — not technical merit alone.
- Git's hashing is for integrity, not encryption — a critical distinction to state precisely in interviews.

## 11. Related Concepts & What's Next

You now have the _why_. Section 3 gives you the precise Git-specific _vocabulary_ — repository, working tree, index/staging area, commit, branch, HEAD, remote, and more — defined exactly as Git uses them, so that Section 4 onward (architecture and internals) can be taught without pausing to define terms.

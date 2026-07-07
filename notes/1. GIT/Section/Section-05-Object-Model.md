# Section 5 — The Object Model: Blobs, Trees, Commits, Annotated Tags & Content-Addressable Storage

## 5.1 Definition

**Plain language:** Everything Git ever stores — every file version, every directory listing, every commit — is saved as one of exactly four object types, each named by the hash of its own content. This is the single database underneath every Git feature you'll ever use.

**Precise:** Git's object database is a **content-addressable store**: given content, Git computes `SHA(type + size + content)` and uses that hash as the object's permanent address. There are exactly four object types — **blob**, **tree**, **commit**, and **tag** — and every one of Git's higher-level features (branches, history, diffs, merges) is built entirely from a graph of these four object kinds. This graph is a **Merkle DAG** (a directed acyclic graph where each node's identity is derived from its own content plus the identities of the nodes it points to).

## 5.2 Why It Exists / Problem It Solves

1. **Deduplication for free.** If two commits, two branches, or two files anywhere in the repo have byte-identical content, they hash to the same value and are stored **once**, physically. Renaming a file, or two unrelated files happening to contain the same text, costs zero extra storage.
2. **Free integrity checking.** Because an object's address *is* the hash of its content, any corruption changes the hash — meaning the object literally cannot be retrieved by its old name anymore, and `git fsck` (§29–30) can detect this systematically. This is the concrete mechanism behind the integrity guarantee promised conceptually in §2.4.4.
3. **Fast, unambiguous identity with no central authority.** As established in §1.10 Q3, no counter-based ID scheme works without a central server. Content hashing lets any two independent clones compute the *same* ID for the *same* content with zero coordination.
4. **Efficient snapshots, not diffs.** Storing a full tree-of-blobs per commit, rather than a diff against the previous commit, means retrieving *any* historical version of the whole project is a direct graph walk from one commit object — not a replay of every change since the beginning. (Compression via delta-encoding still happens, but only inside packfiles as a storage optimization — §7 — and is completely invisible at this logical layer.)

## 5.3 Prerequisites and Dependencies

- SHA hashing as a concept (a function mapping arbitrary input to a fixed-length, effectively-unique digest) — explained inline below if unfamiliar.
- The three-area model from §4 — objects are what actually gets written into `.git/objects` when you `git add` and `git commit`.

## 5.4 The Hash Function Itself

Git has historically used **SHA-1**, producing a 40-character hexadecimal digest (160 bits) for every object, e.g. `a3f8e21bc9d4f5e6...`. Two properties matter enormously here:

- **Determinism:** identical content always produces the identical hash, on any machine, forever.
- **Avalanche effect:** changing even one byte of input produces a completely different, unrelated-looking hash — there is no "close" hash for "close" content, which is exactly what makes tampering detectable rather than merely inconvenient.

> ⚠️ **Version-specific note, flagged per accuracy rules:** SHA-1 has known theoretical collision weaknesses (demonstrated practically in the 2017 "SHAttered" research against SHA-1 in general, not Git specifically). Git mitigates this with a hardened SHA-1 implementation (`sha1dc`) that detects known collision-attack patterns, and the project has an ongoing, still-partial migration path to **SHA-256** as an optional repository format. Treat "Git is transitioning to SHA-256" as accurate at a high level; treat exact current rollout completeness as something to verify against current documentation, since this is actively evolving — fully covered in §32.

## 5.5 The Four Object Types

### 5.5.1 Blob (Binary Large Object)

- **What it stores:** the raw content of exactly one file version — bytes only. **No filename. No permissions. No directory location.** A blob is pure content.
- **Consequence:** two files with identical content — regardless of name, location, or how many commits apart — are the *same blob*, stored once. Renaming a file with unchanged content creates **zero new blobs**.
- **Inspecting one:** `git cat-file -p <hash>` prints a blob's raw content; `git cat-file -t <hash>` prints its type (`blob`).

### 5.5.2 Tree

- **What it stores:** the equivalent of one directory listing — an ordered list of entries, each entry being `(file mode, object type, hash, name)`.
- **Entry types:** an entry's object type is either `blob` (a regular file) or `tree` (a subdirectory) — trees nest recursively, exactly mirroring your folder structure.
- **File mode examples:** `100644` (normal file), `100755` (executable file), `120000` (symbolic link), `040000` (subdirectory/tree). These modes are what let Git track executable permission bits (Unix-style) as part of the *tree* entry, not the blob — the same blob content can be pointed to with different modes in different trees.
- **Consequence of content-addressing at this layer:** if you commit, then later revert a change to restore a directory to a byte-identical prior state, the resulting tree hash is identical to the original tree's hash — Git recognizes it as the *same* tree object, not a new one.

### 5.5.3 Commit

- **What it stores:** exactly one pointer to a root tree object, plus zero or more pointers to parent commit(s), plus metadata: author name/email/timestamp, committer name/email/timestamp (usually identical, but can genuinely differ — e.g., someone rebasing or applying a patch on your behalf becomes the *committer* while you remain the *author*), and the commit message.
- **Parent count and meaning:**
  - **0 parents** → a **root commit** (the very first commit in a repository's history).
  - **1 parent** → an ordinary commit.
  - **2+ parents** → a **merge commit** (§13), recording that this point in history unites multiple prior lines of development.
- **Why hashing a commit chains all of history:** a commit's hash is computed over its *own content*, which includes its parent's hash as literal text. Change anything about an old commit — its message, its tree, its parent — and its hash changes; anything that pointed to it (its child commit) now has different content, so *its* hash changes too, cascading forward through every subsequent commit. This is the literal mechanism behind "history is cryptographically chained" from §2.4.4.

**Inspecting a real commit object** (`git cat-file -p <commit-hash>`):

```
tree 8f3d9c2b1a4e5f6789...
parent a1b2c3d4e5f6789012...
author Jane Doe <jane@example.com> 1719400000 +0530
committer Jane Doe <jane@example.com> 1719400000 +0530

Fix off-by-one error in pagination logic
```

Note precisely what's *absent*: no filenames, no diff, no per-file changes — a commit is a pointer to one complete tree plus lineage plus metadata, nothing more.

### 5.5.4 Tag (Annotated Tag Object)

- **What it stores:** a pointer to any other object (almost always a commit), plus its own metadata: tagger name/email/timestamp, a tag message, and optionally a cryptographic signature (§28).
- **Critical distinction — annotated vs. lightweight:**

| | Lightweight tag | Annotated tag |
|---|---|---|
| **What it physically is** | Just a ref file under `.git/refs/tags/`, pointing straight at a commit — structurally identical to a branch pointer, just conventionally not moved | A real, distinct **tag object** in the object database, which itself is pointed to by a ref |
| **Metadata carried** | None — no tagger, no date, no message | Tagger identity, timestamp, message, optional GPG/SSH signature |
| **Command to create** | `git tag v1.0.0` | `git tag -a v1.0.0 -m "Release 1.0.0"` |
| **When to use** | Quick, throwaway personal markers | **Always, for any tag that will be shared, released, or matters** — the enterprise/production default, detailed in §18 |

> 💡 **Tip:** A lightweight tag is structurally indistinguishable from a branch pointer at the ref level — the only difference is *convention* (you don't move it forward). This is why real releases should always use annotated tags: they're a genuinely distinct, auditable object type with an identity and signature of their own, appropriate for something you'll cite in a compliance audit or a support ticket a year later.

## 5.6 Architecture — How the Four Types Compose Into One Graph

```
                              COMMIT  (the current branch tip)
                             ┌────────────────────────────┐
                             │ tree:   ──────────┐          │
                             │ parent: (older commit)       │
                             │ author/committer/message      │
                             └────────────────────┼─────────┘
                                                   ▼
                                              TREE (root)
                          ┌────────────────────────┼─────────────────────┐
                          ▼                        ▼                     ▼
                  BLOB "README.md"          TREE "src/"            BLOB ".gitignore"
                  (file content)      ┌───────────┼───────────┐    (file content)
                                      ▼           ▼             ▼
                              BLOB "main.py"  BLOB "utils.py"  TREE "tests/"
                                                                     │
                                                                     ▼
                                                             BLOB "test_utils.py"
```

Walking this diagram: one commit → one root tree → that tree's entries point to blobs (files at the top level) and further trees (subdirectories), recursively, until every entry is a blob. **This structure is identical, conceptually, to how a filesystem represents directories and files** — precisely the "model it on filesystem thinking" design choice noted in §2.4.2.

Now the crucial second half of the picture — **how commits chain together across history**:

```
   commit C1 (root, no parent)
        ▲
        │ parent
   commit C2
        ▲
        │ parent
   commit C3  ◄── refs/heads/main  (the "main" branch pointer)
        ▲
        │ parent
   commit C4  ◄── refs/heads/feature-x (a divergent branch, also descends from C3)
```

Each commit object embeds its parent's hash as literal text inside its own content — this is the mechanism that makes the whole thing a chained, tamper-evident graph rather than a set of independent snapshots.

## 5.7 Content-Addressable Storage — Worked Example

Trace exactly what happens, object by object, for a tiny two-file commit:

```bash
$ mkdir demo && cd demo && git init -q
$ echo "hello" > a.txt
$ echo "hello" > b.txt      # IDENTICAL content to a.txt
$ git add a.txt b.txt
$ git commit -q -m "add two identical files"

$ git cat-file -p HEAD^{tree}
100644 blob ce013625030ba8dba906f756967f9e9ca394464    a.txt
100644 blob ce013625030ba8dba906f756967f9e9ca394464    b.txt
```

Both entries point to the **exact same blob hash** — `git` computed the hash of `"hello\n"` once and stored it once, even though it appears in the working directory as two separate files with two separate names. This is deduplication happening automatically, at the storage layer, with no special command or configuration.

Now verify the commit's own chained hash:

```bash
$ git cat-file -p HEAD
tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904
author ...

$ git rev-parse HEAD
7e4f9a2c8b1d3e5f6a7b8c9d0e1f2a3b4c5d6e7f
```

If you amended this commit's message right now (`git commit --amend -m "changed message"`), `git rev-parse HEAD` would print a **completely different** hash — even though the tree (actual file content) is unchanged — because the commit object's content includes the message text, and any change to that content changes the hash by the avalanche effect.

## 5.8 Commands (Full Documentation per §9 Template)

### `git cat-file`

- **Purpose:** low-level ("plumbing") command to inspect any object's raw type, size, or content directly by hash — the primary tool for *seeing* the object model rather than just trusting it exists.
- **Syntax:** `git cat-file <-t|-s|-p> <object>`
- **Key options:**
  - `-t` — print the object's type (`blob`, `tree`, `commit`, or `tag`).
  - `-s` — print the object's size in bytes.
  - `-p` — pretty-print the object's content in a human-readable form appropriate to its type (this is the flag used throughout this section).
- **Practical example:**
  ```bash
  $ git cat-file -t a3f8e21
  commit
  $ git cat-file -p a3f8e21
  tree 8f3d9c2...
  parent 1a2b3c4...
  author ...
  ```
- **Production usage:** used in debugging scripts, forensic history investigation ("what exactly did this object contain before it was garbage-collected"), and in custom Git tooling/hooks that need to inspect objects directly rather than through porcelain commands.
- **Common errors:** `fatal: Not a valid object name <hash>` — the hash doesn't exist in this repository (typo, wrong repo, or the object was pruned by gc without ever being reachable — §7, §29).
- **Security impact:** read-only, no write risk; safe to run against any hash you're curious about.
- **Performance impact:** negligible for single lookups; trivial even at scale since it's a direct hash-indexed retrieval, not a scan.

### `git hash-object`

- **Purpose:** compute (and optionally store) the blob hash Git *would* assign to a given piece of content, without needing a full commit — useful for understanding or scripting around content-addressing directly.
- **Syntax:** `git hash-object [-w] <file>`
- **Key options:** `-w` actually writes the object into `.git/objects`; without it, the command only prints the hash it *would* get, with no side effect.
- **Practical example:**
  ```bash
  $ echo "hello" | git hash-object --stdin
  ce013625030ba8dba906f756967f9e9ca394464
  ```
  This matches exactly the blob hash seen in §5.7 — proving the hash is a pure function of content, computable independent of any repository state.
- **Production usage:** rare in day-to-day work; appears in custom tooling that pre-computes object identity (e.g., deduplication checks, custom sync tools) or in teaching/demonstration contexts like this one.
- **Common errors:** forgetting `--stdin` when piping input leads to Git trying to interpret the pipe as a filename argument.
- **Security impact:** none (read/compute only, unless `-w` is used, in which case it writes a loose object — still low risk, just disk usage).
- **Performance impact:** negligible; hashing is fast even for large files, though very large binary files will show measurable I/O time.

### `git rev-parse`

- **Purpose:** resolve any human-friendly reference (branch name, tag name, `HEAD`, a shortened hash, relative expressions like `HEAD~2`) down to its full, unambiguous 40-character (or 64, under SHA-256) object hash.
- **Syntax:** `git rev-parse <ref-expression>`
- **Key options:** `--short` prints an abbreviated hash instead of the full one; `HEAD^{tree}` (seen in §5.7) resolves to the *tree* a commit points to, rather than the commit itself.
- **Practical example:**
  ```bash
  $ git rev-parse HEAD
  7e4f9a2c8b1d3e5f6a7b8c9d0e1f2a3b4c5d6e7f
  $ git rev-parse --short HEAD
  7e4f9a2
  ```
- **Production usage:** extremely common in CI/CD scripts and automation (§25) — e.g., tagging a built artifact with the exact short commit hash it was built from, so any deployed artifact can be traced back to precisely one commit.
- **Common errors:** `fatal: ambiguous argument '<ref>': unknown revision or path not in the working tree` — typo'd branch/tag name, or you're referring to a path that doesn't exist and Git can't tell if you meant a ref or a file.
- **Security impact:** none; read-only resolution.
- **Performance impact:** negligible; ref resolution is a fast lookup, not a history scan.

## 5.9 Hands-On Example — Proving Deduplication and Chaining Together

```bash
$ mkdir objdemo && cd objdemo && git init -q
$ echo "version 1" > file.txt
$ git add file.txt && git commit -q -m "v1"
$ git rev-parse HEAD
1111111111111111111111111111111111111111   # (illustrative, not a real hash)

$ echo "version 2" > file.txt
$ git add file.txt && git commit -q -m "v2"
$ git rev-parse HEAD
2222222222222222222222222222222222222222

$ echo "version 1" > file.txt   # manually recreate the ORIGINAL content
$ git add file.txt && git commit -q -m "back to v1 content"
$ git cat-file -p HEAD^{tree}
100644 blob <SAME BLOB HASH AS THE VERY FIRST COMMIT>    file.txt
```

The third commit's tree entry for `file.txt` points to the **identical blob hash** as the first commit — because the content is byte-identical, Git never created a new blob for it; it simply reused the existing one from the object database, potentially created "v1 commit" ago. This is deduplication operating silently across arbitrarily distant points in history, not just adjacent commits.

## 5.10 Production & Enterprise Usage

- **Immutable artifact tracing:** enterprise CI/CD pipelines routinely embed the exact short commit hash (via `git rev-parse --short HEAD`) into build artifact names, container image tags, and deployment metadata — giving a direct, unambiguous link from any running production artifact back to the exact source snapshot it was built from. This is a direct practical exploitation of content-addressing: the hash *is* the identity.
- **Compliance/audit trails:** because commit objects chain cryptographically, security and compliance teams can rely on `git log` history as tamper-evident evidence in SOX/ISO 27001-style audits — provided the repository's integrity hasn't been separately compromised (e.g., via force-pushes rewriting history on a shared server without protections — covered in §23, §28).
- **Deduplication at scale:** in large monorepos, the same boilerplate file (license headers, generated code, vendored dependencies) appearing across thousands of directories costs storage for exactly **one** blob, not thousands — a meaningful, automatic space saving with zero configuration.

## 5.11 Security Considerations

- **Integrity, not confidentiality (restated precisely here since this is where it becomes concrete):** anyone with read access to `.git/objects` can read every object's content directly via `git cat-file -p` — there is no encryption at this layer. Hashing prevents *undetected tampering*, not *reading*.
- **SHA-1 collision risk:** Git's hardened `sha1dc` implementation is specifically designed to detect known SHA-1 collision-attack constructions and refuse to accept a maliciously crafted colliding object, mitigating (though the underlying algorithm's theoretical weakness remains a reason the ecosystem is moving toward SHA-256, §32).
- **Signed commits/tags** (full treatment in §28) build directly on this section's annotated-tag and commit-object structure — a signature is cryptographic proof that a specific person, holding a specific key, vouched for a specific object's exact hash.

## 5.12 Performance Considerations

- Loose objects (one file per object, as shown in §4.3) are simple but inefficient at scale — many small files, each individually zlib-compressed. Git periodically consolidates them into **packfiles** with delta compression between similar objects, a purely storage-layer optimization covered in full in §7 that never changes the logical model taught in this section.
- Hash computation itself is fast (SHA-1/SHA-256 are designed for speed), so hashing overhead on `git add`/`git commit` is not a practical bottleneck even for large files — I/O (reading the file, writing the compressed object) dominates any real-world timing.

## 5.13 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `fatal: Not a valid object name` | Hash typo, wrong repository, or object was pruned because nothing referenced it | Verify the hash with `git log --all` or check the reflog (§6, §30) for a reachable reference to it |
| Two files you expected to be "different objects" show identical hashes | Their content is genuinely byte-identical (including trailing whitespace/newlines) | Not a bug — this is deduplication working correctly; diff the actual file content if this is surprising |
| Commit hash changes after only editing the commit message | Expected behavior | The commit object's content includes the message; any change changes the hash — this is not corruption |

## 5.14 Best Practices

- Use **annotated tags** for anything that will be shared, released, or audited — never rely on a lightweight tag for a real release (§18 expands this into a full release-management discipline).
- When building tooling around Git, prefer resolving refs with `git rev-parse` rather than string-matching branch names yourself — it correctly and uniformly handles branches, tags, HEAD, and relative expressions.
- Embed exact commit hashes (not branch names, which move) into anything requiring precise reproducibility — build artifacts, deployment records, audit logs.

## 5.15 Anti-Patterns & Common Mistakes

- **Anti-pattern:** assuming a commit stores a diff. This actively misleads people trying to reason about repository size, `git log -p` performance, or why reverting an old change doesn't "replay" anything — it constructs a new tree by direct snapshot comparison instead.
- **Common mistake:** treating lightweight tags as adequate for production releases, losing the tagger identity, timestamp, message, and signature capability that an annotated tag provides — often only discovered as a gap during a compliance audit, too late to retroactively add real metadata to years of past releases.

## 5.16 Interview Questions

**[Beginner] Q1. What are the four object types in Git, and what does each one represent?**
**Model answer:** Blob, tree, commit, and tag. A blob stores a single file's raw content with no name or metadata attached. A tree represents a directory listing — an ordered set of entries, each naming a file mode, a type (blob or tree), a hash, and a name, letting trees nest to mirror folder structures. A commit points to exactly one root tree plus zero or more parent commits, along with author, committer, and message metadata. A tag (specifically an annotated tag) points to another object, almost always a commit, and carries its own tagger identity, message, and optional signature. Together, these four types are the entire alphabet Git uses to represent everything in a repository.

**[Intermediate] Q2. Explain, with an example, how Git deduplicates storage automatically.**
**Model answer:** Because objects are addressed by the hash of their own content, two pieces of identical content always produce the identical hash and are therefore stored as the exact same object, regardless of filename or location. For example, if two files anywhere in a repository — even in completely different directories, or committed years apart — contain byte-identical content, Git stores that content as a single blob object, and both tree entries simply point to the same hash. Renaming a file with unchanged content, similarly, creates zero new blobs — only the tree entry's name field changes, not the underlying content object. This deduplication is a direct, automatic consequence of content-addressing, requiring no special command or configuration.

**[Senior] Q3. Why does amending only a commit's message change that commit's hash, even though no file content changed?**
**Model answer:** A commit object's hash is computed over its entire content as stored in the object database, and that content includes the commit message as literal text, alongside the tree pointer, parent pointer(s), and author/committer metadata. Changing any of that content — including just the message — produces different input to the hash function, which by the avalanche property produces a completely different, unrelated hash. The tree object itself (representing actual file content) is unaffected and keeps its original hash, but the commit object wrapping it is new. This is also why `git commit --amend` doesn't modify history in place; it creates a brand-new commit object and moves the branch pointer to it, leaving the original (now typically unreferenced) commit object still physically present until garbage collected.

**[Architect] Q4. A security team asks: "Can someone tamper with our Git history without us knowing?" How do you answer, precisely?**
**Model answer:** I'd separate two distinct claims. First: can someone silently alter an *existing* commit's content and have it pass as the original, unnoticed? No — because commit hashes are chained (each commit's hash is partly derived from its parent's hash), changing any historical commit changes its hash, which changes every descendant commit's hash, and everyone else's clones would immediately show a divergent history the moment they fetch — this is detectable, not prevented outright. Second, and more precisely what attackers actually do: can someone construct an *entirely alternate* history and force it to replace the shared one? Yes, via a force-push to a shared branch, if they have write access and branch protections aren't configured to prevent it — this is a permissions and governance problem, not a hash-collision problem, and it's exactly why enterprise setups add protected branches, mandatory code review, and commit/tag signing (§23, §28) on top of the base object model. I'd tell the security team: the object model gives you tamper-*evidence*, not tamper-*prevention* by itself; prevention requires access control and process on top of it, and detection at the individual-object level relies on SHA-1's collision resistance holding, which is one reason the ecosystem is migrating toward SHA-256 as an available repository format.

## 5.17 Common Misconceptions

1. **"Commits store diffs."** Commits point to a full tree snapshot; diffs are computed on demand by comparing two trees, never stored as the commit's actual content.
2. **"A lightweight tag and an annotated tag are basically the same thing."** A lightweight tag is a plain ref pointer, structurally identical to a branch pointer; an annotated tag is a distinct object type carrying its own tagger, date, message, and optional signature — a meaningfully different, more auditable artifact.
3. **"Git hashing is for security/encryption of my code."** It provides content-addressing and tamper-evidence; it does not hide or encrypt content from anyone with repository access.
4. **"Renaming a file creates a new object."** It only changes the tree entry's name field; the underlying blob (and its hash) is unchanged if content is unchanged.

## 5.18 🔑 Key Takeaways

- Four object types — blob, tree, commit, tag — compose into a single content-addressed Merkle DAG; everything in Git is built from just these.
- Blobs are pure content (no name); trees are directory listings pointing to blobs and other trees; commits point to one tree plus parent(s) plus metadata; annotated tags are a distinct, metadata-rich object type — always prefer them for real releases.
- Content-addressing gives automatic deduplication and tamper-evidence for free, as direct consequences of the hash-as-identity design, not separate bolted-on features.
- A commit's hash chains to its parent's hash, cryptographically linking all of history — the concrete mechanism behind §2's "Merkle DAG" claim.
- `git cat-file`, `git hash-object`, and `git rev-parse` are the plumbing tools that make this model directly inspectable rather than an abstraction you have to take on faith.

## 5.19 Related Concepts & What's Next

This section covered the objects themselves. Section 6 covers **refs** — the named pointers (branches, tags-as-refs, HEAD) that give these otherwise anonymous hash-addressed objects human-friendly, moving names — plus the **reflog**, your local safety net for recovering from mistakes. Understanding refs precisely is also the direct prerequisite for detached HEAD, rebasing, and history rewriting in Part D.

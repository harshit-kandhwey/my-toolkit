# Section 4 (Part 2): Git Architecture: The Three Areas & Repo Anatomy

## 4.1 Definition

**Plain language:** Git's architecture is built around three physical locations on your disk that hold three different representations of your project, plus a set of rules for how content moves between them.

**Precise:** A Git repository consists of (1) the **working directory** — ordinary files on disk, (2) the **index** — a single binary file recording the staged snapshot, and (3) the **object database** — a content-addressed store of immutable objects inside `.git/objects`, referenced by **refs** (branches/tags) inside `.git/refs`. Every Git command operates on one or more of these three locations.

## 4.2 Why It Exists / Problem It Solves

A naive VCS could commit directly from the working directory: "commit whatever's different right now." Git deliberately inserts the index as a **buffer** between "what's on disk" and "what goes into history" for concrete reasons:

1. **Partial commits.** You've fixed a bug and, unrelated, made an unfinished experimental edit in the same file or same working tree. The index lets you stage and commit *only* the bug fix (even only certain lines, via `git add -p`, §10) while leaving the experimental edit uncommitted.
2. **Reviewability before permanence.** `git diff` (working dir vs index) and `git diff --staged` (index vs last commit) let you inspect exactly what you're about to make permanent, before you make it permanent.
3. **Building commits programmatically.** Tools, hooks, and scripts (§24) can manipulate the index directly (`git update-index`, low-level plumbing) without touching your working files at all — this is how features like "commit a specific historical blob" or automated formatting-on-commit work.
4. **Merge machinery.** During a merge conflict, the index temporarily holds *multiple* versions of a conflicted path (base, ours, theirs) simultaneously — a capability that wouldn't be possible without an intermediate structured area between disk and history. Detailed in §13.

## 4.3 Physical Anatomy of `.git`

Run `git init` and inspect what's created:

```
your-project/
├── .git/                      ← the repository (this whole directory)
│   ├── HEAD                   ← text file: "ref: refs/heads/main" (points to current branch)
│   ├── config                 ← repo-local configuration (§8)
│   ├── description            ← used only by GitWeb; safe to ignore
│   ├── index                  ← the staging area — binary file, one per repo
│   ├── objects/                ← the object database (§5) — ALL content lives here
│   │   ├── info/
│   │   ├── pack/               ← compressed packfiles (§7) — populated after gc
│   │   └── ab/                 ← loose objects, bucketed by first 2 hash chars
│   │       └── cdef1234...     ← one object, named by the remaining 38 hash chars
│   ├── refs/
│   │   ├── heads/              ← one file per local branch, e.g. refs/heads/main
│   │   ├── tags/                ← one file per tag
│   │   └── remotes/            ← remote-tracking branches, e.g. refs/remotes/origin/main
│   ├── logs/                    ← the reflog (§6) — history of ref movements
│   │   ├── HEAD
│   │   └── refs/heads/main
│   └── hooks/                   ← sample and active hook scripts (§24)
└── (your actual project files — the working directory, NOT inside .git)
```

> ⚠️ **Critical clarification:** the working directory (your actual files) sits **beside** `.git`, not inside it in any logical sense — `.git` is a self-contained database. If you deleted every file in your project except `.git` and ran `git checkout main`, Git would fully reconstruct every file from the object database. This is worth sitting with: **`.git/objects` alone is the entire, sufficient backup of your project's history.**

> 💡 **Tip:** Run `find .git -type f | head -30` after your first commit in a scratch repo. Seeing these files exist physically — not as an abstraction — is one of the fastest ways to de-mystify Git.

## 4.4 The Three Areas in Full Detail

### 4.4.1 Working Directory

- **What:** the checked-out files you edit with your editor/IDE.
- **State relative to history:** reflects one commit's content, *plus* any uncommitted edits you've made on top.
- **Git's view of it:** Git compares working-directory file content against the index to classify files as unmodified/modified (§3.3), using file modification-time and size as a fast pre-check before falling back to full content hashing — this is why `git status` is fast even on large repos (it usually avoids re-hashing unchanged files).

### 4.4.2 The Index (Staging Area)

- **Physical form:** `.git/index`, a single binary file — not human-readable, not a directory of copies.
- **Content:** for every staged path, a record containing the file mode, the blob hash it currently points to, the path name, and cached filesystem metadata (size, timestamps) used for fast change detection.
- **Key mental model:** the index is best understood as **"the tree that the next commit will contain, right now, if you ran `git commit` this instant."** `git add` updates entries in this file; it does not touch the object database's commit history at all — it only writes a new **blob object** for the file's current content (if that exact content doesn't already exist as a blob) and points the index entry at it.
- **Inspecting it directly:** `git ls-files -s` shows raw index entries (mode, hash, stage number, path) — the plumbing-level view of what `git status` summarizes in friendly language.

### 4.4.3 The Repository (Object Database + Refs)

- **Physical form:** `.git/objects` (content) + `.git/refs` (names pointing at content) + `.git/HEAD` (what's currently checked out).
- **Content:** every snapshot ever committed, stored as immutable objects (§5), plus movable pointers (branches) and fixed pointers (tags) into that object graph.
- **Key property:** nothing in here is ever edited in place. "Changing history" always means creating *new* objects and moving a ref to point at the new one — the old objects remain in the database, unreferenced, until garbage-collected (§7, §29).

## 4.5 Data Flow — The Complete Picture

```
 EDIT a file                    STAGE it                      COMMIT it
┌────────────────┐  git add   ┌──────────────┐  git commit  ┌───────────────────┐
│ Working         │ ─────────► │ Index        │ ────────────►│ Object database    │
│ Directory       │             │ (.git/index) │              │ (.git/objects)      │
│ file.txt: "v2"   │             │ file.txt→blob│              │ new commit object   │
└────────────────┘             │   hash B2     │              │ → tree object       │
        ▲                       └──────────────┘              │   → blob B2          │
        │                                                       │ branch ptr moves     │
        │        git checkout <commit> / git restore            │ to new commit        │
        └──────────────────────────────────────────────────────┴──────────────────────┘
```

Walking this concretely with a single file, `notes.txt`:

1. You edit `notes.txt` in your editor. Right now: working directory has the new content; index and last commit still have the old content. `git status` reports it **modified**.
2. `git add notes.txt`. Git computes the SHA of the new content, writes it as a **blob object** in `.git/objects` (if not already present), and updates the index entry for `notes.txt` to point at that new blob hash. `git status` now reports it **staged**.
3. `git commit -m "update notes"`. Git takes the entire current index content, builds the **tree objects** representing that directory structure, creates a **commit object** pointing at the root tree and at the previous commit (the new commit's parent), and moves the current branch's ref file to the new commit's hash. `git status` now reports **nothing to commit, working tree clean** — because working directory, index, and the new commit's content are all identical again.

## 4.6 Configuration Touchpoint (Preview)

The `.git/config` file (repo-local) and its two siblings — the global `~/.gitconfig` and the system-wide config — determine defaults like your identity and editor. Full depth, every relevant setting, is §8; noted here only because `.git/config` physically lives in the anatomy just diagrammed.

## 4.7 Commands That Directly Manipulate These Areas

| Command | Working Dir | Index | Object DB / Refs |
|---|---|---|---|
| `git status` | reads | reads | reads (compares against HEAD's tree) |
| `git add` | reads | **writes** | writes (new blobs only) |
| `git restore --staged <f>` | — | **writes** (reverts to HEAD's version) | reads |
| `git restore <f>` | **writes** (from index) | reads | — |
| `git commit` | — | reads | **writes** (tree, commit objects; moves branch ref) |
| `git checkout <branch>` | **writes** | **writes** | reads; moves HEAD |
| `git diff` | reads | reads (compares working dir ↔ index) | — |
| `git diff --staged` | — | reads | reads (compares index ↔ HEAD's tree) |

Full command-by-command documentation (syntax, flags, output, errors, security/performance notes) begins in §10 following the §9 template — this table exists purely to cement *which area* each command touches, before you learn its full syntax.

## 4.8 Hands-On Example — Watching the Three Areas Change

```bash
# Beginner-level walkthrough with expected output at each step

$ mkdir demo && cd demo && git init
Initialized empty Git repository in /home/user/demo/.git/

$ echo "line one" > notes.txt
$ git status
On branch main
No commits yet
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        notes.txt
nothing added to commit but untracked files present (use "git add" to track)

$ git add notes.txt
$ git status
On branch main
No commits yet
Changes to be committed:
  (use "git rm --cached <file>..." to unstage)
        new file:   notes.txt

$ git commit -m "Initial notes"
[main (root-commit) a1b2c3d] Initial notes
 1 file changed, 1 insertion(+)
 create mode 100644 notes.txt

$ echo "line two" >> notes.txt
$ git status
On branch main
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
        modified:   notes.txt
```

At this exact point: working directory has *two* lines, the index and the last commit both have *one* line — a live, visible demonstration of the three areas being in three different states simultaneously.

## 4.9 Production & Enterprise Usage Notes

- **Bare repositories** (§3.2, detailed §20) exist *only* as an object database plus refs — no working directory, no index in the normal sense. This is the correct shape for any repo that lives purely as a shared hub (a self-hosted Git server, or the backing store behind GitHub/GitLab) since nobody edits files directly there.
- **CI runners** typically perform a shallow or full checkout (materializing working directory from objects) fresh per job — understanding that checkout is "reconstruct working dir from the object DB via a tree walk" explains why large repos with deep history make shallow clones (`--depth`, §26) a meaningful CI speed optimization.
- **Pre-commit hooks** (§24) operate on the **index**, not the working directory — a hook that lints "what's staged" must read from the index, not just re-scan working-directory files, or it will incorrectly flag/pass content that isn't actually about to be committed (a common real bug in home-grown hook scripts).

## 4.10 Performance Considerations

- `git status` performance on very large repositories is dominated by **stat-ing every tracked file** to detect modifications; this is why huge monorepos benefit from filesystem watchers (`git config core.fsmonitor true`, using Watchman or Git's built-in FSMonitor) that cache "nothing changed here since last check" instead of re-stat-ing millions of files — covered fully in §26 and §29.
- The index being a **single file** (not one file per tracked path) is itself a performance decision: one sequential read/write beats filesystem overhead of touching thousands of tiny per-file records.

## 4.11 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `git status` painfully slow on a huge repo | Full working-tree stat scan, no fsmonitor | Enable `core.fsmonitor`; consider sparse-checkout (§26) |
| "Changes not staged" persists after `git add` | You edited the file *again* after staging (working dir now ahead of the index you staged) | `git add` again to re-stage the latest content |
| Index corruption (`fatal: index file corrupt`) | Rare disk/interrupt issue | `rm .git/index && git reset` (rebuilds index from HEAD; **any staged-but-uncommitted state is lost**, working directory files are untouched) |

## 4.12 Best Practices

- Stage deliberately and review with `git diff --staged` before every commit rather than reflexively `git add .`ing everything — this is what the index is *for*.
- Never hand-edit files inside `.git/` directly; always go through Git's commands, which maintain internal consistency (e.g., updating the index and moving refs together) that manual edits can break.

## 4.13 Anti-Patterns & Common Mistakes

- **Anti-pattern:** treating `git add .` as a mindless default habit regardless of what changed, which silently stages unrelated or unfinished work into the next commit.
- **Common mistake:** confusing `git diff` (working dir vs index — "what haven't I staged yet") with `git diff --staged` (index vs last commit — "what have I staged but not committed"). Interviewers frequently probe this exact distinction.

## 4.14 Interview Questions

**[Beginner] Q1. What's the difference between the working directory and the staging area?**
**Model answer:** The working directory is the actual files you see and edit on disk. The staging area, or index, is a separate record — physically a single file, `.git/index` — that tracks exactly which version of each file will go into the next commit. Editing a file changes the working directory only; `git add` copies that content's hash into the index; only `git commit` makes it a permanent, immutable part of history. They can all three be different at once, which is exactly what lets you stage part of your work while leaving other edits uncommitted.

**[Intermediate] Q2. If you deleted your entire project directory except the `.git` folder, could you recover everything?**
**Model answer:** Yes, as long as the last state was committed. The `.git` directory's object database contains every committed snapshot as content-addressed objects, and the refs point to the current branch tips. Running `git checkout <branch>` (or simply re-cloning from that `.git` folder) reconstructs the entire working directory by walking the tree objects referenced from the branch's latest commit. The one caveat is anything that was only in the working directory or only staged but never committed — that content was never written into a durably-referenced object and would be lost (though staged-but-uncommitted blobs technically do exist in the object database briefly and are recoverable via low-level tools until garbage collection, actual working-directory-only edits are simply gone).

**[Senior] Q3. Why does Git use a single binary index file instead of, say, one metadata file per tracked file?**
**Model answer:** Performance and simplicity. A single file lets Git read the entire staging state in one sequential I/O operation instead of opening potentially hundreds of thousands of small per-file records, which would be dominated by filesystem overhead (inode lookups, directory traversal) rather than actual data transfer, especially damaging on network filesystems or at large repo scale. It also makes the staging state atomic to update and easy to reason about — one file, one consistent snapshot of "what's queued for the next commit" — versus needing to keep many small files mutually consistent.

## 4.15 Common Misconceptions

1. **"Staging area = a folder somewhere with copies of my files."** It's one binary file recording hashes and paths, not a mirrored folder of file copies.
2. **"`git add` commits my changes."** It only stages them into the index; nothing is permanent history until `git commit`.
3. **"`.git` is just metadata; my real project data is safe in the working directory."** It's the reverse for anything committed — `.git/objects` *is* the durable copy; the working directory is a disposable, reconstructable materialization of it.

## 4.16 🔑 Key Takeaways

- Three areas: working directory (editable files), index (`.git/index`, the staged snapshot), object database + refs (`.git/objects` + `.git/refs`, the permanent history).
- `git add` writes new blobs and updates index entries; `git commit` builds tree/commit objects from the index and moves the branch ref — two distinct operations touching two distinct areas.
- `.git/objects` alone is sufficient to reconstruct the entire project for any committed state; the working directory is disposable and rebuildable.
- The index exists specifically to enable partial/reviewable/programmatic commits — not as unnecessary ceremony.

## 4.17 Related Concepts & What's Next

Every object type mentioned here in passing — blob, tree, commit — gets its exact byte-level structure, hashing method, and relationships in Section 5, which is where "content-addressable storage" and "Merkle DAG" (both mentioned in §2) become concrete rather than conceptual.

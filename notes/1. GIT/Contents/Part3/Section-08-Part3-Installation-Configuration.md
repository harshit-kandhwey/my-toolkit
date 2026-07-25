# Section 8 (Part 3): Installation & Configuration

## 8.1 Definition

**Plain language:** Before Git is useful, you install the program itself, then tell it who you are and how you like it to behave — identity, default editor, default branch name, authentication method to reach remote servers, and dozens of optional preferences.

**Precise:** Git installation places the `git` binary (plus supporting tooling — Git Bash, credential helpers, GUI launchers on some platforms) on your system; Git configuration is a layered key-value store, read from three (or four, counting a rarely-used "worktree" scope) increasingly specific files, that governs everything from `user.name` to network transport behavior. Nothing in this section touches the object model (§5) or refs (§6) — it is entirely about the environment Git runs _in_, and the credentials it uses to talk to a remote (deep dive in §20).

## 8.2 Why It Exists / Problem It Solves

1. **Every commit needs an author.** Git refuses (or at least strongly warns) to build commit objects without `user.name` and `user.email` set, because that metadata is baked permanently into every commit object (§5) — it cannot be silently defaulted the way a filename can.
2. **One tool, many humans, many preferences.** A single `git` binary serves millions of different workflows; rather than hard-code behavior, Git externalizes preferences (editor, line-ending policy, default branch name, aliases) into config files so the same binary adapts per machine and per repository.
3. **Authentication is not the same problem as version control.** Talking to a remote server (GitHub, GitLab, a self-hosted server) requires proving _who you are_ over a network — a concern orthogonal to Git's local object model, solved by layering standard mechanisms (SSH keys, HTTPS credential helpers) on top rather than inventing a proprietary one.

## 8.3 Installing Git

### 8.3.1 Windows

The standard distribution is **Git for Windows** (`git-scm.com`), which bundles several distinct things in one installer:

- **Git itself** — the `git` command available from any shell.
- **Git Bash** — a MinGW/MSYS2-based Unix-like shell, so Windows users get a bash environment with familiar Unix commands (`ls`, `grep`, `ssh`) rather than being limited to `cmd.exe` semantics. Most Git tutorials assume this shell.
- **Git GUI / gitk** — basic bundled graphical tools (rarely anyone's daily driver today, but present).
- **Windows Credential Manager integration** — the installer offers to configure `credential.helper` to `manager` (formerly `manager-core`), which stores HTTPS credentials/tokens securely in the Windows Credential Store instead of a plaintext file (8.7).

Installer choices worth understanding rather than clicking through blindly:

- **Line-ending conversion** (the "Checkout Windows-style, commit Unix-style" prompt) sets `core.autocrlf` — full treatment of why this matters is §11.5; the safe modern default on Windows is `autocrlf=true`, though a `.gitattributes` policy (§11) is the more robust fix.
- **Default editor** — the installer lets you pick Vim, Notepad, VS Code, or others for `core.editor`; this only matters for operations that open an editor (commit messages without `-m`, interactive rebase in §14, `git config -e`).
- **PATH environment** — "Git from the command line and also from 3rd-party software" is the recommended option so `git` works from any terminal, not just Git Bash.

### 8.3.2 macOS

Three common paths, all equally valid:

- **Xcode Command Line Tools** — running `git --version` on a fresh Mac triggers an install prompt if Git isn't present; this ships an Apple-maintained build (sometimes trailing the latest upstream release).
- **Homebrew** — `brew install git` gives you a more current, easily-updatable build (`brew upgrade git`); this is the common choice among engineers who want the newest features/fixes.
- **Official installer / MacPorts** — less common but available for cases where Homebrew isn't in use.

### 8.3.3 Linux

Installed via the distribution's package manager — `apt install git` (Debian/Ubuntu), `dnf install git` (Fedora/RHEL), `pacman -S git` (Arch). Distro repositories sometimes lag the latest Git release by months; if you need a newer version for a specific feature, add the relevant PPA/repo (e.g. Ubuntu's `ppa:git-core/ppa`) or build from source.

### 8.3.4 Verifying the Install

```bash
# Purpose: confirm Git is installed and check which version
$ git --version
git version 2.44.0.windows.1
```

```bash
# Purpose: locate exactly which binary is being run (useful when multiple Gits exist, e.g. WSL vs native Windows Git)
$ which git        # Git Bash / macOS / Linux
/usr/bin/git
```

> 💡 **Tip:** Version matters more than beginners expect — features referenced throughout this knowledge base (`git switch`/`git restore` from 2.23+, `git range-diff`, improvements to `rebase --update-refs`) simply don't exist on old Git versions still lurking on some corporate machines and CI images. If a command in this series "doesn't exist" for you, checking `git --version` is the first troubleshooting step.

## 8.4 The Three Configuration Scopes

Git configuration is layered: more specific scopes override less specific ones.

| Scope                 | File location                                                                  | Applies to                                           | Flag                                                    |
| --------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------- | ------------------------------------------------------- |
| **System**            | `/etc/gitconfig` (Linux/Mac) or `C:\Program Files\Git\etc\gitconfig` (Windows) | Every user on the machine                            | `git config --system`                                   |
| **Global**            | `~/.gitconfig` (or `~/.config/git/config`)                                     | Every repository for the current user                | `git config --global`                                   |
| **Local**             | `.git/config` inside a specific repository                                     | That one repository only                             | `git config --local` (or no flag — this is the default) |
| **Worktree** _(rare)_ | `.git/config.worktree`, requires `extensions.worktreeConfig`                   | One worktree (§31) of a repo with multiple worktrees | `git config --worktree`                                 |

**Precedence: local beats global beats system.** A `user.email` set locally in one repo (common for "use my work email only in this company's repos") silently overrides whatever is set globally, which is precisely the intended use case, not a bug to be confused by.

```
System (all users on machine)
        │  overridden by
        ▼
Global (~/.gitconfig — this user, all repos)
        │  overridden by
        ▼
Local (.git/config — this repo only)
```

### 8.4.1 Setting values

```bash
# Purpose: set your identity globally — required before your first commit anywhere
$ git config --global user.name "Harshit Kandhwey"
$ git config --global user.email "harshitkandhwey@gmail.com"

# Purpose: override just for this one repository (e.g., a client's repo needing a different email)
$ git config --local user.email "harshit@client-example.com"
```

### 8.4.2 Reading values

```bash
# Purpose: read one specific key, respecting precedence (shows the effective value)
$ git config user.email
harshit@client-example.com

# Purpose: list every effective config value
$ git config --list

# Purpose: list every value AND which file each one came from — invaluable when a setting
# isn't behaving as expected and you don't know which scope is winning
$ git config --list --show-origin
file:C:/Users/harsh/.gitconfig     user.name=Harshit Kandhwey
file:C:/Users/harsh/.gitconfig     user.email=harshitkandhwey@gmail.com
file:.git/config                   user.email=harshit@client-example.com
```

> ⚠️ **Common confusion to preempt:** `git config --list` shows the _merged, effective_ configuration — it does not tell you which file a value came from unless you add `--show-origin`. Debugging "why is my commit using the wrong email" almost always means reaching for `--show-origin` rather than staring at `--list` output.

### 8.4.3 Editing directly

All three files are plain INI-style text and can be hand-edited:

```bash
# Purpose: open the global config in your configured editor
$ git config --global -e
```

```ini
[user]
    name = Harshit Kandhwey
    email = harshitkandhwey@gmail.com
[init]
    defaultBranch = main
[alias]
    co = checkout
    st = status
```

Hand-editing is perfectly safe and common — unlike `.git/objects` or `.git/index` (§4), config files are plain text with no binary structure or consistency invariants to break.

## 8.5 First-Time Setup Checklist

```bash
# Purpose: identity — mandatory before committing
$ git config --global user.name "Your Name"
$ git config --global user.email "you@example.com"

# Purpose: modern Git (2.28+) requires you to set a default branch name explicitly,
# or every new `git init` prints a warning and falls back to "master"
$ git config --global init.defaultBranch main

# Purpose: choose the editor Git opens for commit messages, interactive rebase, etc.
$ git config --global core.editor "code --wait"   # VS Code
# or: git config --global core.editor "vim"
# or: git config --global core.editor "notepad"   # Windows, simplest but weakest option
```

> 💡 **Tip:** `init.defaultBranch` only affects _new_ repositories created after you set it (via `git init` or `git clone` when the remote's default happens to match) — it has no effect on existing repos, which keep whatever branch name they already have. The industry-wide move from `master` to `main` as the conventional default (GitHub changed its own default in 2020) is a naming convention, not a Git feature; nothing internally treats `main` specially.

## 8.6 Useful Aliases

Aliases are just config entries under `[alias]` that expand a short name into a full Git command (including arbitrary flags):

```bash
# Purpose: create common shorthand aliases
$ git config --global alias.co checkout
$ git config --global alias.br branch
$ git config --global alias.st status
$ git config --global alias.cm "commit -m"
$ git config --global alias.lg "log --oneline --graph --all --decorate"
```

```bash
# Usage after aliasing
$ git st
$ git lg
```

> 💡 **Tip:** Prefixing an alias body with `!` lets it run an arbitrary shell command rather than just another Git subcommand, e.g. `git config --global alias.root '!pwd'` — this is how power users build small custom workflows without leaving Git's own command surface. Full scripting/hooks territory is §24.

## 8.7 SSH Keys and Remote Authentication

Talking to a remote host (GitHub, GitLab, a company Git server) requires proving your identity over the network. Git supports two transport families for this, and understanding both — plus _when_ each authentication step happens — matters from day one, even though full remote mechanics are §20.

### 8.7.1 Generating an SSH key pair

```bash
# Purpose: generate a modern Ed25519 key pair (preferred over older RSA keys — smaller, faster, equally secure)
$ ssh-keygen -t ed25519 -C "harshitkandhwey@gmail.com"
Generating public/private ed25519 key pair.
Enter file in which to save the key (/home/user/.ssh/id_ed25519):
Enter passphrase (empty for no passphrase):
```

This produces two files: `~/.ssh/id_ed25519` (the **private** key — never shared, never committed, never emailed) and `~/.ssh/id_ed25519.pub` (the **public** key — safe to hand to any hosting platform).

```bash
# Purpose: copy the public key to your clipboard / print it to paste into GitHub/GitLab settings
$ cat ~/.ssh/id_ed25519.pub
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx harshitkandhwey@gmail.com
```

You then paste this into the hosting platform's **SSH keys** settings page (GitHub: Settings → SSH and GPG keys → New SSH key).

### 8.7.2 Testing the connection

```bash
# Purpose: verify the key is recognized by GitHub without performing any Git operation
$ ssh -T git@github.com
Hi harshitkandhwey! You've successfully authenticated, but GitHub does not
provide shell access.
```

That message — despite looking like an error — is the expected **success** output; GitHub deliberately has no interactive shell to give you over this connection, it only confirms the key.

### 8.7.3 HTTPS vs SSH remote URLs

| Aspect                        | HTTPS                                                                                             | SSH                                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| URL form                      | `https://github.com/user/repo.git`                                                                | `git@github.com:user/repo.git`                                                                |
| Auth mechanism                | Username + Personal Access Token (PAT), or a credential helper caching one                        | Public/private key pair                                                                       |
| Firewall friendliness         | Excellent — uses port 443, same as normal web traffic, works through almost every corporate proxy | Uses port 22, which some corporate/hotel/airport networks block                               |
| First-time setup              | Generate a PAT on the hosting platform                                                            | Generate a key pair, register the public key                                                  |
| Per-repo credential switching | Easy with credential helpers or `.netrc`-style scoping                                            | Requires SSH config `Host` aliases with different `IdentityFile`s (§20) for multiple accounts |
| Typical enterprise preference | Common where port 22 is blocked, or where token-based auth integrates with SSO                    | Common where key-based auth is mandated and port 22 is open                                   |

Neither is objectively "better" — they are two transport/authentication mechanisms Git supports interchangeably for the same underlying operations (fetch/push). A single repository can even have different remotes configured with different URL schemes.

### 8.7.4 Credential helpers (HTTPS)

Since 2021, GitHub (and most major hosts) removed plain password authentication over HTTPS entirely — you authenticate with a **Personal Access Token (PAT)** (or, for organizations, an OAuth app / GitHub App token) used _in place of_ a password. Typing that token on every push would be unbearable, so Git delegates storage to a **credential helper**:

```bash
# Purpose: check which credential helper is currently configured
$ git config --get credential.helper
manager

# Purpose: set the Windows/cross-platform "Git Credential Manager" explicitly (installed by Git for Windows by default)
$ git config --global credential.helper manager

# Purpose: on Linux without a GUI keyring, a simple (less secure) plaintext cache is available
$ git config --global credential.helper store   # writes to ~/.git-credentials in plaintext — understand the trade-off

# Purpose: a time-limited in-memory cache instead of permanent storage
$ git config --global credential.helper 'cache --timeout=3600'
```

The first time you push over HTTPS, Git prompts for username + token (or opens a browser for OAuth, depending on the helper); the credential helper then stores it securely (Windows Credential Manager, macOS Keychain, or the GNOME/KDE keyring on Linux via `libsecret`) so subsequent pushes are silent.

> ⚠️ **Critical clarification:** a Personal Access Token is not the same as your account password — it is a separate, scoped, revocable credential (you choose its permissions and expiry) that you generate from the hosting platform's developer settings. Treat a PAT exactly like a password: never commit it, never paste it into chat, and revoke it immediately if it leaks (full secrets-in-history remediation is §28).

## 8.8 Configuring an External Diff/Merge Tool

Git's built-in text diff output is adequate for quick review, but a visual diff/merge tool is far superior for genuinely gnarly merge conflicts (full conflict-resolution workflow in §13). Git lets you register any tool via config:

```bash
# Purpose: use VS Code as both the diff and merge tool
$ git config --global diff.tool vscode
$ git config --global difftool.vscode.cmd 'code --wait --diff $LOCAL $REMOTE'

$ git config --global merge.tool vscode
$ git config --global mergetool.vscode.cmd 'code --wait $MERGED'
```

```bash
# Usage
$ git difftool              # opens each changed file in VS Code's diff view, one by one
$ git mergetool             # opens each conflicted file in VS Code for manual resolution
```

Other popular choices follow the same pattern — register a name under `diff.tool`/`merge.tool`, then define its invocation command:

```bash
# Purpose: register a dedicated GUI merge tool (example: KDiff3)
$ git config --global merge.tool kdiff3
$ git config --global mergetool.kdiff3.path "/usr/bin/kdiff3"

# Purpose: skip Git's habit of creating .orig backup files after a successful mergetool resolution
$ git config --global mergetool.keepBackup false
```

> 💡 **Tip:** `git difftool` and `git mergetool` are _wrappers_ — they don't replace `git diff`/conflict markers, they just launch your chosen external program for each file, then hand control back to Git once you close it. You can always fall back to plain-text `git diff` and manual conflict-marker editing even with a tool configured; nothing is lost by configuring one.

## 8.9 Other Commonly Tuned Settings

```bash
# Purpose: make `git push` default to pushing only the current branch to its tracked upstream (modern default, but worth setting explicitly on older Git)
$ git config --global push.default simple

# Purpose: color output in terminals that support it
$ git config --global color.ui auto

# Purpose: control line-ending conversion (full depth in §11.5)
$ git config --global core.autocrlf true    # Windows
$ git config --global core.autocrlf input   # Mac/Linux
```

## 8.10 Hands-On: From Zero to First Configured Commit

```bash
# Purpose: complete first-time setup sequence on a fresh machine
$ git config --global user.name "Harshit Kandhwey"
$ git config --global user.email "harshitkandhwey@gmail.com"
$ git config --global init.defaultBranch main
$ git config --global core.editor "code --wait"
$ git config --global credential.helper manager

# Purpose: verify everything landed in the global file, not scattered elsewhere
$ git config --list --show-origin | grep gitconfig
```

## 8.11 Interview Questions

**[Beginner] Q1. What are the three configuration scopes in Git, and which one wins if a setting exists in more than one?**
**Model answer:** Git configuration exists at system scope (`/etc/gitconfig`, all users on the machine), global scope (`~/.gitconfig`, all repos for the current user), and local scope (`.git/config`, one specific repository). More specific scopes override less specific ones — local beats global, which beats system — which is exactly what allows a common pattern like setting your personal email globally but overriding it locally in a work repository.

**[Intermediate] Q2. Why can't you just type your GitHub password when pushing over HTTPS anymore, and what replaced it?**
**Model answer:** GitHub and most major hosting platforms deprecated plain password authentication over HTTPS Git operations around 2021 for security reasons — passwords are long-lived, broad-scope, and hard to rotate safely. They were replaced by Personal Access Tokens: a separate, revocable credential you generate with a specific scope and expiry, used in the password field. Typing a token manually on every push is impractical, so Git relies on a credential helper (Windows Credential Manager, macOS Keychain, or `git-credential-manager` cross-platform) to securely cache it after the first prompt, so subsequent operations are silent.

**[Senior] Q3. A new hire's commits are showing up under the wrong name in the company's repos even though they set `user.name` globally. What's your debugging approach?**
**Model answer:** The most likely cause is a local override — either a stale `.git/config` in that specific repo from a previous clone or template, or an earlier `git config --local user.name` someone ran and forgot about, which silently wins over the global setting per Git's precedence rules. I'd run `git config --list --show-origin` inside the affected repo to see exactly which file each effective value is coming from, rather than guessing. If it's a systemic problem across many repos (e.g., a shared clone template or CI image with a baked-in identity), I'd also check the system scope and any global `includeIf` directives that conditionally apply different config based on the repo's directory path — a common enterprise pattern for "use this identity under `~/work/`, this one under `~/personal/`" that can surprise someone unaware it exists.

## 8.12 Common Misconceptions

1. **"Git needs a GitHub account to work."** Git is fully functional entirely locally — commits, branches, merges, history — with zero network access or hosting account. A hosting platform is only needed for remote collaboration (§20, §23).
2. **"SSH and HTTPS remotes give different Git functionality."** They are purely different authentication/transport mechanisms for the exact same set of operations (fetch, push, clone) — neither unlocks or restricts any Git feature.
3. **"My GitHub password is my Git credential."** Since the PAT-only transition, your account password is not usable for HTTPS Git operations at all; only a token (or SSH key) works.
4. **"`git config --list` tells me which file a setting came from."** It shows the merged, effective values only; `--show-origin` is required to see the source file.

## 8.13 🔑 Key Takeaways

- Installation on Windows brings Git Bash and Windows Credential Manager integration alongside the `git` binary itself; macOS/Linux installs are simpler package-manager affairs.
- Config is layered: system → global → local (→ worktree), each overriding the previous; `--show-origin` is the tool for debugging precedence confusion.
- `user.name`/`user.email` are mandatory in practice; `init.defaultBranch` and aliases are quality-of-life defaults every serious setup configures.
- SSH keys (`ssh-keygen`, tested with `ssh -T git@github.com`) and HTTPS PATs via credential helpers are the two supported authentication paths to a remote — neither is universally superior, they trade off firewall friendliness against setup mechanics.
- `diff.tool`/`merge.tool` config wraps an external GUI tool around `git difftool`/`git mergetool` without replacing Git's own plain-text diff/conflict-marker mechanics underneath.

## 8.14 Related Concepts & What's Next

Configuration set up here — identity, credential helpers, SSH keys — becomes load-bearing the moment you touch a remote, and §20 (Remotes in Depth) revisits authentication with full push/fetch/pull mechanics, multiple-remote setups, and per-host SSH config for juggling multiple accounts. The merge tool configured in 8.8 becomes practically necessary once §13 (Merging) introduces real conflict resolution. With Git installed and configured, §9 moves to actually creating and cloning your first repositories.

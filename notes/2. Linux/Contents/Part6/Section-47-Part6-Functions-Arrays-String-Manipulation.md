# Section 47 (Part 6): Functions, Arrays, and String Manipulation in Bash

## 1. Function Definition Syntax: Two Forms, One Recommendation

Bash supports two syntaxes for defining a function, and they're equivalent in behavior but not in portability:

```bash
function greet {
    echo "Hello, $1"
}
```

```bash
greet() {
    echo "Hello, $1"
}
```

The `function name { ... }` form is a bash-specific (and ksh-derived) keyword. The `name() { ... }` form — no `function` keyword, just a name followed by empty parentheses — is POSIX-compliant and works identically in `sh`, `dash`, and every POSIX-conformant shell, not just bash. Combining both (`function greet() { ... }`) also works in bash but is redundant and gains nothing.

> 💡 **Tip:** Default to `name() { ... }` for anything that might ever run under a stricter shell than bash (a `#!/bin/sh` script, a Debian `dash`-backed system script, a CI step that swaps interpreters) — it's the more portable of two syntaxes that do exactly the same thing in bash itself, so there's no cost to preferring it even when you know bash is guaranteed.

A function must be **defined before it's called** — bash reads and executes top to bottom, and unlike some languages there's no hoisting; calling `greet "Alice"` above a `greet() { ... }` definition fails with "command not found" because bash hasn't parsed the definition yet.

## 2. Function Arguments: Their Own `$1`/`$@`/`$#` Scope

[§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) covered positional parameters (`$1`, `$@`, `$#`) as how a _script_ reads its arguments. Functions get an entirely separate copy of the same mechanism — calling a function with arguments gives that function its own `$1`, `$2`, `$@`, and `$#`, temporarily shadowing whatever the script's own positional parameters were:

```bash
#!/usr/bin/env bash
deploy() {
    local env="$1"
    local version="$2"
    echo "Deploying version $version to $env"
}

deploy "production" "1.4.2"
echo "Script's own \$1 is still: $1"
```

```bash
$ ./run.sh staging
Deploying version 1.4.2 to production
Script's own $1 is still: staging
```

Inside `deploy`, `$1` is `"production"` and `$2` is `"1.4.2"` — the arguments passed to the _function call_, not the script's own `$1`. Once the function returns, the script's original `$1` (`"staging"`) is exactly as it was; the function's parameter scope doesn't leak in either direction. `$@`, `$*`, and `$#` inside a function follow the same rule — they all refer to the function's own arguments, and the `"$@"` vs `$*` quoting distinction from [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) applies identically inside a function body.

## 3. `local`: Variable Scoping, and the Global-by-Default Gotcha

Bash variables are **global by default**, including variables assigned inside a function — this is the opposite of the scoping model most other languages default to, and it's a frequent source of bugs for anyone coming from a language where function-local variables are the default assumption:

```bash
#!/usr/bin/env bash
counter=0

increment() {
    counter=$((counter + 1))   # no 'local' — modifies the GLOBAL counter
}

increment
increment
echo "$counter"   # 2, not "undefined" or an error
```

`local` restricts a variable's visibility and lifetime to the function it's declared in, shadowing any global variable of the same name for the function's duration and disappearing entirely when the function returns:

```bash
#!/usr/bin/env bash
counter=0

increment() {
    local counter=0     # this counter is local — the global 'counter' is untouched
    counter=$((counter + 1))
    echo "inside: $counter"
}

increment
echo "outside: $counter"
```

```bash
$ ./local.sh
inside: 1
outside: 0
```

> ⚠️ **Warning:** Forgetting `local` is one of the most common bash bugs in scripts with more than a couple of functions, and it's insidious precisely because it usually _works_ in isolated testing — a function that assigns to `result` without `local` will silently clobber a global `result` variable set by an entirely unrelated part of the script, and the bug only surfaces once two functions happen to use the same variable name, often far later and in a different code path than where the assignment actually happened. Declare every variable a function doesn't explicitly intend to expose globally as `local`, as a default habit rather than an afterthought.

`local` can be combined with assignment on one line (`local result="$1"`) — but one subtlety worth knowing: `local var=$(some_command)` discards the exit status of `some_command`, because `local` itself is the last command that runs and its own exit status (from the declaration) is what `$?` sees afterward. If a script relies on `set -e` ([§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)) to catch a failing command substitution, splitting the declaration and assignment (`local var; var=$(some_command)`) preserves the inner command's exit status where `set -e` can actually see it.

## 4. Return Values: `return` Is Exit-Code-Only, Not for Data

`return N` sets a function's exit status, exactly like `exit N` sets a script's — a number from `0` to `255`, following the same "0 = success, nonzero = failure" convention [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) covered for scripts. If a function has no explicit `return`, its exit status is simply the exit status of the last command it ran, the same implicit fallback [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) described for scripts.

```bash
file_exists() {
    if [[ -f "$1" ]]; then
        return 0
    else
        return 1
    fi
}

if file_exists "/etc/hosts"; then
    echo "found it"
fi
```

> ⚠️ **Warning:** A very common misconception among people new to bash is treating `return` as if it could hand back arbitrary data, the way `return` works in most general-purpose languages. It cannot — `return`'s argument is coerced to an integer in the 0–255 range, and anything outside that range wraps around (`return 256` actually sets exit status `0`; `return -1` becomes `255`). Trying to `return "some string"` or `return 42000` doesn't do what it looks like it does, and the failure mode is silent, not an error.

**The actual idiom for "returning" data from a bash function is `echo` (or `printf`) plus command substitution** — the function writes its result to stdout, and the caller captures that output with `$(...)`:

```bash
get_env_name() {
    local branch="$1"
    case "$branch" in
        main)    echo "production" ;;
        staging) echo "staging" ;;
        *)       echo "development" ;;
    esac
}

target_env=$(get_env_name "main")
echo "Deploying to: $target_env"
```

This works because command substitution captures stdout, and a function is just another command from the caller's perspective. It composes cleanly with `return`'s actual role: a function can `echo` its result _and_ `return` a meaningful exit code, letting the caller check both — did it succeed (`$?` / `return`), and what did it produce (`$(...)` capturing the `echo`).

## 5. Indexed Arrays

Bash indexed arrays hold an ordered list of values, indexed numerically from `0`:

```bash
hosts=(web01 web02 db01)
```

**Common operations:**

```bash
echo "${hosts[0]}"        # web01 — single element access
echo "${hosts[@]}"        # web01 web02 db01 — all elements
echo "${#hosts[@]}"        # 3 — element count
hosts+=(cache01)          # append — hosts is now (web01 web02 db01 cache01)
hosts[1]="web02-replaced" # overwrite by index
unset 'hosts[2]'          # remove db01 by index — leaves a gap, doesn't renumber
```

**Iterating** over an array follows the exact same quoting logic [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) established for `"$@"` vs `$*`, and it matters just as much:

```bash
for host in "${hosts[@]}"; do
    echo "Checking: $host"
done
```

`"${hosts[@]}"` — quoted, with `@` — expands each array element as its own separate word, exactly preserving elements that contain spaces (`"web server 01"` stays one item). `${hosts[@]}` unquoted, or `"${hosts[*]}"` quoted with `*`, both flatten and re-split on `$IFS`, which silently breaks any element containing whitespace — the identical word-splitting hazard [§42](./Section-42-Part6-Shell-Basics-Variables-Quoting-Expansion-Command-Substitution.md) covered for scalar variables and [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) covered for `$@`/`$*`, just showing up again one level up in arrays. Always quote `"${arr[@]}"` when iterating or passing array elements onward, as a default, not a special case.

## 6. Associative Arrays (Bash 4+)

**Associative arrays** — key-value maps, not present in bash 3.x (notably the ancient bash still shipped as `/bin/bash` on stock macOS) — require an explicit `declare -A` before use:

```bash
declare -A service_ports
service_ports[ssh]=22
service_ports[https]=443
service_ports[postgres]=5432
```

```bash
echo "${service_ports[https]}"     # 443 — value lookup by key
echo "${!service_ports[@]}"        # ssh https postgres — all keys (note the '!')
echo "${service_ports[@]}"         # 22 443 5432 — all values
echo "${#service_ports[@]}"        # 3 — entry count
unset 'service_ports[ssh]'         # remove a key
```

`${!arrayname[@]}` — the `!` prefix — is specifically how keys are enumerated; it's easy to forget and reach for `${arrayname[@]}` instead, which gives values, not keys. Iterating over both together is a common pattern:

```bash
for key in "${!service_ports[@]}"; do
    echo "$key -> ${service_ports[$key]}"
done
```

Indexed arrays technically support sparse/arbitrary numeric indices too (`arr[100]=x` is legal without 99 preceding elements), but associative arrays are the correct tool whenever the natural index is a name rather than a position — configuration-like lookups, counting occurrences by label, or anything else that reads more naturally as `$service_ports[https]` than `$ports[2]`.

## 7. String Manipulation via Parameter Expansion

Bash's parameter expansion syntax includes a set of operators for manipulating strings **without spawning an external process** — no `sed`, `awk`, or `cut` subshell, which matters in a tight loop where forking a process per iteration is measurably slower than an in-shell string operation.

**Prefix and suffix removal** — `#`/`##` strip from the front, `%`/`%%` strip from the back, and single-vs-double controls greedy vs. minimal matching:

```bash
path="/var/log/app/access.log"

echo "${path#*/}"     # var/log/app/access.log   — strip shortest match from the front
echo "${path##*/}"    # access.log                — strip longest match from the front (basename-style)
echo "${path%/*}"     # /var/log/app              — strip shortest match from the back (dirname-style)
echo "${path%%.*}"    # /var/log/app/access       — strip longest match from the back
```

**Substitution** — `/` replaces the first match, `//` replaces all matches:

```bash
name="web-server-01"
echo "${name/-/_}"     # web_server-01   — first '-' only
echo "${name//-/_}"    # web_server_01   — all '-' replaced
```

**Length and substring:**

```bash
str="production"
echo "${#str}"          # 10           — length
echo "${str:0:4}"       # prod         — substring: offset 0, length 4
echo "${str:4}"         # uction       — offset 4 to the end
echo "${str: -4}"       # tion         — negative offset (note the required space before '-')
```

**Comparison table:**

| Expansion              | Operation                                       |
| ---------------------- | ----------------------------------------------- |
| `${var#pattern}`       | Remove shortest matching prefix                 |
| `${var##pattern}`      | Remove longest matching prefix                  |
| `${var%pattern}`       | Remove shortest matching suffix                 |
| `${var%%pattern}`      | Remove longest matching suffix                  |
| `${var/pat/repl}`      | Replace first match of `pat` with `repl`        |
| `${var//pat/repl}`     | Replace all matches of `pat` with `repl`        |
| `${#var}`              | Length of `var`                                 |
| `${var:offset:length}` | Substring, starting at `offset`, `length` chars |

> 💡 **Tip:** These operators are genuinely worth reaching for — extracting a filename from a path, stripping a known suffix, or a single find/replace are common enough that spawning `sed` or `basename` for them is unnecessary overhead in a hot loop. But this table is close to the practical ceiling of what's worth doing in raw parameter expansion. Anything beyond it — regex with capture groups, conditional replacement, multi-line text, column-based extraction — gets noticeably harder to read as nested `${var...}` expressions than as a single `sed` or `awk` invocation, which is exactly [§48](./Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md)'s (next) territory. Treat parameter expansion as the right tool for simple, single-value string cleanup, not as a substitute for a real text-processing tool once the logic gets any more involved than the operators in this table.

## 8. Common Misconceptions

1. **"`return` can hand back any value a function computes."** It can only set an exit code, `0`–`255`, and anything outside that range wraps around silently — it is not a data-return mechanism (4). "Returning" data is done by `echo`ing and capturing the output with `$(...)`.
2. **"Variables assigned inside a function are automatically local to it."** The opposite is true — bash variables are global by default even when assigned inside a function, and `local` must be declared explicitly to scope a variable to the function (3). Omitting it is a common source of one function silently clobbering another's variable.
3. **"`${arr[@]}` and `"${arr[@]}"` behave the same."** They diverge exactly the way `$@` and `"$@"` do ([§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)) — unquoted, array elements are word-split and glob-expanded; quoted, each element is preserved as its own word regardless of embedded whitespace (5).
4. **"Associative arrays are just indexed arrays with string keys."** They require `declare -A` explicitly and are a bash 4+ feature entirely absent in older bash (notably stock macOS bash) — code relying on them isn't portable to every environment bash itself runs on (6).
5. **"Parameter expansion string operators can replace `sed`/`awk` for any text task."** They cover simple, single-value operations well, but nested parameter expansions for anything involving regex capture groups, multi-line text, or column extraction becomes hard to read fast — that's the point where reaching for `sed`/`awk` ([§48](./Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md)) is the more maintainable choice (7).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's wrong with this function, and what would you change?"_

```bash
set_status() {
    status="ready"
}
```

**Model answer:** It's missing `local` — `status="ready"` assigns to a global variable named `status`, not a variable scoped to `set_status`. If anything else in the script also uses a variable called `status`, this function will silently overwrite it, and the bug will only show up once that collision actually happens, likely far from this function's definition. I'd write it as `local status="ready"` unless the whole point of the function actually is to set a global, in which case I'd say so with a comment, because relying on bash's global-by-default behavior implicitly is easy to get wrong.
_What the interviewer is probing for:_ Knowing that bash's default scoping is global, not local, which is the opposite of most languages' default and a frequent real-world source of bugs.

**🎯 Intermediate:** _"How would you get a value back out of a bash function into a variable in the calling code?"_
**Model answer:** `return` only sets a numeric exit status from 0–255, so it can't carry data back — the idiom is for the function to `echo` (or `printf`) its result to stdout, and for the caller to capture that with command substitution: `result=$(my_function "$arg")`. If the function also needs to signal success/failure independently of the value it produces, I'd have it both `echo` the value and `return` a meaningful exit code, and have the caller check `$?` right after the assignment if that distinction matters, since `$?` after `result=$(...)` reflects the command substitution's exit status.
_What the interviewer is probing for:_ Clear separation of `return` (control flow signal) from output capture (actual data), and awareness that both can be used together deliberately.

**🎯 Senior:** _"You're debugging a 300-line script where a variable seems to have the wrong value partway through, in a code path that doesn't obviously touch it. What's your first hypothesis given what you know about bash function scoping?"_
**Model answer:** My first hypothesis is a missing `local` somewhere — bash functions don't get implicit local scoping, so any function anywhere in that 300 lines that assigns to a variable with that same name, without declaring it `local`, is silently mutating the global rather than operating on its own copy. I'd grep the whole file for that variable name across every function definition, specifically looking for assignments without a preceding `local` declaration in the same function, rather than assuming the bug is near where the wrong value is observed — because the actual mutation could be in a completely unrelated function that happens to reuse a common variable name like `result`, `status`, or `count`. This is exactly the failure mode that makes disciplined `local` usage worth enforcing as a default habit rather than an occasional cleanup, especially as scripts grow past a couple of functions.
_What the interviewer is probing for:_ Recognizing global-by-default scoping as a systemic risk in larger scripts, not just a one-off gotcha, and having a concrete debugging strategy (grep for unscoped assignments) rather than just naming the concept.

**🎯 Architect:** _"A junior engineer wants to build a small config-lookup layer entirely in bash parameter expansion and associative arrays instead of reaching for a real templating tool or `jq`/`yq`. How do you advise them?"_
**Model answer:** Associative arrays and parameter expansion are fine, and genuinely the right tool, for simple, bounded cases — a lookup table of a dozen known keys to values, or stripping/substituting a handful of fixed patterns in a path or string, benefits from staying in-shell rather than spawning an external process per lookup. Where I'd push back is the moment the "config" starts needing nested structure, arrays of objects, type awareness, or non-trivial parsing logic — bash associative arrays are flat, string-keyed, string-valued, bash-4+-only (a portability constraint worth flagging up front if this needs to run anywhere older or on macOS's stock bash), and nested parameter expansions for anything beyond simple prefix/suffix/substitution get hard to read and debug fast. At that point a real structured-data tool (`jq` for JSON, `yq` for YAML) or a proper config file format the script just reads is both more correct and more maintainable than continuing to stretch bash's string primitives to cover a problem they weren't designed for. I'd frame it as: bash string/array manipulation is for cleanup and glue, not for owning structured configuration as complexity grows.
_What the interviewer is probing for:_ Judgment about where bash's native data structures stop being the right tool, not just knowledge that they exist — and the ability to articulate the specific limitations (flat structure, bash-4+ requirement, readability ceiling) rather than a vague "use a better tool" answer.

## 10. Key Takeaways

- `name() { ... }` is the portable function-definition syntax (works under any POSIX shell); `function name { ... }` is bash-specific — prefer the former by default.
- Functions get their own `$1`/`$2`/`$@`/`$#` scope from the arguments passed at call time, entirely separate from the script's own positional parameters, which are untouched once the function returns.
- Bash variables are global by default even inside functions — `local` must be declared explicitly to scope a variable, and omitting it is a common, insidious source of one function silently clobbering another's variable.
- `return N` sets only a numeric exit code (0–255) and is not a data-return mechanism; the idiom for returning actual data is `echo`ing a value and capturing it with `$(...)` in the caller.
- Indexed arrays (`arr=(a b c)`) support `${arr[@]}` (all elements), `${#arr[@]}` (count), and `+=` for appending; associative arrays (`declare -A`, bash 4+) add named-key lookups via `${arr[key]}` and `${!arr[@]}` for enumerating keys.
- `"${arr[@]}"` quoted preserves each array element as a separate word; unquoted or `${arr[*]}` flattens and word-splits — the identical hazard [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) covered for `"$@"` vs `$*`, one level up.
- Parameter expansion (`${var#pattern}`, `${var%pattern}`, `${var/pat/repl}`, `${#var}`, `${var:offset:length}`) handles simple string manipulation without spawning an external process, but anything beyond simple single-value cases is more maintainable as `sed`/`awk` ([§48](./Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md), next).

## 11. Related Concepts & What's Next

This section builds directly on [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)'s positional-parameter and quoting groundwork — function arguments reuse the exact same `$1`/`$@`/`$#`/quoting mechanics, just in a new, per-call scope — and assumes [§46](./Section-46-Part6-Control-Structures-If-Case-For-While-Until.md)'s control-structure syntax (`if`, `case`, `for`) as the vocabulary functions are typically built from. [§48](./Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md) (next) covers `grep`, `sed`, and `awk` in full, which is the natural escalation path the moment string manipulation in this section's parameter-expansion operators starts feeling strained.

**Next Section:** [§48](./Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md) — `Section-48-Part6-Text-Processing-Tools.md`

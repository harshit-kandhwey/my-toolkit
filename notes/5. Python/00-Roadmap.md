# 00 — Roadmap: Python (Complete Topic Roadmap)

## 0. Assumption Line

Python is treated in its **DevOps / Cloud / SRE / Infrastructure Automation** interpretation: Python as the general-purpose scripting and automation language used to build CLIs, infrastructure tooling, API clients, and operational glue code — covering language fundamentals, the standard library, environment and dependency management (venv, pip, Poetry), core data structures, functions and modules, object-oriented programming, error handling and logging, file I/O, working with APIs and subprocesses, testing with pytest, packaging and distribution, concurrency/async basics, and infrastructure-facing libraries (boto3, PyYAML, Click/argparse, requests). This roadmap runs **130 sections across 16 parts**, sized to the same standard of depth as this repo's other tracks (comparable to Linux's 125 and Ansible's 119 sections).

This roadmap explicitly **excludes data science, numerical computing, and machine learning** — no pandas, numpy, scikit-learn, Jupyter notebooks, or statistical/ML libraries appear here. Where infrastructure-relevant overlap exists (e.g., reading a CSV of server inventory), it is handled with the standard library (`csv`, `json`) rather than data-science tooling. A brief scoping note on this divergence appears in Part 1.

Because Python spans language fundamentals, tooling, testing, packaging, and a wide ecosystem of infra-facing libraries, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and History

1.1 What Python Is; Design Philosophy (Zen of Python, "batteries included")
1.2 History: Python 2 vs. Python 3, the 2020 Sunset, and Why It Still Matters for Legacy Scripts
1.3 CPython vs. Alternative Implementations (PyPy, Jython, IronPython) — Brief Orientation
1.4 Python's Role in DevOps/Cloud/SRE Tooling (Ansible, AWS CLI, SaltStack, Certbot Are Python)
1.5 Scope Note: Why This Roadmap Excludes Data Science/ML (pandas, numpy, Jupyter)
1.6 Installing Python: python.org, pyenv, OS Package Managers, Version Management
1.7 Running Python: REPL, Scripts, `python -c`, Shebangs on Linux
1.8 Prerequisites Recap (Command-Line Comfort, Text Editors, Linux Fundamentals)

### Part 2 — Environment and Tooling

2.1 Virtual Environments: `venv` Deep Dive and Why Isolation Matters
2.2 `pip` Fundamentals: Installing, Upgrading, Uninstalling, `requirements.txt`
2.3 Dependency Pinning Strategies (`==`, `>=`, `~=`), `pip freeze`, and Dependency Hygiene (pip-tools, Dependabot/Renovate)
2.4 Poetry: Project Initialization, `pyproject.toml`, Lockfiles
2.5 pipx for Isolated CLI Tool Installation
2.6 pyenv for Multi-Version Python Management
2.7 IDE and Editor Tooling (VS Code, PyCharm Basics, Linters in the Editor)
2.8 Linters, Formatters, and Type Checkers: `black`, `ruff`, `flake8`, `isort`, `mypy`

### Part 3 — Core Language Syntax

3.1 Variables, Naming Conventions (PEP 8), and Dynamic Typing
3.2 Numbers: int, float, Complex, and Arithmetic Operators
3.3 Strings: Literals, Indexing, Slicing, f-strings, Common Methods
3.4 Booleans, Truthiness, Comparison Operators, and the `None` Type
3.5 Control Flow: if/elif/else, Ternary Expressions
3.6 Loops: for, while, `range()`, `enumerate()`, `zip()`, break/continue/else
3.7 Input/Output Basics: `print()`, `input()`, Formatting Output
3.8 Comments, Docstrings, and PEP 8 Style Conventions

### Part 4 — Data Structures

4.1 Lists: Creation, Indexing, Slicing, Mutating Methods
4.2 Tuples: Immutability and Use Cases
4.3 Dictionaries: Creation, Access Patterns, Iteration, `dict` Methods
4.4 Sets: Operations, Deduplication, Membership Testing
4.5 Comprehensions: List, Dict, Set, and Generator Comprehensions
4.6 Nested Data Structures and Working With JSON-Shaped Data
4.7 `collections` Module: `defaultdict`, `Counter`, `namedtuple`, `deque`, `OrderedDict`
4.8 Choosing the Right Data Structure for Infra Scripting Tasks

### Part 5 — Functions and Modules

5.1 Defining Functions: Parameters, Return Values, Default Arguments
5.2 `*args` and `**kwargs`: Variadic Functions
5.3 Scope: Local, Enclosing, Global, Built-in (LEGB Rule)
5.4 Lambda Functions and Higher-Order Functions: `map()`, `filter()`, `functools.reduce()`
5.5 Decorators: Writing and Applying Them
5.6 Generators and the `yield` Keyword
5.7 Modules and Packages: `import`, `__init__.py`, Namespace Packages, and the `if __name__ == "__main__":` Idiom
5.8 Organizing a Multi-File Python Project (Layout Conventions)

### Part 6 — Object-Oriented Programming in Python

6.1 Classes and Instances: `__init__`, Attributes, Methods
6.2 Class Variables vs. Instance Variables
6.3 Inheritance and Method Resolution Order (MRO)
6.4 Encapsulation Conventions: `_protected`, `__private`, Properties (`@property`)
6.5 Dunder Methods: `__str__`, `__repr__`, `__eq__`, `__len__`, and Others
6.6 Composition Over Inheritance in Infrastructure Tooling; When to Reach for OOP vs. Plain Functions
6.7 `dataclasses`: Reducing Boilerplate for Data-Holding Classes
6.8 Abstract Base Classes and `typing.Protocol` for Interfaces

### Part 7 — Error Handling and Logging

7.1 Exceptions: try/except/else/finally
7.2 Built-in Exception Hierarchy and Catching Specific Exceptions
7.3 Raising Exceptions and Custom Exception Classes
7.4 Context Managers and the `with` Statement (`contextlib`)
7.5 The `logging` Module: Loggers, Handlers, Formatters, Levels
7.6 Structured Logging Patterns for Production Automation Scripts
7.7 Logging Configuration: `dictConfig`, Rotating File Handlers, Log Shipping Considerations
7.8 Defensive Scripting: Input Validation, Fail-Fast vs. Retry Patterns

### Part 8 — File I/O and the Standard Library

8.1 Reading and Writing Files: `open()`, Modes, Context Managers
8.2 Working With Paths and the Filesystem: `os.path` vs. `pathlib`, `tempfile`, `shutil`, `glob`
8.3 `json` Module: Serialization and Deserialization
8.4 `csv` Module: Reading/Writing Tabular Infra Data
8.5 Config File Formats: `PyYAML` (YAML, Ansible/K8s Manifests) and `configparser` (`.ini`)
8.6 `datetime`, `time`, and `zoneinfo`: Handling Timestamps in Automation
8.7 `os` and `sys` Modules: Environment Variables, Exit Codes, Arguments
8.8 `re` Module: Regular Expressions for Log Parsing and Text Processing

### Part 9 — Working With APIs, Subprocess, and Shell Integration

9.1 The `requests` Library: GET/POST, Headers, Auth, Sessions; Brief Comparison to `httpx` for Async Use Cases
9.2 Handling JSON APIs, Pagination, and Rate Limits
9.3 Error Handling for HTTP Calls: Timeouts, Retries, `requests.exceptions`
9.4 Authentication Patterns: API Keys, Bearer Tokens, OAuth2 Basics
9.5 The `subprocess` Module: `run()`, `Popen`, Capturing Output, Exit Codes
9.6 Shelling Out Safely: Avoiding Shell Injection, `shell=True` Pitfalls
9.7 Environment Variables and `.env` Files (`python-dotenv`)
9.8 Interacting With REST APIs of Infra Tools (Kubernetes API, Vault, Consul via `requests`)

### Part 10 — Testing (pytest)

10.1 Why Test Automation Scripts; Testing Philosophy for Infra Code
10.2 `pytest` Fundamentals: Test Discovery, Assertions, Running Tests
10.3 Fixtures: Setup/Teardown, Fixture Scopes
10.4 Parametrized Tests: `@pytest.mark.parametrize`
10.5 Mocking and Patching: `unittest.mock`, `monkeypatch`
10.6 Testing Code That Calls External APIs or Subprocesses
10.7 Test Coverage: `coverage.py` and `pytest-cov`
10.8 Test Organization: `conftest.py`, Markers, Test Layout Conventions, and Integrating pytest Into CI Pipelines

### Part 11 — Packaging and Distribution

11.1 Python Packaging Landscape: `setuptools`, `pyproject.toml`, PEP 517/518
11.2 Building a Distributable Package Structure (`src/` Layout)
11.3 `pyproject.toml` Deep Dive: Metadata, Dependencies, Build Backends
11.4 Building Wheels and Source Distributions
11.5 Publishing to PyPI and Private Package Indexes
11.6 Versioning Strategies (SemVer) and Changelog Practices
11.7 Distributing CLI Tools: Entry Points and Console Scripts
11.8 Packaging Scripts as Standalone Executables (`pyinstaller`, `shiv`, `zipapp`)

### Part 12 — Concurrency and Async Basics

12.1 The Global Interpreter Lock (GIL): What It Means for Infra Scripts
12.2 `threading` Module: Threads for I/O-Bound Work
12.3 `multiprocessing` Module: Processes for CPU-Bound Work
12.4 `concurrent.futures`: `ThreadPoolExecutor` and `ProcessPoolExecutor`
12.5 `asyncio` Fundamentals: Event Loop, Coroutines, `async`/`await`
12.6 Practical Async Patterns: Concurrent API Calls, `asyncio.gather`
12.7 Choosing Threading vs. Multiprocessing vs. Asyncio for a Given Task
12.8 Common Concurrency Pitfalls in Automation Scripts (Race Conditions, Deadlocks)

### Part 13 — Infrastructure Automation Libraries

13.1 `boto3` Fundamentals: Clients vs. Resources, Sessions, Credential Resolution; Brief Cross-Cloud Comparison to Google Cloud (`google-cloud-*`) and Azure (`azure-sdk-for-python`)
13.2 `boto3` Common Patterns: EC2, S3, IAM Automation Scripts
13.3 `boto3` Pagination, Waiters, and Error Handling (`botocore.exceptions`)
13.4 `PyYAML` and `ruamel.yaml` for Kubernetes/CI Manifest Manipulation
13.5 The `kubernetes` Python Client Library — Overview and Common Use
13.6 `Click` Framework: Building Structured CLI Tools
13.7 `argparse`: Standard-Library CLI Argument Parsing
13.8 `Click` vs. `argparse` vs. `Typer` — Choosing a CLI Framework; Jinja2 for Templating Config Files and Reports Outside of Ansible

### Part 14 — Production Script Patterns and CLI Tools

14.1 Anatomy of a Production-Grade CLI Tool (Structure, Entry Points, Exit Codes)
14.2 Configuration Management for Scripts: Layered Config (Defaults, File, Env, Flags)
14.3 Idempotency Patterns in Python Automation (Mirroring Infra-as-Code Principles)
14.4 Dry-Run Modes and `--check`-Style Flags
14.5 Progress Reporting and User Feedback (`tqdm`, Spinners, Verbose Flags)
14.6 Secrets Handling in Scripts: Avoiding Hardcoded Credentials, Vault/SSM Integration
14.7 Signal Handling and Graceful Shutdown (`SIGINT`, `SIGTERM`)
14.8 Packaging a Script as a Container: Minimal Python Docker Images
14.9 Cron Jobs, Scheduled Tasks, and Long-Running Daemons in Python

### Part 15 — Mastery, Best Practices, and Comparisons

15.1 PEP 8 and PEP 20 Revisited: Idiomatic "Pythonic" Code
15.2 Common Anti-Patterns in Infra Scripts (Bare `except:`, Global State, Mutable Defaults)
15.3 Performance Profiling: `cProfile`, `timeit`, Identifying Bottlenecks
15.4 Memory Considerations: Generators vs. Lists at Scale
15.5 Python vs. Bash vs. Go for Infrastructure Tooling — When to Choose Which
15.6 Security Considerations: Dependency Vulnerabilities, `pip audit`, Supply-Chain Basics
15.7 Code Review Checklist for Python Automation Scripts
15.8 Documentation Practices: Docstrings, Type Hints, Auto-Generated Docs (`mkdocs`, Sphinx Overview)

### Part 16 — Interview Prep and Wrap-Up

16.1 Core Language Interview Question Bank (Beginner to Intermediate)
16.2 Data Structures and Algorithms Question Bank (Infra-Relevant Scope)
16.3 OOP and Design-Pattern Interview Questions
16.4 Scenario-Based Questions: "Write a Script That..." (Log Parsing, API Polling, Cleanup Jobs)
16.5 System-Design-Adjacent Questions: Designing a CLI Tool or Automation Service
16.6 Progressive Hands-On Labs (Beginner → Production-Style Automation Projects)
16.7 Consolidated Key-Takeaways Checklist
16.8 Common Misconceptions and Anti-Patterns Recap
16.9 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                     | Needed For    | Introduced                                        |
| ------------------------------------------------ | ------------- | ------------------------------------------------- |
| Basic command-line comfort                       | Throughout    | Assumed baseline (see [[../2. Linux/00-Roadmap]]) |
| Text editor / IDE familiarity                    | Part 2 onward | Briefly recapped in 2.7                           |
| Basic understanding of files and directories     | Part 8        | Assumed baseline                                  |
| Basic HTTP/REST concepts (helpful, not required) | Part 9        | Introduced from first principles in 9.1           |

No external topic must be studied before starting; this roadmap builds every Python-specific prerequisite in place, though general command-line and filesystem fundamentals are assumed baseline knowledge.

---

## 3. Learning Phases

| Phase                                   | Parts Covered | Goal                                                              |
| --------------------------------------- | ------------- | ----------------------------------------------------------------- |
| Phase 1 — Foundations and Setup         | Part 1, 2     | Understand Python's role in DevOps and set up a working toolchain |
| Phase 2 — Core Language                 | Part 3, 4, 5  | Syntax, data structures, functions, and modules                   |
| Phase 3 — Structuring Larger Programs   | Part 6, 7     | OOP, error handling, and logging for maintainable scripts         |
| Phase 4 — Interacting With the World    | Part 8, 9     | Standard library, file I/O, APIs, and shell integration           |
| Phase 5 — Quality and Shipping          | Part 10, 11   | Testing with pytest and packaging/distribution                    |
| Phase 6 — Scaling and Infra Integration | Part 12, 13   | Concurrency/async and infra-facing libraries (boto3, Click, etc.) |
| Phase 7 — Production Readiness          | Part 14, 15   | Production script patterns and best-practice mastery              |
| Phase 8 — Career Readiness and Wrap-Up  | Part 16       | Interview prep, labs, and next steps                              |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `9.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, GIT, Ansible). Section numbers (`§`) are continuous across the entire 16-part roadmap (1–124), not reset per part.

| Part                                                          | Roadmap Range | Continuous § Range | Folder             |
| ------------------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations and History                              | 1.1–1.8       | §1–§8              | `Contents/Part1/`  |
| Part 2 — Environment and Tooling                              | 2.1–2.8       | §9–§16             | `Contents/Part2/`  |
| Part 3 — Core Language Syntax                                 | 3.1–3.8       | §17–§24            | `Contents/Part3/`  |
| Part 4 — Data Structures                                      | 4.1–4.8       | §25–§32            | `Contents/Part4/`  |
| Part 5 — Functions and Modules                                | 5.1–5.8       | §33–§40            | `Contents/Part5/`  |
| Part 6 — Object-Oriented Programming in Python                | 6.1–6.8       | §41–§48            | `Contents/Part6/`  |
| Part 7 — Error Handling and Logging                           | 7.1–7.8       | §49–§56            | `Contents/Part7/`  |
| Part 8 — File I/O and the Standard Library                    | 8.1–8.8       | §57–§64            | `Contents/Part8/`  |
| Part 9 — Working With APIs, Subprocess, and Shell Integration | 9.1–9.8       | §65–§72            | `Contents/Part9/`  |
| Part 10 — Testing (pytest)                                    | 10.1–10.8     | §73–§80            | `Contents/Part10/` |
| Part 11 — Packaging and Distribution                          | 11.1–11.8     | §81–§88            | `Contents/Part11/` |
| Part 12 — Concurrency and Async Basics                        | 12.1–12.8     | §89–§96            | `Contents/Part12/` |
| Part 13 — Infrastructure Automation Libraries                 | 13.1–13.8     | §97–§104           | `Contents/Part13/` |
| Part 14 — Production Script Patterns and CLI Tools            | 14.1–14.9     | §105–§113          | `Contents/Part14/` |
| Part 15 — Mastery, Best Practices, and Comparisons            | 15.1–15.8     | §114–§121          | `Contents/Part15/` |
| Part 16 — Interview Prep and Wrap-Up                          | 16.1–16.9     | §122–§130          | `Contents/Part16/` |

**Total: 130 sections across 16 parts.**

---

## 5. Cross-Topic Dependency Graph

```text
Foundations and History (P1)
        │
        ▼
Environment and Tooling (P2) ──────────────► venv, pip, Poetry, linters, mypy
        │
        ▼
Core Language Syntax (P3)
        │
        ▼
Data Structures (P4)
        │
        ▼
Functions and Modules (P5) ──► Decorators, generators, project layout
        │
        ▼
Object-Oriented Programming (P6)
        │
        ▼
Error Handling and Logging (P7)
        │
        ▼
File I/O and the Standard Library (P8) ──► pathlib, json, YAML, csv, re
        │
        ▼
Working With APIs, Subprocess, and Shell Integration (P9) ──► requests, subprocess
        │
        ▼
Testing: pytest (P10)
        │
        ▼
Packaging and Distribution (P11)
        │
        ▼
Concurrency and Async Basics (P12)
        │
        ▼
Infrastructure Automation Libraries (P13) ──► boto3, kubernetes client, Click/argparse
        │
        ▼
Production Script Patterns and CLI Tools (P14)
        │
        ▼
Mastery, Best Practices, and Comparisons (P15)
        │
        ▼
Interview Prep and Wrap-Up (P16) ──► Recommended next topics: Ansible, Terraform, CI/CD scripting, cloud SDKs
```

**Recommended technologies to learn alongside or after Python:** Ansible (Python-based automation atop the language fundamentals here — see [[../8. Ansible/00-Roadmap]]), Terraform (declarative provisioning to complement imperative Python scripting — see [[../7. Terraform]]), CI/CD pipeline scripting (see [[../9. CI-CD]]), cloud provider SDKs (boto3 for AWS, `google-cloud-*` for GCP, `azure-sdk-for-python` — see [[../6. Cloud]]), Git (already covered — see [[../1. GIT]]).

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                                          | Section   | Status         |
| --- | ------------------------------------------------------------- | --------- | -------------- |
| 01  | Part 1 — Foundations and History                              | 1.1–1.8   | ⬜ Not Started |
| 02  | Part 2 — Environment and Tooling                              | 2.1–2.8   | ⬜ Not Started |
| 03  | Part 3 — Core Language Syntax                                 | 3.1–3.8   | ⬜ Not Started |
| 04  | Part 4 — Data Structures                                      | 4.1–4.8   | ⬜ Not Started |
| 05  | Part 5 — Functions and Modules                                | 5.1–5.8   | ⬜ Not Started |
| 06  | Part 6 — Object-Oriented Programming in Python                | 6.1–6.8   | ⬜ Not Started |
| 07  | Part 7 — Error Handling and Logging                           | 7.1–7.8   | ⬜ Not Started |
| 08  | Part 8 — File I/O and the Standard Library                    | 8.1–8.8   | ⬜ Not Started |
| 09  | Part 9 — Working With APIs, Subprocess, and Shell Integration | 9.1–9.8   | ⬜ Not Started |
| 10  | Part 10 — Testing (pytest)                                    | 10.1–10.8 | ⬜ Not Started |
| 11  | Part 11 — Packaging and Distribution                          | 11.1–11.8 | ⬜ Not Started |
| 12  | Part 12 — Concurrency and Async Basics                        | 12.1–12.8 | ⬜ Not Started |
| 13  | Part 13 — Infrastructure Automation Libraries                 | 13.1–13.8 | ⬜ Not Started |
| 14  | Part 14 — Production Script Patterns and CLI Tools            | 14.1–14.9 | ⬜ Not Started |
| 15  | Part 15 — Mastery, Best Practices, and Comparisons            | 15.1–15.8 | ⬜ Not Started |
| 16  | Part 16 — Interview Prep and Wrap-Up                          | 16.1–16.9 | ⬜ Not Started |

**Next Section:** Part 1 — Foundations and History (§1–§8)
</content>

# Coding language compatibility

The editor can open text files even when no execution adapter exists. Syntax highlighting does not imply execution support.

## Browser documents

HTML/HTM uses **Preview**, beside Save. It renders the current editor contents in an isolated iframe, so unsaved edits are visible. Inline CSS and JavaScript and bounded same-project linked stylesheets/classic scripts are supported; network requests and external resources are blocked. Preview is not a full web development server. Linked images, nested CSS imports and JavaScript module imports are not currently resolved. CSS is edited as a stylesheet, not executed as a program.

## Sandbox programs

Run executes the selected entry file in the validated Docker Linux image. No code runs directly on the Windows host. Network access is disabled; third-party dependencies must already be available locally.

| Language | Extensions | Runtime |
|---|---|---|
| Python | py | Python 3 |
| JavaScript | js, mjs, cjs | Node.js |
| TypeScript | ts | TypeScript compiler, then Node.js |
| Java | java | JDK 17; public class must match filename |
| C | c | GCC |
| C++ | cpp, cc, cxx | G++ |
| C# | cs | .NET 10/Roslyn; standalone source file with installed framework references, no NuGet downloads |
| Go | go | Go, offline |
| Rust | rs | rustc; standalone source file |
| PHP | php | PHP CLI |
| Ruby | rb | Ruby |
| Shell | sh, bash | Bash on Linux |
| SQL | sql | SQLite, not a remote database |
| R | r, R | Rscript |
| Lua | lua | Lua 5.4 |
| Perl | pl | Perl |

Kotlin, Swift, Dart, Scala, PowerShell, F#, JSX/TSX and other project/framework formats may be edited with highlighting, but do not have a standalone Run adapter here. A language's platform-specific libraries, package builds, GUI applications, framework servers and debugger are not implied by this table.

Live sandbox results are recorded in `benchmarks/workbench-language-matrix.json`. Run `scripts/prepare-workbench-sandbox.ps1` after installing the application dependencies. It activates the pinned image only after every language check and the sandbox isolation probes pass. The .NET adapter bounds heap/thread usage and compiles directly against installed framework references; it does not run package restore or MSBuild worker servers.

## Verified release checks (2026-09-29)

All 16 listed program languages passed both their check and run fixture in the final pinned Linux image `sha256:de4d03ebf7509fd3791515b958cfc5c34d2cc06c09b3fa4654e9e86c0e3dd11b`. The five isolation probes passed: normal output, blocked network, read-only root, read-only input and non-root user. The 512 MiB / one CPU execution policy was retained. These small fixtures establish adapter availability, not compatibility with every library or application framework.

The pre-fix matrix is retained in `benchmarks/workbench-language-matrix-pre-tmp-fix.json`: C# failed before temporary-directory handling was corrected. A later .NET/MSBuild attempt exhausted its bounded memory; the final direct Roslyn adapter passed without increasing the policy limits. Only the final matrix was activated.

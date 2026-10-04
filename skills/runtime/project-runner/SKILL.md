---
name: project-runner
description: Run existing programs and diagnose observed execution errors.
---

Resources: project file list/map, typed file_run, bounded terminal execution, Docker stdout/stderr and HTTP preview validation. Prefer file_run for an exact known source entrypoint. Paths are relative to the selected root; the project display name is not a child folder. Terminal cwd belongs in target. Separate commands do not share directory state. Dependency installation is not evidence an application ran. Use exact errors to select remaining authorized actions, never repeat actions unchanged. Execution occurs only through the provided Docker tools. Confirm the required output or HTTP validation, and state a precise blocker if validation fails.

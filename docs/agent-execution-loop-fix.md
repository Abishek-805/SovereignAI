Application execution continuation fix

A fixed operation list previously stopped at the first tool failure and treated a prerequisite terminal exit as task completion. ApplicationTools now sends bounded actual execution observations to the same existing tool planner for remaining actions after terminal operations or run failures. No new agent/model/controller was added. At most two continuations are allowed; repeated actions are rejected, cancellation and existing task budgets remain in effect, and every continuation passes current-request authorization again. Running alone cannot authorize code edits.

Selected workspace display names resolve to the existing root when they are not actual relative folders. Plain Python/Node source invocations use the typed Docker execution adapter, including Flask HTTP preview. Arguments and compound commands retain terminal semantics.

Evidence: outputs/agent-execution-loop/live-before-root-fix.json preserves a failed live request. live-job.json records the same request completing in 25.8 seconds with HTTP 200. real-error-continuation.json records Docker rejecting cd: todo_app, the real Qwen worker receiving the exact error, and one corrected continuation serving HTTP 200. Generated code ran only in Docker; project source files were not edited by this run.

Regression validation: 46 application-tool and web-preview tests passed. Tests cover setup-to-run continuation, error-to-run continuation, duplicate-action rejection, authorization during recovery, project-root resolution and preservation of shell arguments/compound commands. This validates the observed recovery, not guaranteed recovery from arbitrary code or dependency defects.

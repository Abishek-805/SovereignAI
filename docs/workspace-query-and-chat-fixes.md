# Workspace, assessment queries and chat fixes

Requests to create a programming project use the selected managed workspace. Creating a new managed workspace requires an explicit new/separate workspace request. Application plans cannot silently replace that selection, even when the planner emits a project creation operation.

Table queries separate the requested mathematical measure from source binding. Categorical percentage queries across assessments bind the requested cohort to actual identity values or prefixes, find recorded outcome fields across complementary sheets, and calculate each numerator and denominator over complete records. Numeric aggregations support several columns with separate sample counts. The answer shows verified percentages and identifies sheets without an explicit result rule; it does not infer a passing score from cell colours.

Chat distinguishes wheel, touch, keyboard and scrollbar input from scroll changes caused by layout. The composer reserves its entire wrapper height, and the last desktop answer no longer has a changing viewport-derived minimum height. Browser regression checks verified that the current answer stays visible above the composer and manual history scrolling remains respected.

Python programs needing a camera or desktop window cannot run inside the existing isolated Docker environment. Run reports that requirement and provides a command for `scripts/run-workspace-python.ps1`. The user launches that command on Windows; it creates a separate project environment outside the source tree, installs the project's requirements, and supplies the OpenCV desktop package for older projects missing that dependency. Generated programs are never automatically launched on the host. The launcher was tested with OpenCV import and the bundled face cascade; physical camera capture was not tested.

Validation includes the exact original OpenCV request in a temporary selected workspace, a live multi-assessment percentage query, the existing student comparison, a browser scroll regression, frontend build/type checks and backend tests. Private workbook records and live request results remain outside version control.
# Reopening conversations

The Chat composer is fixed to the viewport and measured against the chat content
column, including sidebar resizing. Route scroll restoration is disabled inside
Chat so it cannot overwrite the latest-message landing position. The latest user
and assistant rows mount immediately; page height changes keep the bottom pinned
until the user scrolls through history.

Run `node tests/chat_opening_browser.cjs` against the running workbench to check
streaming, manual history scrolling, repeated reopenings, and a full reload using
an isolated browser profile with mocked generation. No real conversations change.



## Model planning for assessment refinements

The table planner supplies an explicit active mathematical measure, actual
assessment fields, and contrasting examples to the model. The model decides
whether a request refines that measure or starts a new task, and identifies the
literal numeric rule separately from the requested outcome. The executor binds
that plan to source records and performs arithmetic; there is no parser for user
phrases such as "below ... fails". Model weights are unchanged.

A generic report request no longer narrows the library to a document whose
filename happens to contain "report". Outcome polarity prevents mixed PASS/FAIL
numerators; literal source identifiers prevent an omitted cohort from silently
expanding a calculation to the entire workbook. Numeric criteria and denominators
are shown in the answer so the calculation can be checked.

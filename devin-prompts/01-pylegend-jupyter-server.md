Repository: https://github.com/finos/pylegend (public). Open pull request #338, "Update dependency jupyter-server to v2.20.0 [SECURITY]", was opened by a dependency bot to fix security advisories and has been failing CI (PyTest on Python 3.9) since it was opened.

Your job:
1. Clone the repository and check out the bot PR's branch (git fetch origin pull/338/head).
2. Reproduce the failing check locally using the exact commands from the repo's CI workflow files. Show the failing output.
3. Find the root cause. State it in two sentences.
4. Make the smallest change that makes the upgrade pass: fix call sites, config or constraints. Keep the security upgrade itself. Regenerate lockfiles with the project's own package manager, never by hand.
5. Re-run the same CI commands and the full test suite. Show before and after results.
6. Do NOT open a pull request, do not push, and do not comment on the repository. Finish by printing: (a) root cause, (b) the complete output of git diff against the bot PR's branch, (c) the test commands and their pass/fail summary, (d) anything you could not verify.
If the failure needs secrets or services you do not have, stop and say so instead of guessing.

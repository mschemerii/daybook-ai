# Phase 10 Release Readiness

**Status:** implementation prepared; final readiness requires the recorded
Phase 10 validation run on the authoritative Mac checkout.

## Required evidence

- focused cleanup/model-runtime tests
- complete retained regression suite
- native desktop suite
- compileall and `git diff --check`
- fresh install/preflight/start
- migrations and backup behavior
- PDF and CSV ZIP inspection
- real local inference
- deterministic fallback
- repeated shutdown/restart
- database release
- independently started llama.cpp preserved
- reopening retains earlier completion in reports

## Publication gates

1. Implementation and validation review.
2. Explicit approval to commit and push.
3. Pull request creation and full diff/check review.
4. Separate merge approval.
5. Post-merge verification of `main` and `origin/main`.
6. Separate final v0.9 tag/release and branch-cleanup approval.

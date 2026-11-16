# WP1 execution summary after the local-review patch

The original PR reported 72,394 source rows, 72,235 primary rows, 71,607 exposure-
sensitivity rows, and 80 size-summary rows. The fixed implementation reproduced
those counts and all original count/exposure/rate values on the available snapshot.
The sixteen regression tests and ten existing WP1 test functions were exercised
during patch preparation. The complete locked-environment project test suite and
Ruff must run on the owner's checkout using the bundled local verification script.

The original source and runtime metadata describe Charles's historical run. For
the actual refreshed run, use `artifacts/research_v2/annual/source_run_manifest.json`:
it is now generated, not manually maintained. It records the real input hash,
source-year counts, code hashes, Git revision/dirty status, runtime versions,
parameters, output hashes and row counts, and successful reconciliation checks.
The available review snapshot and Charles's source have different file hashes;
no exact-input identity is assumed by the patch.

The documented CLI regenerates all seven release files. Existing files require
`--overwrite`; the local patch runner backs up original WP1 code/outputs first.
The independent verifier compares the refreshed counts and rates with both the
source facts and the backed-up pre-patch summary. Original modeling artifacts,
modeling code, locked dependencies, and the annual source are checksum-protected
by the runner throughout local verification.

The revised day audit uses total DART cases, includes a combined-day screen,
and no longer flags ordinary restricted-day/DAFW-case combinations by themselves.
There are 446 measure-level flags in the supplied snapshot. DAFW and DJTR totals
remain blank and `blocked_review`; raw-value review is still outstanding.

The 2025 exposure anomaly and the four candidate findings in `annual_findings.md`
remain unchanged. Neither automatic clipping nor a new forecasting/modeling run
is part of this patch. The generated manifest and local backup's verification
receipt are the authoritative records of the owner's successful execution.

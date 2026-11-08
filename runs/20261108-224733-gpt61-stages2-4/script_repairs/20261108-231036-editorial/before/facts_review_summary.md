# Targeted facts repair review

Status: checks complete; awaiting human approval of the repaired facts. Stage 4 has not run.

## Exact edits

- claim_001: attribution normalized to Searchbloom; text now reads: In its author's disclosure, Searchbloom says it publishes the list and ranks itself first.
- claim_010: attribution normalized to Searchbloom; unchanged text retains “In Searchbloom’s own tracking”.
- claim_016: The client's team must own sponsorship and affiliate budgets when the most-retrieved roundup in its category is a paid placement; it must also own retailer, marketplace, and partner listings, social media and community work, and brand positioning and the budget behind PR.

All other 17 claims are unchanged. Claim IDs, order, citations, and declared company names are unchanged. Original facts and their Sol provenance are preserved in the repair before/ snapshot. The edited artifact is labeled local-targeted-edit and changes.json links the original model result to each deterministic edit. No model generation or repair loops were used.

## Validation and semantic verification

- Structural errors: zero.
- Terra verdicts: 20 supported, zero partial, zero unsupported (previously 19 supported / one partial).
- Three changed candidates were freshly verified using gpt-6.1-terra; 17 exact unchanged verdicts were reused.
- Two attribution flags and the omitted-condition semantic flag are resolved.
- Three raw MISSING_NAME flags remain on claim_009, claim_011, claim_017. These have explicit, hash-bound false-positive dispositions in output/facts_review_dispositions.json, as instructed by the user. “Buyers” is a common noun here; all three semantic checks are supported.
- Flags have not been deleted or suppressed. Validation code and rules are unchanged. No facts approval receipt has been created. At the approval checkpoint the three exact flag IDs must be acknowledged with the documented false-positive reason.

## Cost and preservation

Additional repair verification estimate: $0.002343. Stage 3 including repair: $0.057919. Cumulative isolated run including selection: $0.162361. These use the recorded Standard short-context rates and usage, not invoice data. See cost_comparison.json.

All 388 original working output/cache files remain byte-identical, including approvals, TTS, and timings. Isolated selection and its approval, all existing isolated cache entries, and the usage log prefix are preserved. Original isolated facts/review and reports are backed up under fact_repairs/20261108-225631-targeted/before/.

## Approval gate

Review output/facts_review.md and output/facts_review_dispositions.json. The repaired facts remain unapproved. No script, TTS, or timing generation was performed.

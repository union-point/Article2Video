# Stage 3 facts checkpoint

Selection approval was recorded from the user’s explicit chat approval. Stage 3 completed with fresh generation and verification; stopped before any script generation.

## Review results

- Claims: 20; structural errors: 0; review flags: 6 across 6 claims.
- Semantic verdicts: 19 supported, 1 partial, 0 unsupported.
- 14 claims have no current flags. No facts have been approved or repaired.

## Findings requiring human review

- claim_016: substantive loss of a condition. The source assigns sponsorship/affiliate budgets to the client when the most-retrieved category roundup is a paid placement; the claim omits that condition. Terra returned partial.
- claim_001 and claim_010: attribution metadata includes explanatory text beyond the publisher name. The deterministic attribution check flags these strings; Terra supports both claims against their cited evidence.
- claim_009, claim_011, claim_017: the proper-name heuristic treats sentence-initial “Buyers” as a missing name. Terra supports these claims. These appear to be heuristic false positives, but no flags were waived and no validator rules were changed.

## Comparison with the existing working facts

| Metric | Old working facts | New draft |
| --- | ---: | ---: |
| Claims | 17 | 20 |
| Structural errors | 0 | 0 |
| Review flags | 0 | 6 |
| Supported verdicts | 17 | 19 |
| Partial verdicts | 0 | 1 |

The old facts are a curated/repaired approved set; the new facts are an unrepaired draft from a different section selection. These counts do not establish that one model is more accurate. Evidence support is assessed against the frozen article; the source’s real-world claims have not been independently verified. Script quality comparison remains pending Stage 4 and the facts approval gate.

## Usage and estimated cost

| Operation | Requests | Input tokens | Output tokens | Estimated USD |
| --- | ---: | ---: | ---: | ---: |
| selection | 1 | 37,397 | 1,095 | $0.104441 |
| facts | 1 | 9,562 | 1,632 | $0.040224 |
| verify | 20 | 10,758 | 919 | $0.015353 |

Stage 3 estimate: $0.055577; cumulative isolated-run estimate including selection: $0.160018. Generation used gpt-6.1-sol; all 20 verifier records used gpt-6.1-terra. No old response cache was reused. Output usage includes reasoning tokens; cache-write and cached-input rates are accounted for separately in cost_comparison.json. Estimates assume Standard short-context processing and 30-minute cache writes, with no regional/account adjustments; they are not invoice amounts.

Pricing sources checked 2026-11-08: [Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra).

## Preservation and next gate

All 388 existing working output/cache files remain byte-identical. Existing approvals, TTS, and timing outputs are unchanged. New run contains a selection approval only. Facts approval, script generation, repairs, TTS, and timings were not performed.

Review output/facts_review.md for every claim, exact cited text, verdict, and flag ID. Human review must approve an explicit claim subset or acknowledge applicable flags before script generation.

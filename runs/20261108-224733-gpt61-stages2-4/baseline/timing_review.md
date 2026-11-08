# Stage 6 timing review

Status: **review_required**
Audio: 155.150s; 30 fps; 4661 frames including tail padding.
Sentences: 18; overall normalized similarity: 0.9878.

Audio is the master clock. Word cues are approximate (typically 100–300 ms uncertainty).
Fallback spans are estimates, not exact scene durations. Human listening review remains pending.

| Scene | Start | End | Frames | Method | Minimum sentence score |
| --- | ---: | ---: | ---: | --- | ---: |
| scene_001 | 0.000 | 17.800 | 534 | even_fallback | 0.9681 |
| scene_002 | 17.800 | 29.380 | 348 | even_fallback | 1.0000 |
| scene_003 | 29.380 | 53.140 | 713 | even_fallback | 0.9613 |
| scene_004 | 53.140 | 80.000 | 805 | even_fallback | 0.9474 |
| scene_005 | 80.000 | 99.360 | 581 | even_fallback | 0.9787 |
| scene_006 | 99.360 | 119.340 | 600 | even_fallback | 0.9732 |
| scene_007 | 119.340 | 155.150 | 1080 | even_fallback | 0.9763 |

## Issues

- EMPTY_TRANSCRIPT_WORDS — transcript: 2 empty word entries omitted; full API response retained in the diagnostic receipt
- NAME_MISMATCH — scene_001.n1.s1: Company names not recognized exactly after normalization: ['Tinuiti', 'iPullRank']
- ZERO_DURATION_WORD — scene_002.n1.s1: Whisper returned a word without a positive time span; use scene fallback
- ZERO_DURATION_WORD — scene_003.n1.s1: Whisper returned a word without a positive time span; use scene fallback
- QUANTITY_MISMATCH — scene_003.n1.s1: Missing quantities: ['number:68631', 'percent:8.9']; extra: ['number:631', 'number:68', 'number:8', 'number:9']
- ZERO_DURATION_WORD — scene_003.n2.s1: Whisper returned a word without a positive time span; use scene fallback
- ZERO_DURATION_WORD — scene_003.n3.s1: Whisper returned a word without a positive time span; use scene fallback
- ZERO_DURATION_WORD — scene_004.n2.s1: Whisper returned a word without a positive time span; use scene fallback
- QUANTITY_MISMATCH — scene_004.n2.s1: Missing quantities: ['percent:122']; extra: ['number:122']
- ZERO_DURATION_WORD — scene_004.n4.s1: Whisper returned a word without a positive time span; use scene fallback
- ZERO_DURATION_WORD — scene_005.n1.s1: Whisper returned a word without a positive time span; use scene fallback
- QUANTITY_MISMATCH — scene_005.n1.s1: Missing quantities: ['gbp:1500']; extra: ['gbp:1', 'number:500']
- ZERO_DURATION_WORD — scene_005.n2.s1: Whisper returned a word without a positive time span; use scene fallback
- NAME_MISMATCH — scene_005.n2.s1: Company names not recognized exactly after normalization: ['Tinuiti']
- QUANTITY_MISMATCH — scene_006.n1.s1: Missing quantities: ['unparsed:12-month']; extra: []
- ZERO_DURATION_WORD — scene_006.n2.s1: Whisper returned a word without a positive time span; use scene fallback
- NAME_MISMATCH — scene_006.n2.s1: Company names not recognized exactly after normalization: ['iPullRank']
- ZERO_DURATION_WORD — scene_007.n1.s1: Whisper returned a word without a positive time span; use scene fallback
- QUANTITY_MISMATCH — scene_007.n1.s1: Missing quantities: ['gbp:1500', 'usd:3000', 'usd:8000']; extra: ['gbp:1', 'number:0', 'number:500', 'number:8']
- ZERO_DURATION_WORD — scene_007.n2.s1: Whisper returned a word without a positive time span; use scene fallback
- OVERLAPPING_WORDS — scene_007.n2.s1: Whisper word intervals overlap; use scene fallback
- SCENE_FALLBACK — scene_001: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review
- SCENE_FALLBACK — scene_002: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review
- SCENE_FALLBACK — scene_003: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review
- SCENE_FALLBACK — scene_004: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review
- SCENE_FALLBACK — scene_005: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review
- SCENE_FALLBACK — scene_006: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review
- SCENE_FALLBACK — scene_007: Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review

## Sentence matches

- scene_001.n1.s1 (0.000–8.900s, score 0.9681, even_fallback)
  - Approved: Searchbloom lists Searchbloom, The SEO Works, Tinuiti, Graphite, and iPullRank as the best AI SEO companies in 2026.
  - Transcript: SearchBloom lists SearchBloom the SEOWorks Tenuity Graphite and iPollRank as the best AI SEO companies in 2026
- scene_001.n2.s1 (8.900–17.800s, score 1.0000, even_fallback)
  - Approved: AI SEO mostly involves traditional SEO work, but now adds measuring AI visibility and citations from external pages.
  - Transcript: AI SEO mostly involves traditional SEO work but now adds measuring AI visibility and citations from external pages
- scene_002.n1.s1 (17.800–29.380s, score 1.0000, even_fallback)
  - Approved: Searchbloom lists AI visibility, brand presence on external pages, technical and structured-data foundations, content and entity authority, and documented results as scoring criteria.
  - Transcript: SearchBloom lists AI visibility brand presence on external pages technical and structured data foundations content and entity authority and documented results as scoring criteria
- scene_003.n1.s1 (29.380–37.300s, score 0.9613, even_fallback)
  - Approved: Searchbloom reports measuring 68,631 AI answers in its category, with its own website cited 8.9% of the time.
  - Transcript: SearchBloom reports measuring 68 631 AI answers in its category with its own website cited 8 9 of the time
- scene_003.n2.s1 (37.300–45.220s, score 1.0000, even_fallback)
  - Approved: Searchbloom says the best AI SEO company manages SEO work, measures AI visibility daily, and identifies outside pages worth earning.
  - Transcript: SearchBloom says the best AI SEO company manages SEO work measures AI visibility daily and identifies outside pages worth earning
- scene_003.n3.s1 (45.220–53.140s, score 0.9677, even_fallback)
  - Approved: PR, social, sponsorships, and partner listings remain with the client's own team.
  - Transcript: PR social sponsorships and partner listings remain with the client's own
- scene_004.n1.s1 (53.140–59.855s, score 1.0000, even_fallback)
  - Approved: Searchbloom ranks itself as the best overall AI SEO company in 2026 based on published methods and results.
  - Transcript: SearchBloom ranks itself as the best overall AI SEO company in 2026 based on published methods and results
- scene_004.n2.s1 (59.855–66.570s, score 0.9474, even_fallback)
  - Approved: Searchbloom reports a custom closet company's search leads rose 122% in a year.
  - Transcript: SearchBloom reports a custom closet company's search leads rose 122 in a year
- scene_004.n3.s1 (66.570–73.285s, score 1.0000, even_fallback)
  - Approved: That company's CRM recorded 20 of its 51 September 2026 leads as coming from AI search.
  - Transcript: That company's CRM recorded 20 of its 51 September 2026 leads as coming from AI search
- scene_004.n4.s1 (73.285–80.000s, score 1.0000, even_fallback)
  - Approved: In Searchbloom's ranking, the company scored 48 out of 50 for AI search tied to leads and revenue.
  - Transcript: In SearchBloom's ranking the company scored 48 out of 50 for AI search tied to leads and revenue
- scene_005.n1.s1 (80.000–89.680s, score 1.0000, even_fallback)
  - Approved: In Searchbloom's ranking, The SEO Works placed second with 44 out of 50 for specialist SEO and AI SEO partnerships, starting at GBP 1,500 a month.
  - Transcript: In SearchBloom's ranking the SEO works placed second with 44 out of 50 for specialist SEO and AI SEO partnerships starting at GBP 1 500 a month
- scene_005.n2.s1 (89.680–99.360s, score 0.9787, even_fallback)
  - Approved: Searchbloom ranks Tinuiti third with 44 out of 50 for AI search within full-funnel media engagements; fees are not published.
  - Transcript: SearchBloom ranks tenuity third with 44 out of 50 for AI search within full funnel media engagements Fees are not published
- scene_006.n1.s1 (99.360–109.350s, score 0.9732, even_fallback)
  - Approved: Searchbloom ranks Graphite fourth with 42 out of 50 for AEO and SEO grounded in original research, with unpublished fees and a 12-month minimum SEO term.
  - Transcript: SearchBloom ranks graphite fourth with 42 out of 50 for SEO grounded in original research with unpublished fees and a 12 month minimum SEO term
- scene_006.n2.s1 (109.350–119.340s, score 0.9914, even_fallback)
  - Approved: Searchbloom ranks iPullRank fifth with 41 out of 50 for relevance engineering and technical AI search work; fees, minimums, and terms are not published.
  - Transcript: SearchBloom ranks iPoll rank fifth with 41 out of 50 for relevance engineering and technical AI search work Fees minimums and terms are not published
- scene_007.n1.s1 (119.340–128.292s, score 0.9763, even_fallback)
  - Approved: Only three companies publish a price: Searchbloom starts SEO at $3,000 a month with no lengthy contracts, The SEO Works starts at GBP 1,500 a month, and Siege Media’s minimum is $8,000 a month.
  - Transcript: Only three companies publish a price SearchBloom starts SEO at 3 000 a month with no lengthy contracts The SEO work starts at GBP 1 500 a month and Siege Media's minimum is 8 000 a month
- scene_007.n2.s1 (128.292–137.245s, score 1.0000, even_fallback)
  - Approved: Searchbloom says AI SEO priced at a few hundred dollars a month likely produces automated content flagged by Google's spam policies.
  - Transcript: SearchBloom says AI SEO priced at a few hundred dollars a month likely produces automated content flagged by Google's spam policies
- scene_007.n3.s1 (137.245–146.197s, score 1.0000, even_fallback)
  - Approved: The SEO Works and Siege Media publish all key transparency items, while Searchbloom publishes all but minimums beyond starting fees.
  - Transcript: The SEO works and Siege Media publish all key transparency items while SearchBloom publishes all but minimums beyond starting fees
- scene_007.n4.s1 (146.197–155.150s, score 1.0000, even_fallback)
  - Approved: Eight of the nine companies publish dated AI search results, and all nine say how they track AI visibility.
  - Transcript: Eight of the nine companies publish dated AI search results and all nine say how they track AI visibility

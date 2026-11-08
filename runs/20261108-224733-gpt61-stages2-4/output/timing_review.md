# Stage 6 timing review

Status: **review_required**
Audio: 135.600s; 30 fps; 4074 frames including tail padding.
Sentences: 20; overall normalized similarity: 0.9989.
Zero-duration words: 31; affected sentences: 16.

Audio is the master clock. Word cues are approximate (typically 100–300 ms uncertainty).
Aligned spans may retain timestamp review findings; text similarity does not establish acoustic accuracy.
Fallback spans are estimates, not exact scene durations. Human listening review remains pending.

| Scene | Start | End | Frames | Method | Minimum sentence score |
| --- | ---: | ---: | ---: | --- | ---: |
| scene_001 | 0.000 | 18.080 | 543 | aligned | 0.9833 |
| scene_002 | 18.080 | 41.080 | 690 | aligned | 1.0000 |
| scene_003 | 41.080 | 64.880 | 714 | aligned | 1.0000 |
| scene_004 | 64.880 | 85.960 | 632 | aligned | 1.0000 |
| scene_005 | 85.960 | 106.880 | 628 | aligned | 1.0000 |
| scene_006 | 106.880 | 123.940 | 512 | aligned | 1.0000 |
| scene_007 | 123.940 | 135.600 | 355 | aligned | 1.0000 |

## Issues

- ZERO_DURATION_WORD — scene_002.n1.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_002.n2.s1: 4 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_002.n3.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_003.n1.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_003.n2.s1: 3 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_003.n3.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_003.n4.s1: 2 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_004.n1.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_004.n2.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_004.n3.s1: 4 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_005.n1.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_005.n2.s1: 3 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_005.n3.s1: 2 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_006.n2.s1: 1 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_006.n3.s1: 2 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps
- ZERO_DURATION_WORD — scene_007.n1.s1: 3 words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps

## Sentence matches

- scene_001.n1.s1 (0.000–8.760s, score 1.0000, aligned)
  - Approved: Searchbloom publishes this agency list and ranks itself first, so its ranking reflects the publisher's own assessment, not an independent verdict.
  - Transcript: Search Bloom publishes this agency list and ranks itself first so its ranking reflects the publisher's own assessment not an independent verdict
- scene_001.n2.s1 (9.500–17.680s, score 0.9833, aligned)
  - Approved: Throughout this guide, the source is Searchbloom: its facts come from company websites, and its case-study figures are the companies' own reporting.
  - Transcript: Throughout this guide the source is Search Bloom Its facts come from company websites and its case study figures are the company's own reporting
- scene_002.n1.s1 (18.080–26.340s, score 1.0000, aligned)
  - Approved: Start by defining success: leads, sign-ups, or revenue from AI referrals, rather than citation counts or visibility scores.
  - Transcript: Start by defining success leads signups or revenue from AI referrals rather than citation counts or visibility scores
- scene_002.n2.s1 (27.060–33.220s, score 1.0000, aligned)
  - Approved: Then ask for a dated AI search result with a named or described company, a figure, and a period.
  - Transcript: Then ask for a dated AI search result with a named or described company a figure and a period
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_002.n3.s1 (34.200–40.200s, score 1.0000, aligned)
  - Approved: Watch for promises of AI citations in weeks, or reports that count citations without mentioning leads or revenue.
  - Transcript: Watch for promises of AI citations in weeks or reports that count citations without mentioning leads or revenue
- scene_003.n1.s1 (41.080–45.460s, score 1.0000, aligned)
  - Approved: AI answers are probabilistic: repeating the same question can produce different brands.
  - Transcript: AI answers are probabilistic Repeating the same question can produce different brands
- scene_003.n2.s1 (46.420–52.500s, score 1.0000, aligned)
  - Approved: Track a fixed set of real buyer questions daily across the AI platforms your buyers use, then read the trend.
  - Transcript: Track a fixed set of real buyer questions daily across the AI platforms your buyers use then read the trend
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_003.n3.s1 (53.260–58.560s, score 1.0000, aligned)
  - Approved: Separate branded and non-branded prompts, and segment them by awareness, consideration, and purchase.
  - Transcript: Separate branded and non branded prompts and segment them by awareness consideration and purchase
- scene_003.n4.s1 (59.230–64.200s, score 1.0000, aligned)
  - Approved: Ask which tracking tool, prompts, platforms, and run frequency an agency uses.
  - Transcript: Ask which tracking tool prompts platforms and run frequency an agency uses
- scene_004.n1.s1 (64.880–69.820s, score 1.0000, aligned)
  - Approved: In Searchbloom's own tracking, about nine of every ten sources AI cites are on other people's sites.
  - Transcript: In Search Bloom's own tracking about nine of every 10 sources AI cites are on other people's sites
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_004.n2.s1 (70.720–77.220s, score 1.0000, aligned)
  - Approved: Ask which outside URLs are retrieved and cited for your top buyer questions, and which placements the agency can help you secure.
  - Transcript: Ask which outside URLs are retrieved and cited for your top buyer questions and which placements the agency can help you secure
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_004.n3.s1 (77.960–85.280s, score 1.0000, aligned)
  - Approved: When an answer leaves your business out, inspect the pages it cited; often, the fix is a listing through outreach, a review, or sponsorship.
  - Transcript: When an answer leaves your business out inspect the pages it cited Often the fix is a listing through outreach a review or sponsorship
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_005.n1.s1 (85.960–91.600s, score 1.0000, aligned)
  - Approved: Crawler access, correct structured data, and clean architecture make a site legible to AI platforms.
  - Transcript: Crawler access correct structured data and clean architecture make a site legible to AI platforms
- scene_005.n2.s1 (92.300–97.840s, score 1.0000, aligned)
  - Approved: The agency should handle technical, content, and entity work, and review visibility tracking with you monthly.
  - Transcript: The agency should handle technical content and entity work and review visibility tracking with you monthly
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_005.n3.s1 (98.820–106.300s, score 1.0000, aligned)
  - Approved: Clarify whether the agency implements technical changes or supplies technical recommendations, and price the developer time you will need to provide.
  - Transcript: Clarify whether the agency implements technical changes or supplies technical recommendations and price the developer time you will need to provide
  - Timestamp review: first or last word has zero duration; sentence boundary remains uncertain.
- scene_006.n1.s1 (106.880–112.740s, score 1.0000, aligned)
  - Approved: Your team must own sponsorship and affiliate budgets when the most-retrieved roundup in your category is a paid placement.
  - Transcript: Your team must own sponsorship and affiliate budgets when the most retrieved roundup in your category is a paid placement
- scene_006.n2.s1 (113.280–116.960s, score 1.0000, aligned)
  - Approved: Your team must also own retailer, marketplace, and partner listings.
  - Transcript: Your team must also own retailer marketplace and partner listings
- scene_006.n3.s1 (117.620–123.280s, score 1.0000, aligned)
  - Approved: That responsibility extends to social media and community work, brand positioning, and the budget behind PR.
  - Transcript: That responsibility extends to social media and community work brand positioning and the budget behind PR
- scene_007.n1.s1 (123.940–129.480s, score 1.0000, aligned)
  - Approved: In Searchbloom's comparison of nine companies, three publish a fee, two a minimum, and four a contract term.
  - Transcript: In Search Bloom's comparison of nine companies three publish a fee two a minimum and four a contract term
- scene_007.n2.s1 (130.160–135.300s, score 1.0000, aligned)
  - Approved: Before comparing agencies, get any unpublished fees, minimums, and contract lengths in writing.
  - Transcript: Before comparing agencies get any unpublished fees minimums and contract lengths in writing

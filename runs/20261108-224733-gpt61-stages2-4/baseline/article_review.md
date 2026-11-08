# Searchbloom snapshot review

Snapshot SHA-256: `e4c271f49b9e0cb84c108bb9b043b98a8c73cfc772676ac1426c1b4e6340381c`

Parsed offline from the user-provided saved HTML; the earlier live HTTP request returned 403. No live-fetch success is claimed.

## Verified template and extraction

- Title: `article.article-holder h1.entry-title`.
- Main body: `article.article-holder .entry-content.card-text`.
- Nine repeated profiles: numbered `h3` elements under `h2#profiles`, each followed by `p.sb-answer` and labeled facts, scores, fit, overview, results, terms, and alternatives.
- Profile text is grouped into ranked fields with original-DOM locators; quotes retain their attribution and result lists retain their links.
- The original profile headings remain heading blocks. Rank comes from the displayed heading, never from position.
- Three real tables, ten rows each including headers, with 5, 4, and 7 columns. No rowspan or colspan in the snapshot.
- Three lazy-loaded editorial diagrams; noscript duplicates are omitted. The Searchbloom diagram records its parent ranked entry and its position after field 5.
- Removed the preferred-source and AI-summary widgets, the TOC label and its adjacent list, and non-visible scripts/styles. Related guides, navigation, footer, and share controls are outside the selected body.
- Preserved the publisher self-ranking disclosure, methodology, all company profiles, questions and answers, author note, and refresh log.
- 51 headings, 146 blocks, 381 sentences; all IDs are unique and offsets reconstruct their original normalized text.
- Full normalized extracted text equals the cleaned title/body text, in order: 6,688 / 6,688 words (100%). The rejection threshold remains 90%.
- Validation is valid; no fallback or warnings. Original DOM paths were captured before removing widgets and checked against the untouched fixture.

## Sentence-boundary review

The shortest units are source fragments (Yes., New York., Clutch 4.9., and score totals), not truncated content. The longest is the original semicolon-separated refresh-log sentence. Quotes retain attribution. No wording or punctuation was rewritten.

## Ten shortest sentences

- `block_0137.s1` (4 characters): Yes.
- `block_0033.f2.s2` (9 characters): New York.
- `block_0045.f2.s2` (9 characters): New York.
- `block_0028.f2.s3` (11 characters): Clutch 4.9.
- `block_0146.s1` (12 characters): Refresh log.
- `block_0028.f3.s2` (13 characters): Total: 48/50.
- `block_0031.f3.s2` (13 characters): Total: 44/50.
- `block_0033.f3.s2` (13 characters): Total: 44/50.
- `block_0035.f3.s2` (13 characters): Total: 42/50.
- `block_0037.f3.s2` (13 characters): Total: 41/50.

## Ten longest sentences

- `block_0146.s2` (477 characters): October 2026: added Graphite; removed Omniscient Digital and Digital Authority Partners; added each company's fee, minimum, and term where its site publishes them, and its most recent dated result, each checked on the company's own site; replaced the AI Overviews and LLM citations criteria with AI visibility measurement and earned media guidance, and re-scored every company on what it publishes; added sections on measurement and on what an agency can and cannot do for you.
- `block_0127.s1` (298 characters): The companies on this list with published ChatGPT or LLM results are The SEO Works (ChatGPT referrals up 121% for DHL), Graphite (LLM sign-ups doubled for Webflow), Siege Media (LLM visibility from 11% to 43% for Grow Therapy), and Single Grain (113 more ChatGPT mentions for LS Building Products).
- `block_0123.s1` (272 characters): The best AI SEO companies in 2026 are Searchbloom, The SEO Works, Tinuiti, Graphite, and iPullRank, ranked on AI visibility measurement, earned media on the pages AI reads, the technical and structured-data foundation, content and entity authority, and documented results.
- `block_0133.s1` (268 characters): Among the companies on this list that publish a price, Searchbloom's SEO starts at $3,000 a month, The SEO Works starts at GBP 1,500 a month on a 12-month campaign, and Siege Media's content marketing minimum is $8,000 a month on a 12-month contract with a 30-day out.
- `block_0031.f5.s1` (261 characters): Overview: The SEO Works is a specialist agency founded in Sheffield in 2009, with a US office in Philadelphia, that has deliberately stayed in its lane: organic SEO, technical SEO, content, link building, and now GEO and AI SEO, sold as one integrated campaign.
- `block_0143.s2` (246 characters): It is the only company at 9 or above on all five, it wrote and published the MERIT methodology for AI search, it published its own study of 68,631 AI answers, and it publishes a dated result where AI search leads are counted in the partner's CRM.
- `block_0003.s2` (234 characters): The part that is new is measurement, and the part most companies miss is that AI answers are built from pages you do not own: across 68,631 AI answers Searchbloom tracked in its own category, its own website was 8.9% of what AI cited.
- `block_0033.f5.s2` (229 characters): Its AI SEO offering, launched in June 2025, starts with an audit of how discoverable a brand is in AI answers, then builds a prompt library mapped to buying stages and tracks which prompts and pages cite the brand using Profound.
- `block_0131.s1` (229 characters): The SEO Works, Seer Interactive, and iPullRank publish the clearest AI Overview results: AI Overview citations up 287% for DHL, AI Overview references up 2.8x for Trex, and AI Overview visibility up 278% for a self-storage brand.
- `block_0002.s2` (223 characters): They score highest on five things: measuring AI visibility, earning the brand a place on the other people's pages AI reads, the technical and structured-data foundation, content and entity authority, and documented results.

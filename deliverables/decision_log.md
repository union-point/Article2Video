# Decision Log — Article-to-Video Automation

## 1. Objective

Build an end-to-end automated pipeline that converts a blog article into a narrated explainer video.

The main goal was to make video production repeatable: provide a new article, run a single command, and produce a finished video with minimal manual intervention.

The workflow automates content extraction, fact verification, scripting, voiceover generation, synchronization, visual composition, and rendering.

## 2. Key Technical Decisions

| Component | Technology | Why I Chose It |
|---|---|---|
| Article extraction | Python, structured parsing | Extract content while preserving traceable source evidence |
| Content analysis and scripting | OpenAI GPT-6.1 Sol | Generate structured claims, narration, and content plans |
| Independent verification | OpenAI GPT-6.1 Terra + Python validation | Cross-check factual claims and catch unsupported numbers or entities |
| Voiceover | OpenAI GPT-4o Mini TTS (Alloy) | Produce consistent English narration without manual recording |
| Audio synchronization | OpenAI Whisper | Generate timestamps to align visual elements with narration |
| Visual planning | LLM + predefined templates | Automate creative decisions within controlled design constraints |
| Video composition | React + Remotion | Generate reusable, animated video layouts programmatically |
| Rendering and validation | Remotion + FFmpeg | Export and validate 1920×1080 MP4 output |
| Optimization | Caching, structured outputs, deterministic checks | Reduce redundant API calls and improve reproducibility |

The LLM handles tasks that require semantic understanding and creative planning. Deterministic code handles validation, synchronization, layout constraints, and rendering wherever possible.

This separation makes the workflow more predictable and easier to scale.

## 3. Automated Workflow

The entire production process is orchestrated through a single command.

**Article URL → Extraction → Fact Analysis → Script → AI Voiceover → Timing → Storyboard → Rendering → MP4**

The pipeline automatically:

1. Extracts the article and preserves supporting evidence.
2. Selects relevant content and generates a source-grounded script.
3. Validates factual claims and produces the Fact Sheet.
4. Generates English narration using AI text-to-speech.
5. Synchronizes narration and visual elements using timestamps.
6. Selects visual templates and generates animated scenes.
7. Renders the final video and validates the output.

Intermediate artifacts are retained for traceability, debugging, and reproducibility.

## 4. Quality Control by Design

Quality checks are integrated into the automated workflow rather than treated as separate manual production steps.

**Factual accuracy:** Claims are linked to source evidence and checked using deterministic validation and independent semantic verification.

**Structured generation:** Strict schemas prevent invalid model outputs from propagating through the pipeline.

**Visual consistency:** Six reusable Remotion templates provide controlled layouts, animations, and typography. The LLM selects predefined options rather than generating arbitrary React components.

**Synchronization:** Whisper timestamps drive the timing of visual elements. The pipeline retains timing diagnostics where alignment is uncertain.

**Output validation:** Automated checks verify media properties, including resolution, codecs, frame rate, and duration.

**Human oversight:** Manual review remains available for editorial decisions and exceptional cases, without requiring every production step to be performed manually.

## 5. Trade-offs and Limitations

**Template-based generation vs. unrestricted creativity**

Reusable templates improve consistency, reliability, and production speed. The trade-off is less creative flexibility than fully manual video editing. Controlled variants and motion graphics help reduce visual repetition.

**Automated verification vs. perfect accuracy**

Combining Python checks with independent LLM verification reduces unsupported claims, but semantic verification is not infallible. Source traceability and optional human review provide additional safeguards.

**Automatic synchronization vs. precise alignment**

Whisper provides practical timing information without manual editing. Some timestamps may be inaccurate, so the pipeline retains diagnostics and uses fallback alignment where necessary.

**Automation vs. production cost**

Multiple AI stages introduce API costs. Caching, targeted repairs, and reusable intermediate results reduce unnecessary requests and repeated computation.

**Future improvements:** Broader visual template variety, more accurate word-level alignment, and parallel batch processing.

## 6. Development Tools

- **OpenAI Codex:** AI-assisted coding and debugging
- **ChatGPT:** Brainstorming and exploring alternative approaches.
- **Git & GitHub:** Version control and project delivery.
- **Remotion Studio:** Visual previews and animation refinement.
- **FFmpeg / FFprobe:** Media inspection, troubleshooting, and output validation.

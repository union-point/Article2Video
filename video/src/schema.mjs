import { z } from "zod";
const frame = z.number().int().nonnegative();
const ids = z
  .array(z.string().min(1))
  .min(1)
  .refine((a) => new Set(a).size === a.length, "Duplicate IDs");
export const elementSchema = z
  .object({
    element_id: z.string().min(1),
    role: z.enum(["title", "body"]),
    text: z.string().trim().min(1).max(120),
    claim_ids: ids,
    source_ids: ids,
    start_frame: frame,
    end_frame: frame,
  })
  .strict()
  .superRefine((e, ctx) => {
    if (e.end_frame <= e.start_frame)
      ctx.addIssue({
        code: "custom",
        message: "Element must have positive duration",
      });
    if (e.role === "title" && [...e.text].length > 80)
      ctx.addIssue({ code: "custom", message: "Title exceeds 80 characters" });
  });
export const sceneSchema = z
  .object({
    scene_id: z.string().min(1),
    component: z.enum([
      "title",
      "methodology",
      "ranking",
      "statistic",
      "comparison",
      "conclusion",
    ]),
    layout: z.enum(["wide", "split"]),
    animation: z.enum(["calm", "brisk"]),
    theme: z.enum(["paper", "slate"]),
    composition: z
      .enum([
        "dossier",
        "pipeline",
        "network",
        "orbit",
        "ledger",
        "magnitude",
        "dual",
        "checklist",
      ])
      .optional(),
    reveal: z.enum(["draw", "focus", "cascade"]).optional(),
    primary_node: z.number().int().min(0).max(5).optional(),
    visual_nodes: z
      .array(
        elementSchema.refine(
          (e) => e.role === "body" && e.text.length <= 48,
          "Visual node must be a short body label",
        ),
      )
      .max(6)
      .optional(),
    start_frame: frame,
    duration_frames: z.number().int().positive(),
    timing_method: z.enum(["aligned", "even_fallback"]),
    elements: z.array(elementSchema).min(1).max(7),
  })
  .strict()
  .superRefine((s, ctx) => {
    const fail = (message) => ctx.addIssue({ code: "custom", message });
    if (s.component === "ranking" && s.elements.length > 5)
      fail("Ranking supports at most four body items");
    if (
      s.elements[0].role !== "title" ||
      s.elements.slice(1).some((e) => e.role !== "body")
    )
      fail("Exactly one leading title required");
    if (
      s.component === "comparison" &&
      s.elements.length < 3 &&
      (s.visual_nodes?.length ?? 0) < 2
    )
      fail("Comparison requires two body items");
    if (new Set(s.elements.map((e) => e.element_id)).size !== s.elements.length)
      fail("Duplicate element IDs");
    if (
      new Set(
        [...s.elements, ...(s.visual_nodes ?? [])].map((e) => e.element_id),
      ).size !==
      s.elements.length + (s.visual_nodes?.length ?? 0)
    )
      fail("Duplicate visual IDs");
    const allowed = {
      title: ["dossier"],
      methodology: ["pipeline", "network", "orbit"],
      ranking: ["ledger"],
      statistic: ["magnitude"],
      comparison: ["dual"],
      conclusion: ["checklist"],
    };
    if (s.composition && !allowed[s.component].includes(s.composition))
      fail("Incompatible composition");
    if (
      s.visual_nodes?.length &&
      (s.primary_node ?? 0) >= s.visual_nodes.length
    )
      fail("Primary node out of range");
    for (const e of [...s.elements, ...(s.visual_nodes ?? [])])
      if (
        e.start_frame < s.start_frame ||
        e.end_frame > s.start_frame + s.duration_frames
      )
        fail("Element outside scene");
  });
export const storyboardSchema = z
  .object({
    schema_version: z.literal("1.0"),
    stage: z.literal("storyboard"),
    template_version: z.enum(["storyboard.v1", "storyboard.v2"]),
    width: z.literal(1920),
    height: z.literal(1080),
    fps: z.literal(30),
    duration_frames: z.number().int().positive(),
    scenes: z.array(sceneSchema).min(2).max(8),
    inputs: z.record(z.string(), z.string()).optional(),
    run: z
      .object({
        requested_model: z.string(),
        resolved_model: z.string(),
        prompt_version: z.string(),
        cache_key: z.string(),
        response_id: z.string().nullable(),
        usage: z.record(z.string(), z.number()),
      })
      .strict()
      .optional(),
    review: z
      .object({
        status: z.literal("review_required"),
        timing_status: z.enum(["valid", "review_required"]),
        timing_issues: z.array(
          z
            .object({
              code: z.string(),
              target: z.string(),
              message: z.string(),
            })
            .strict(),
        ),
        listening_review: z.literal("pending"),
        visual_review: z.literal("pending"),
      })
      .strict()
      .optional(),
  })
  .strict()
  .superRefine((m, ctx) => {
    const fail = (message) => ctx.addIssue({ code: "custom", message });
    if (
      m.scenes[0].component !== "title" ||
      m.scenes.at(-1).component !== "conclusion"
    )
      fail("Title first, conclusion last");
    if (new Set(m.scenes.map((s) => s.scene_id)).size !== m.scenes.length)
      fail("Duplicate scenes");
    let end = 0;
    m.scenes.forEach((s, i) => {
      if (s.start_frame !== end) fail("Scene timeline must be contiguous");
      if (i && m.scenes[i - 1].component === s.component)
        fail("Adjacent templates repeat");
      if (
        i > 0 &&
        i < m.scenes.length - 1 &&
        ["title", "conclusion"].includes(s.component)
      )
        fail("Reserved boundary template");
      end += s.duration_frames;
    });
    if (end !== m.duration_frames) fail("Duration differs from scene timeline");
  });

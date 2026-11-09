import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { fitTextOnNLines } from "@remotion/layout-utils";
import { explicitProportion } from "./proportion.mjs";
import { tokens } from "./tokens";
import type { StoryScene } from "./types";

const Fit: React.FC<{
  text: string;
  width: number;
  size?: number;
  lines?: number;
  weight?: number;
  height?: number;
}> = ({ text, width, size = 64, lines = 3, weight = 600, height = 1000 }) => {
  const { fontSize } = fitTextOnNLines({
    text,
    fontFamily: tokens.fonts.body,
    fontWeight: weight,
    maxBoxWidth: width,
    maxLines: lines,
    maxFontSize: Math.min(size, height / (lines * 1.08)),
  });
  return (
    <div
      data-fit-warning={fontSize < 36 ? "minimum-size" : undefined}
      style={{
        width,
        fontSize,
        fontWeight: weight,
        lineHeight: 1.08,
        overflowWrap: "anywhere",
        outline: fontSize < 36 ? "3px solid red" : undefined,
      }}
    >
      {text}
    </div>
  );
};
// No numeric glyphs in these semantic line drawings: they encode document,
// question, linked-source and collection structure, never invented data.
const Symbol: React.FC<{ kind: string; color: string }> = ({ kind, color }) => (
  <svg
    width="96"
    height="96"
    viewBox="0 0 96 96"
    fill="none"
    stroke={color}
    strokeWidth="4"
    strokeLinecap="round"
    aria-hidden
  >
    {kind === "dossier" || kind === "checklist" ? (
      <>
        <path d="M24 12h34l16 16v56H24zM58 12v20h16" />
        <path d="M34 46h28M34 60h22M34 74h16" />
      </>
    ) : kind === "network" || kind === "orbit" ? (
      <>
        <path d="M48 48L18 20M48 48l30-28M48 48v32" />
        <circle cx="48" cy="48" r="13" />
        <circle cx="18" cy="20" r="8" />
        <circle cx="78" cy="20" r="8" />
        <circle cx="48" cy="80" r="8" />
      </>
    ) : (
      <>
        <rect x="10" y="16" width="76" height="24" rx="5" />
        <rect x="10" y="56" width="76" height="24" rx="5" />
        <path d="M26 28h42M26 68h42" />
      </>
    )}
  </svg>
);
const defaults = {
  title: "dossier",
  methodology: "pipeline",
  ranking: "ledger",
  statistic: "magnitude",
  comparison: "dual",
  conclusion: "checklist",
} as const;
const Editorial: React.FC<{ scene: StoryScene }> = ({ scene }) => {
  const local = useCurrentFrame();
  const frame = local + scene.start_frame;
  const t = tokens.themes[scene.theme];
  const kind = scene.composition ?? defaults[scene.component];
  const nodes = scene.visual_nodes?.length
    ? scene.visual_nodes
    : scene.elements.slice(1);
  const intro = scene.component === "title";
  const closing = scene.component === "conclusion";
  const wide = scene.layout === "wide";
  const motion = tokens.motion[scene.animation];
  const progress = (from: number) =>
    interpolate(frame, [from, from + motion], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const diagramX = intro ? 900 : wide ? 80 : 720;
  const diagramY = wide && !intro ? 340 : 180;
  const diagramW = 1840 - diagramX;
  const diagramH = wide && !intro ? 480 : closing ? 510 : 540;
  const list = kind === "ledger" || kind === "checklist";
  const columns = list
    ? nodes.length > 3
      ? 2
      : 1
    : kind === "dual" || kind === "network" || kind === "orbit"
      ? 2
      : Math.min(3, Math.max(1, nodes.length));
  const rows = Math.ceil(nodes.length / columns);
  const positions = nodes.map((_, i) => {
    if (kind === "magnitude" && nodes.length <= 3) {
      const primary = scene.primary_node ?? 0;
      if (i === primary) return { x: 0, y: 0, w: diagramW * 0.61, h: diagramH };
      const index = i < primary ? i : i - 1;
      return { x: diagramW * 0.65, y: index * 260, w: diagramW * 0.35, h: 230 };
    }
    const w = (diagramW - (columns - 1) * 28) / columns;
    const h = Math.min(
      list ? 170 : 250,
      (diagramH - (rows - 1) * 28) / Math.max(1, rows),
    );
    return {
      x: (i % columns) * (w + 28),
      y: Math.floor(i / columns) * (h + 28),
      w,
      h,
    };
  });
  return (
    <AbsoluteFill
      style={{
        background: t.background,
        color: t.ink,
        fontFamily: tokens.fonts.body,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 80,
          top: 72,
          width: intro ? 710 : wide ? 1640 : 540,
          opacity: interpolate(local, [0, 18], [0, 1], {
            extrapolateRight: "clamp",
          }),
          translate: `0 ${interpolate(local, [0, 24], [22, 0], { extrapolateRight: "clamp" })}px`,
        }}
      >
        <div style={{ marginBottom: intro ? 64 : 28 }}>
          <Symbol kind={kind} color={t.accent} />
        </div>
        <Fit
          text={scene.elements[0].text}
          width={intro ? 710 : wide ? 1640 : 540}
          size={intro ? 132 : wide ? 88 : 94}
          lines={wide && !intro ? 1 : 4}
          weight={800}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: diagramX,
          top: diagramY,
          width: diagramW,
          height: diagramH,
        }}
      >
        {(kind === "network" || kind === "orbit" || kind === "pipeline") &&
        nodes.length > 1 ? (
          <svg
            width={diagramW}
            height={diagramH}
            style={{ position: "absolute", inset: 0 }}
          >
            {positions.map((p, i) => {
              if (i === (scene.primary_node ?? 0) && kind !== "pipeline")
                return null;
              if (!i && kind === "pipeline") return null;
              const a =
                kind === "pipeline"
                  ? positions[i - 1]
                  : positions[scene.primary_node ?? 0];
              return (
                <line
                  key={i}
                  x1={a.x + a.w / 2}
                  y1={a.y + a.h / 2}
                  x2={p.x + p.w / 2}
                  y2={p.y + p.h / 2}
                  stroke={t.accent}
                  strokeWidth={3}
                  pathLength={1}
                  strokeDasharray={1}
                  strokeDashoffset={1 - progress(nodes[i].start_frame)}
                />
              );
            })}
          </svg>
        ) : null}
        {nodes.map((node, i) => {
          const p = positions[i];
          const reveal = progress(
            node.start_frame + (scene.reveal === "cascade" ? i * 6 : 0),
          );
          const primary = i === (scene.primary_node ?? 0);
          const featured =
            primary && (kind === "magnitude" || kind === "dossier");
          const proportion =
            kind === "magnitude" && primary
              ? explicitProportion(node.text)
              : null;
          const size =
            kind === "magnitude" && primary
              ? 140
              : kind === "ledger" || kind === "checklist"
                ? 48
                : 56;
          return (
            <div
              key={node.element_id}
              data-source-ids={node.source_ids.join(" ")}
              style={{
                position: "absolute",
                left: p.x,
                top: p.y,
                width: p.w,
                height: p.h,
                boxSizing: "border-box",
                padding: 28,
                display: "flex",
                flexDirection: proportion ? "column" : "row",
                justifyContent: proportion ? "center" : undefined,
                gap: proportion ? 30 : undefined,
                alignItems: "center",
                borderRadius: tokens.radius,
                background: primary ? t.ink : t.surface,
                color: primary ? t.background : t.ink,
                border: `2px solid ${primary ? t.ink : t.muted}`,
                opacity: reveal,
                translate:
                  scene.reveal === "focus" ? "0 0" : `0 ${(1 - reveal) * 24}px`,
                scale: scene.reveal === "focus" ? 0.94 + 0.06 * reveal : 1,
                boxShadow: featured ? `12px 12px 0 ${t.signal}` : undefined,
              }}
            >
              {closing ? (
                <div
                  style={{
                    width: 24,
                    height: 24,
                    border: `3px solid ${primary ? t.signal : t.accent}`,
                    borderRadius: 24,
                    marginRight: 22,
                    flexShrink: 0,
                  }}
                />
              ) : null}
              {proportion ? (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${Math.min(10, proportion.denominator)}, 1fr)`,
                    gap: 14,
                    width: p.w - 90,
                  }}
                  aria-hidden
                >
                  {Array.from({ length: proportion.denominator }, (_, dot) => (
                    <div
                      key={dot}
                      style={{
                        height: 64,
                        borderRadius: 8,
                        border: `3px solid ${t.accent}`,
                        background:
                          dot < proportion.numerator ? t.accent : "transparent",
                        opacity: interpolate(
                          frame,
                          [
                            node.start_frame + dot * 3,
                            node.start_frame + dot * 3 + 12,
                          ],
                          [0, 1],
                          {
                            extrapolateLeft: "clamp",
                            extrapolateRight: "clamp",
                          },
                        ),
                      }}
                    />
                  ))}
                </div>
              ) : null}
              <Fit
                text={node.text}
                width={p.w - 56 - (closing ? 46 : 0)}
                size={proportion ? 72 : size}
                lines={kind === "magnitude" && primary ? 4 : p.h < 190 ? 2 : 3}
                height={p.h - (proportion ? 170 : 56)}
              />
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
export const Title: React.FC<{ scene: StoryScene }> = ({ scene }) => (
  <Editorial scene={scene} />
);
export const Methodology: React.FC<{ scene: StoryScene }> = ({ scene }) => (
  <Editorial scene={scene} />
);
export const Ranking: React.FC<{ scene: StoryScene }> = ({ scene }) => (
  <Editorial scene={scene} />
);
export const Statistic: React.FC<{ scene: StoryScene }> = ({ scene }) => (
  <Editorial scene={scene} />
);
export const Comparison: React.FC<{ scene: StoryScene }> = ({ scene }) => (
  <Editorial scene={scene} />
);
export const Conclusion: React.FC<{ scene: StoryScene }> = ({ scene }) => (
  <Editorial scene={scene} />
);
export const templates = {
  title: Title,
  methodology: Methodology,
  ranking: Ranking,
  statistic: Statistic,
  comparison: Comparison,
  conclusion: Conclusion,
};

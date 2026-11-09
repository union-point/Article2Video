import React from "react";
import {
  Sequence,
  staticFile,
  useVideoConfig,
  useCurrentFrame,
} from "remotion";
import { Audio } from "@remotion/media";
import { fitTextOnNLines } from "@remotion/layout-utils";
import { tokens } from "./tokens";
import { templates } from "./Templates";
import { storyboardSchema } from "./schema.mjs";
import type { Storyboard } from "./types";

type Caption = { text: string; start: number; end: number };

const Overlays: React.FC<{ manifest: Storyboard; captions: Caption[] }> = ({
  manifest,
  captions,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const caption = captions.find(
    (item) => frame / fps >= item.start && frame / fps < item.end,
  );
  const theme = tokens.themes.slate;
  const { fontSize } = fitTextOnNLines({
    text: caption?.text || " ",
    fontFamily: tokens.fonts.body,
    fontWeight: 400,
    maxBoxWidth: 1600,
    maxLines: 3,
    maxFontSize: 46,
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        right: 80,
        bottom: 28,
        padding: "18px 24px 20px",
        borderRadius: tokens.radius,
        background: theme.background,
        color: theme.ink,
        fontFamily: tokens.fonts.body,
      }}
    >
      <div
        style={{
          height: 150,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          overflow: "hidden",
        }}
      >
        {caption && (
          <div
            style={{
              width: 1600,
              fontSize,
              lineHeight: 1.08,
              overflowWrap: "anywhere",
            }}
          >
            {caption.text}
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        {manifest.scenes.map((scene) => {
          const progress = Math.max(
            0,
            Math.min(
              1,
              (frame + 1 - scene.start_frame) / scene.duration_frames,
            ),
          );
          return (
            <div
              key={scene.scene_id}
              style={{
                flex: 1,
                height: 8,
                background: theme.muted,
                borderRadius: 4,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${progress * 100}%`,
                  height: "100%",
                  background: theme.accent,
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const StoryboardVideo: React.FC<{
  manifest: Storyboard;
  captions?: Caption[];
  narration?: string;
  narrationVolume?: number;
}> = ({ manifest, captions = [], narration, narrationVolume = 1 }) => {
  storyboardSchema.parse(manifest);
  const { fps } = useVideoConfig();
  return (
    <>
      {narration ? (
        <Audio
          src={staticFile(narration)}
          volume={narrationVolume}
          premountFor={fps}
        />
      ) : null}
      {manifest.scenes.map((scene) => {
        const Template = templates[scene.component];
        return (
          <Sequence
            key={scene.scene_id}
            name={scene.scene_id}
            from={scene.start_frame}
            durationInFrames={scene.duration_frames}
            premountFor={fps}
          >
            <Template scene={scene} />
          </Sequence>
        );
      })}
      <Overlays manifest={manifest} captions={captions} />
    </>
  );
};

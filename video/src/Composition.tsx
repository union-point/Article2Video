import React from "react";
import { Sequence, useVideoConfig } from "remotion";
import { templates } from "./Templates";
import { storyboardSchema } from "./schema.mjs";
import type { Storyboard } from "./types";

export const StoryboardVideo: React.FC<{ manifest: Storyboard }> = ({
  manifest,
}) => {
  storyboardSchema.parse(manifest);
  const { fps } = useVideoConfig();
  return (
    <>
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
    </>
  );
};

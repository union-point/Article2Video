import { Composition } from "remotion";
import { StoryboardVideo } from "./Composition";
import { storyboardSchema } from "./schema.mjs";
import example from "../public/storyboard.json";
import captions from "../public/captions.json";
import type { Storyboard } from "./types";

export const RemotionRoot = () => (
  <Composition
    id="Storyboard"
    component={StoryboardVideo}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={180}
    defaultProps={{ manifest: example as Storyboard, captions }}
    calculateMetadata={({ props }) => {
      const data = storyboardSchema.parse(props.manifest);
      return { durationInFrames: data.duration_frames };
    }}
  />
);

export type ScreenElement = {
  element_id: string;
  role: "title" | "body";
  text: string;
  claim_ids: string[];
  source_ids: string[];
  start_frame: number;
  end_frame: number;
};
export type StoryScene = {
  scene_id: string;
  component:
    | "title"
    | "methodology"
    | "ranking"
    | "statistic"
    | "comparison"
    | "conclusion";
  composition?:
    | "dossier"
    | "pipeline"
    | "network"
    | "orbit"
    | "ledger"
    | "magnitude"
    | "dual"
    | "checklist";
  reveal?: "draw" | "focus" | "cascade";
  primary_node?: number;
  visual_nodes?: ScreenElement[];
  layout: "wide" | "split";
  animation: "calm" | "brisk";
  theme: "paper" | "slate";
  start_frame: number;
  duration_frames: number;
  timing_method: "aligned" | "even_fallback";
  elements: ScreenElement[];
};
export type Storyboard = {
  schema_version: "1.0";
  stage: "storyboard";
  template_version: "storyboard.v1" | "storyboard.v2";
  width: 1920;
  height: 1080;
  fps: 30;
  duration_frames: number;
  scenes: StoryScene[];
};

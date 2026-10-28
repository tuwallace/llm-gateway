import React from "react";
import { Composition } from "remotion";
import { W, H, FPS, clipSeconds } from "./ui";
import { Hook, Stack, Caps, Pool, Failure, Variance, Honest, Takeaways } from "./Scenes";
import { Seg3, Seg4, Seg5 } from "./LiveSegs";
import { Thumbnail } from "./Thumbnail";

// Each clip is as long as its narration audio (+2 s) -- see ../narration/build_narration.py and ../../script.md.
const CLIPS = [
  { id: "Hook", c: Hook, seg: "seg1" }, { id: "Stack", c: Stack, seg: "seg2" }, { id: "Seg3", c: Seg3, seg: "seg3" },
  { id: "Seg4", c: Seg4, seg: "seg4" }, { id: "Seg5", c: Seg5, seg: "seg5" }, { id: "Caps", c: Caps, seg: "seg6" },
  { id: "Pool", c: Pool, seg: "seg7" }, { id: "Failure", c: Failure, seg: "seg8" }, { id: "Variance", c: Variance, seg: "seg9" },
  { id: "Honest", c: Honest, seg: "seg10" }, { id: "Takeaways", c: Takeaways, seg: "seg11" },
];
export const Root: React.FC = () => (
  <>{CLIPS.map((k) => <Composition key={k.id} id={k.id} component={k.c} durationInFrames={Math.ceil(clipSeconds(k.seg) * FPS)} fps={FPS} width={W} height={H} />)}<Composition id="Thumbnail" component={Thumbnail} durationInFrames={1} fps={FPS} width={1280} height={720} /></>
);

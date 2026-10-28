import React from "react";
import { AbsoluteFill } from "remotion";
import { C, FONT } from "./ui";

// 1280x720 thumbnail: five team tiles, one flaring red, and the one-line thesis. No terminal text, keys or logos.
export const Thumbnail: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, color: C.text, padding: "60px 70px" }}>
    <div style={{ fontSize: 150, fontWeight: 900, letterSpacing: -4, lineHeight: 0.95, marginTop: 20 }}>LIMITS</div>
    <div style={{ fontSize: 150, fontWeight: 900, letterSpacing: -4, lineHeight: 0.95, color: C.red }}>{"≠"} ISOLATION</div>
    <div style={{ display: "flex", gap: 20, marginTop: 56 }}>
      {["search", "support", "analytics", "research", "intern"].map((t) => (
        <div key={t} style={{ flex: 1, textAlign: "center", padding: "26px 0", borderRadius: 18, background: C.panel, fontSize: 30, fontWeight: 700,
          border: `4px solid ${t === "research" ? C.red : t === "support" ? C.teal : C.panelLine}`, boxShadow: t === "research" ? "0 0 50px rgba(255,107,107,.7)" : "none" }}>{t}</div>
      ))}
    </div>
    <div style={{ fontSize: 40, color: C.muted, marginTop: 34 }}>support waits <span style={{ color: C.teal }}>1 s</span> {"→"} <span style={{ color: C.red }}>38 s</span></div>
  </AbsoluteFill>
);

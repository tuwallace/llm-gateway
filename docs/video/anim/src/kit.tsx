import React from "react";
import { Appear, C, FONT, useProgress } from "./ui";

export const Card: React.FC<{ at: number; color?: string; title: string; children?: React.ReactNode; flex?: number; style?: React.CSSProperties }> = ({ at, color = C.panelLine, title, children, flex = 1, style }) => (
  <Appear at={at} style={{ flex, background: C.panel, border: `3px solid ${color}`, borderRadius: 22, padding: "28px 34px", ...style }}>
    <div style={{ fontSize: 38, fontWeight: 800, color: color === C.panelLine ? C.text : color }}>{title}</div>
    {children && <div style={{ fontSize: 30, color: C.muted, marginTop: 12, lineHeight: 1.35 }}>{children}</div>}
  </Appear>
);

export const Big: React.FC<{ at: number; value: string; label: string; color: string; flex?: number }> = ({ at, value, label, color, flex = 1 }) => (
  <Appear at={at} style={{ flex, background: C.panel, border: `3px solid ${color}`, borderRadius: 22, padding: "30px 36px" }}>
    <div style={{ fontSize: 110, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
    <div style={{ fontSize: 30, color: C.muted, marginTop: 14 }}>{label}</div>
  </Appear>
);

export const Hbar: React.FC<{ at: number; label: string; value: number; max: number; color: string; unit?: string }> = ({ at, label, value, max, color, unit = " s" }) => {
  const p = useProgress(at, 1.0);
  return (
    <div style={{ display: "flex", alignItems: "center", margin: "14px 0", opacity: Math.min(1, p * 3) }}>
      <div style={{ width: 360, fontSize: 30, color: C.muted }}>{label}</div>
      <div style={{ flex: 1, background: "#0b0f19", borderRadius: 10, height: 52 }}>
        <div style={{ width: `${(value / max) * 100 * p}%`, height: 52, background: color, borderRadius: 10 }} />
      </div>
      <div style={{ width: 170, fontSize: 40, fontWeight: 800, textAlign: "right" }}>{(value * p).toFixed(1)}{unit}</div>
    </div>
  );
};

/** Table whose rows appear at their own times. */
export const Table: React.FC<{ head: string[]; widths: number[]; rows: { at: number; cells: React.ReactNode[]; color?: string }[]; size?: number }> = ({ head, widths, rows, size = 30 }) => (
  <div style={{ fontFamily: FONT }}>
    <div style={{ display: "flex", fontSize: size - 4, color: C.muted, borderBottom: `2px solid ${C.panelLine}`, paddingBottom: 10 }}>
      {head.map((h, i) => <div key={h} style={{ width: widths[i] }}>{h}</div>)}
    </div>
    {rows.map((r, k) => (
      <Appear key={k} at={r.at} style={{ display: "flex", fontSize: size, padding: "16px 0", borderBottom: `1px solid ${C.panelLine}`, color: r.color ?? C.text, alignItems: "center" }}>
        {r.cells.map((c, i) => <div key={i} style={{ width: widths[i] }}>{c}</div>)}
      </Appear>
    ))}
  </div>
);

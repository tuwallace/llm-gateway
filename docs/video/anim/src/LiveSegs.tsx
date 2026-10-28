import React from "react";
import { beat } from "./ui";
import { Ev, TerminalScene } from "./Terminal";
import cap from "./captures.json";

// Terminal replays of REAL captured output (docs/video/demo/*, captured by demo/build_captures.py), timed to the narration.
const lines = (k: "seg3" | "seg4" | "seg5") => cap[k].split("\n");

export const Seg3: React.FC = () => {
  const S = "seg3", L = lines("seg3"), go = beat(S, "Each team gets");
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg3_teams.py", cps: 40 },
    { kind: "print", at: go, text: L.slice(0, 4).join("\n"), reveal: 0.6 },
    { kind: "print", at: go + 0.8, text: L.slice(4, 8).join("\n"), reveal: 1.0 },
    { kind: "hl", at: beat(S, "Local models are free"), until: beat(S, "The intern team"), match: ["price per token"] },
    { kind: "hl", at: beat(S, "The intern team"), until: beat(S, "One caveat"), match: ["intern-sandbox"] },
  ];
  return <TerminalScene seg={S} events={ev} title="llm-gateway" />;
};

export const Seg4: React.FC = () => {
  const S = "seg4", L = lines("seg4");
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg4_cache.py", cps: 40 },
    { kind: "print", at: beat(S, "A semantic cache"), text: L[0] },
    { kind: "print", at: beat(S, "Ask for the capital"), text: L[1] },
    { kind: "print", at: beat(S, "Ask it a different way"), text: L[2] },
    { kind: "print", at: beat(S, "Ask about Germany"), text: L[3] },
    { kind: "print", at: beat(S, "That works because"), text: L[4] + "\n" + L[5] + "\n" + L[6] },
    { kind: "hl", at: beat(S, "Ask for the capital"), until: beat(S, "Ask it a different way"), match: ["original question"] },
    { kind: "hl", at: beat(S, "Ask it a different way"), until: beat(S, "Ask about Germany"), match: ["paraphrase"] },
    { kind: "hl", at: beat(S, "Ask about Germany"), until: beat(S, "That works because"), match: ["same shape"] },
    { kind: "hl", at: beat(S, "That works because"), until: beat(S, "At zero point eight"), match: ["similarity threshold"] },
  ];
  return <TerminalScene seg={S} events={ev} title="llm-gateway" />;
};

export const Seg5: React.FC = () => {
  const S = "seg5", L = lines("seg5");
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg5_simulation.py", cps: 40 },
    { kind: "print", at: beat(S, "To test it I sent"), text: L[0] },
    { kind: "print", at: beat(S, "The checks passed"), text: "\n" + L.slice(2, 8).join("\n"), reveal: 1.2 },
    { kind: "print", at: beat(S, "But look at support"), text: L.slice(8, 12).join("\n"), reveal: 0.8 },
    { kind: "hl", at: beat(S, "After a research burst"), until: beat(S, "Limits cap how much"), match: ["during a research burst"] },
    { kind: "hl", at: beat(S, "against about one second"), until: beat(S, "Limits cap how much"), match: ["otherwise"] },
    { kind: "print", at: beat(S, "Limits cap how much"), text: L.slice(12, 15).join("\n"), reveal: 1.0 },
  ];
  return <TerminalScene seg={S} events={ev} title="llm-gateway" />;
};

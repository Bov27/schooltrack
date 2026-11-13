/**
 * Same palette as the dashboard: Popayán's lime-washed walls (cal), deep painted wood
 * (tinta), chalkboard green for presence and school-desk yellow for a temporary exit.
 */
import type { AttendanceState } from "../core/attendance";

export const colors = {
  cal: "#f5f6f2",
  paper: "#ffffff",
  tinta: "#123a47",
  tinta2: "#1b4d5c",
  pizarra: "#1e6b52",
  pupitre: "#f2b318",
  text: "#17222b",
  muted: "#5a6670",
  border: "#e1e4de",
  // Kept for screens that still use the old names.
  accent: "#1b4d5c",
  ok: "#1e6b52",
  okBg: "#e3f1ea",
  warn: "#7a5800",
  warnBg: "#fdf3d6",
  bad: "#b3261e",
  badBg: "#fbe9e7",
};

/** The home header takes the colour of where the person is. */
export const stateTheme: Record<AttendanceState, { bg: string; fg: string; soft: string }> = {
  OUTSIDE: { bg: colors.tinta, fg: "#ffffff", soft: "#9fbcc3" },
  PRESENT: { bg: colors.pizarra, fg: "#ffffff", soft: "#bfe0d1" },
  TEMPORARY_EXIT: { bg: colors.pupitre, fg: colors.tinta, soft: "#5b4300" },
};

export const radius = { lg: 22, md: 14, sm: 10 };

export const typography = {
  hero: { fontSize: 34, fontWeight: "800" as const, letterSpacing: -0.5 },
  title: { fontSize: 22, fontWeight: "800" as const, letterSpacing: -0.3 },
  heading: { fontSize: 17, fontWeight: "700" as const },
  body: { fontSize: 16 },
  small: { fontSize: 13 },
};

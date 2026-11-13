/** Small stroke icons drawn inline, so the dashboard needs no icon package. */

const PATHS = {
  bell: "M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Z M10 20.5a2 2 0 0 0 4 0",
  roll: "M4 5h16v14H4z M8 9h2 M8 13h2 M13 9h3 M13 13h3 M8 17h8",
  clipboard: "M9 4h6v3H9z M7 5H5v16h14V5h-2 M9 12l2 2 4-4",
  chart: "M4 20h16 M7 16v-5 M12 16V7 M17 16v-8",
  pin: "M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11Z M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z M3 20a6 6 0 0 1 12 0 M16 4.5a3.5 3.5 0 0 1 0 6.5 M18 14.5a6 6 0 0 1 3 5.5",
  building: "M4 21V8l8-5 8 5v13 M9 21v-6h6v6 M3 21h18 M9 10h.01 M15 10h.01",
  logout: "M10 5H5v14h5 M15 8l4 4-4 4 M19 12H9",
  menu: "M4 7h16 M4 12h16 M4 17h16",
  close: "M6 6l12 12 M18 6 6 18",
  plus: "M12 5v14 M5 12h14",
  alert: "M12 3 2.5 20h19L12 3Z M12 10v4.5 M12 17.5h.01",
  check: "M5 12.5 10 17l9-10",
  download: "M12 4v11 M7.5 10.5 12 15l4.5-4.5 M5 20h14",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

const paths = {
  split: "M5 3h14v18H5z M9 3v18 M12 8h4 M12 12h4 M12 16h4",
  compare: "M3 5h7v14H3z M14 5h7v14h-7z",
  export: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
  samples: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  sun: "M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  doc: "M6 3h8l4 4v14H6z M14 3v5h4",
  play: "M8 5l11 7-11 7z",
} as const;
export default function Icon({ name }: { name: keyof typeof paths }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

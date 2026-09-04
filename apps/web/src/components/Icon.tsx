const PATHS: Record<string, string> = {
  cursor: "M5 3l12 7-5 1.5L9.5 17z",
  ruler: "M3 15l12-12 6 6-12 12z M8 10l2 2 M11 7l2 2 M14 4l2 2",
  cam: "M3 7h13v10H3z M16 10l5-2v8l-5-2z",
  cube: "M12 3l8 4.5v9L12 21l-8-4.5v-9z M4 7.5l8 4.5 8-4.5 M12 12v9",
  layers: "M12 4l9 5-9 5-9-5z M3 14l9 5 9-5",
  pin: "M12 21s-6-5.5-6-11a6 6 0 0112 0c0 5.5-6 11-6 11z M12 8v4",
  clip: "M4 4h16v16H4z M4 12h16 M12 4v16",
  draw: "M4 20l4-1 11-11-3-3L5 16z",
  search: "M5 11a6 6 0 1012 0 6 6 0 00-12 0z M20 20l-4.5-4.5",
  tent: "M3 20L12 4l9 16z M12 4v16",
  photo: "M3 5h18v14H3z M12 8.5a3.5 3.5 0 100 7 3.5 3.5 0 000-7z",
  target: "M12 5a7 7 0 100 14 7 7 0 000-14z M12 2v4 M12 18v4 M2 12h4 M18 12h4",
  check: "M5 12l4 4 10-10",
  play: "M7 5v14l11-7z",
  compass: "M12 3a9 9 0 100 18 9 9 0 000-18z M12 5l3 7-3 7-3-7z",
  chevron: "M9 6l6 6-6 6",
  x: "M6 6l12 12 M18 6L6 18",
};

export function Icon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={PATHS[name] ?? ""} />
    </svg>
  );
}

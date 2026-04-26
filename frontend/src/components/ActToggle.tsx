interface Props {
  value: string;
  onChange: (v: string) => void;
  allowBoth?: boolean;
  dark?: boolean;
}

export default function ActToggle({ value, onChange, allowBoth = true }: Props) {
  const opts = allowBoth
    ? [{ v: "2025", label: "2025 Act" }, { v: "1961", label: "1961 Act" }, { v: "both", label: "Both" }]
    : [{ v: "2025", label: "2025 Act" }, { v: "1961", label: "1961 Act" }];

  return (
    <div
      className="inline-flex rounded-lg p-0.5 gap-0.5"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)" }}
    >
      {opts.map(({ v, label }) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className="px-2.5 py-1 rounded-md text-xs font-semibold transition-all duration-150"
          style={
            value === v
              ? { background: "var(--accent)", color: "#fff", boxShadow: "0 1px 6px var(--accent-glow)" }
              : { color: "var(--text-muted)" }
          }
        >
          {label}
        </button>
      ))}
    </div>
  );
}

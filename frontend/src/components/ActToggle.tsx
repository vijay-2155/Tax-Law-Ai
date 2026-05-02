interface Props {
  value: string;
  onChange: (v: string) => void;
  allowBoth?: boolean;
  dark?: boolean;
}

export default function ActToggle({ value, onChange, allowBoth = true }: Props) {
  const opts = allowBoth
    ? [
        { v: "2025", label: "2025 Act" },
        { v: "1961", label: "1961 Act" },
        { v: "both", label: "Both" },
      ]
    : [
        { v: "2025", label: "2025 Act" },
        { v: "1961", label: "1961 Act" },
      ];

  const activeColor = (v: string) => {
    if (v === "2025") return { bg: "#fff0e8", color: "#cc4400", shadow: "0 1px 6px rgba(204,68,0,0.15)", border: "rgba(204,68,0,0.35)" };
    if (v === "1961") return { bg: "#dcf5e4", color: "#0a7504", shadow: "0 1px 6px rgba(10,117,4,0.15)", border: "rgba(10,117,4,0.3)" };
    return { bg: "#e8f0fe", color: "#2452b8", shadow: "0 1px 6px rgba(36,82,184,0.15)", border: "rgba(36,82,184,0.3)" };
  };

  return (
    <div
      className="inline-flex rounded-lg p-0.5 gap-0.5"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)" }}
    >
      {opts.map(({ v, label }) => {
        const isActive = value === v;
        const ac = activeColor(v);
        return (
          <button
            key={v}
            onClick={() => onChange(v)}
            className="px-2.5 py-1 rounded-md text-xs font-semibold transition-all duration-200"
            style={
              isActive
                ? {
                    background: ac.bg,
                    color: ac.color,
                    boxShadow: ac.shadow,
                    border: `1px solid ${ac.border}`,
                  }
                : { color: "var(--text-muted)", border: "1px solid transparent" }
            }
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

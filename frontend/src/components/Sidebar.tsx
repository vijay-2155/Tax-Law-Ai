import { NavLink } from "react-router-dom";
import { Search, BookOpen, LayoutGrid, MessageSquare, Settings, Scale } from "lucide-react";

const NAV = [
  { to: "/",        icon: Search,       label: "Search",   desc: "Find sections" },
  { to: "/browse",  icon: LayoutGrid,   label: "Browse",   desc: "By income head" },
  { to: "/chat",    icon: MessageSquare,label: "Ask AI",   desc: "Chat with Acts" },
];

export default function Sidebar() {
  return (
    <aside
      className="w-[220px] flex flex-col shrink-0 h-full"
      style={{
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border-subtle)",
      }}
    >
      {/* Logo */}
      <div className="px-4 pt-5 pb-4" style={{ borderBottom: "1px solid var(--border-faint)" }}>
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{
              background: "linear-gradient(135deg, #2563eb, #4a8bff)",
              boxShadow: "0 2px 12px rgba(74,139,255,0.35)",
            }}
          >
            <Scale className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-bold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>TaxIQ</div>
            <div className="text-[10px] font-medium" style={{ color: "var(--text-muted)", marginTop: "1px" }}>Income Tax Intelligence</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        <div className="px-2 pb-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Tools
          </span>
        </div>

        {NAV.map(({ to, icon: Icon, label, desc }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 group relative ${
                isActive ? "nav-active" : ""
              }`
            }
            style={({ isActive }) => isActive ? {} : {
              color: "var(--text-muted)",
            }}
          >
            {({ isActive }) => (
              <>
                <Icon
                  className="w-4 h-4 shrink-0 transition-colors"
                  style={{ color: isActive ? "var(--accent-light)" : "var(--text-muted)" }}
                />
                <div className="min-w-0">
                  <div
                    className="text-sm font-medium leading-none mb-0.5"
                    style={{ color: isActive ? "var(--text-primary)" : "var(--text-secondary)" }}
                  >
                    {label}
                  </div>
                  <div className="text-[11px] leading-none" style={{ color: "var(--text-muted)" }}>
                    {desc}
                  </div>
                </div>
                {isActive && (
                  <div
                    className="absolute right-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-l"
                    style={{ background: "var(--accent)" }}
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom — Acts info + Settings */}
      <div className="px-2 pb-3" style={{ borderTop: "1px solid var(--border-faint)" }}>
        <div className="px-3 py-2.5 rounded-lg mb-1 mt-2" style={{ background: "var(--accent-dim)" }}>
          <div className="flex items-center gap-2 mb-1">
            <BookOpen className="w-3 h-3 shrink-0" style={{ color: "var(--accent-light)" }} />
            <span className="text-xs font-semibold" style={{ color: "var(--accent-light)" }}>Two Acts Indexed</span>
          </div>
          <div className="text-[11px] space-y-0.5" style={{ color: "var(--text-muted)" }}>
            <div>IT Act 1961 · 5,109 vectors</div>
            <div>IT Act 2025 · 2,812 vectors</div>
          </div>
        </div>

        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 ${isActive ? "nav-active" : ""}`
          }
          style={({ isActive }) => isActive ? {} : { color: "var(--text-muted)" }}
        >
          {({ isActive }) => (
            <>
              <Settings
                className="w-4 h-4 shrink-0"
                style={{ color: isActive ? "var(--accent-light)" : "var(--text-muted)" }}
              />
              <span
                className="text-sm font-medium"
                style={{ color: isActive ? "var(--text-primary)" : "var(--text-secondary)" }}
              >
                Settings
              </span>
            </>
          )}
        </NavLink>
      </div>
    </aside>
  );
}

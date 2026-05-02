import { NavLink } from "react-router-dom";
import { Search, BookOpen, LayoutGrid, MessageSquare, Settings } from "lucide-react";

const NAV = [
  { to: "/",       icon: Search,        label: "Search",    desc: "Find sections" },
  { to: "/browse", icon: LayoutGrid,    label: "Browse",    desc: "By income head" },
  { to: "/chat",   icon: MessageSquare, label: "Ask AI",    desc: "Chat with Acts" },
];

export default function Sidebar() {
  return (
    <aside
      className="w-[228px] flex flex-col shrink-0 h-full govt-header"
      style={{
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border-subtle)",
      }}
    >
      {/* India stripe at top */}
      <div className="india-stripe" />

      {/* Logo / Brand */}
      <div
        className="px-4 pt-4 pb-4"
        style={{ borderBottom: "1px solid var(--border-faint)" }}
      >
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 overflow-hidden"
            style={{
              boxShadow: "0 2px 10px rgba(204,68,0,0.15)",
              border: "1px solid rgba(204,68,0,0.15)",
            }}
          >
            <img src="/favicon.png" alt="ActInsight icon" className="w-full h-full object-cover rounded-xl" />
          </div>
          <div>
            <div
              className="text-sm font-bold tracking-tight"
              style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}
            >
              ActInsight
            </div>
            <div
              className="text-[10px] font-medium"
              style={{ color: "var(--text-muted)", marginTop: "1px", letterSpacing: "0.04em" }}
            >
              Income Tax Intelligence
            </div>
          </div>
        </div>

        {/* Tagline badge */}
        <div
          className="mt-3 px-2.5 py-1 rounded-md text-[10px] font-medium"
          style={{
            background: "rgba(204,68,0,0.06)",
            border: "1px solid rgba(204,68,0,0.15)",
            color: "#cc4400",
            letterSpacing: "0.03em",
          }}
        >
          IT Act 1961 · IT Act 2025
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        <div className="px-2 pb-2 pt-1">
          <span
            className="text-[10px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Tools
          </span>
        </div>

        {NAV.map(({ to, icon: Icon, label, desc }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group relative ${
                isActive ? "nav-active" : ""
              }`
            }
            style={({ isActive }) =>
              isActive ? {} : { color: "var(--text-muted)" }
            }
          >
            {({ isActive }) => (
              <>
                <div
                  className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 transition-all duration-200"
                  style={{
                    background: isActive
                      ? "#fff0e8"
                      : "transparent",
                    border: isActive
                      ? "1px solid rgba(204,68,0,0.2)"
                      : "1px solid transparent",
                  }}
                >
                  <Icon
                    className="w-3.5 h-3.5 transition-colors"
                    style={{
                      color: isActive ? "#cc4400" : "var(--text-muted)",
                    }}
                  />
                </div>
                <div className="min-w-0">
                  <div
                    className="text-sm font-medium leading-none mb-0.5"
                    style={{
                      color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                    }}
                  >
                    {label}
                  </div>
                  <div
                    className="text-[11px] leading-none"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {desc}
                  </div>
                </div>
                {isActive && (
                  <div
                    className="absolute right-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-l"
                    style={{ background: "var(--accent)" }}
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="px-2 pb-3" style={{ borderTop: "1px solid var(--border-faint)" }}>
        {/* Database stats */}
        <div
          className="mx-1 px-3 py-2.5 rounded-xl mb-2 mt-3"
          style={{
            background: "linear-gradient(135deg, rgba(204,68,0,0.05), rgba(10,117,4,0.04))",
            border: "1px solid rgba(204,68,0,0.12)",
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className="w-3 h-3 shrink-0" style={{ color: "var(--accent-light)" }} />
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--accent-light)" }}>
              Acts Indexed
            </span>
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium" style={{ color: "var(--text-muted)" }}>IT Act 1961</span>
              <span className="text-[10px] font-mono" style={{ color: "#0a7504" }}>5,109 §</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium" style={{ color: "var(--text-muted)" }}>IT Act 2025</span>
              <span className="text-[10px] font-mono" style={{ color: "#cc4400" }}>2,812 §</span>
            </div>
          </div>
        </div>

        {/* Settings link */}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${isActive ? "nav-active" : ""}`
          }
          style={({ isActive }) =>
            isActive ? {} : { color: "var(--text-muted)" }
          }
        >
          {({ isActive }) => (
            <>
              <div
                className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 transition-all duration-200"
                style={{
                  background: isActive ? "#fff0e8" : "transparent",
                  border: isActive ? "1px solid rgba(204,68,0,0.2)" : "1px solid transparent",
                }}
              >
                <Settings
                  className="w-3.5 h-3.5"
                  style={{ color: isActive ? "var(--accent-light)" : "var(--text-muted)" }}
                />
              </div>
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

      {/* Footer */}
      <div
        className="px-4 py-2.5 text-center"
        style={{ borderTop: "1px solid var(--border-faint)" }}
      >
        <p className="text-[9px] tracking-widest uppercase font-medium" style={{ color: "var(--text-muted)" }}>
          Ministry of Finance · CBDT
        </p>
      </div>
    </aside>
  );
}

import { useState, useEffect } from "react";
import { PanelLeftClose, PanelLeft } from "lucide-react";
import { NAV_ITEMS, SIDEBAR_KEY } from "./navConfig";

export default function Sidebar({ page, onNavigate }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === "true");
  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, String(collapsed));
    document.documentElement.setAttribute("data-sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  return (
    <aside
      data-collapsed={collapsed}
      className="apw-rail"
      style={{ width: collapsed ? 64 : 240, background: "var(--bg-sidebar)",
               borderRight: "1px solid var(--border)", transition: "width 180ms",
               height: "100vh", position: "sticky", top: 0, flexShrink: 0,
               display: "flex", flexDirection: "column" }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px" }}>
        {!collapsed && <span style={{ fontFamily: "var(--font-display)", fontWeight: 700 }}>floww</span>}
        <button aria-label={collapsed ? "expand sidebar" : "collapse sidebar"}
                onClick={() => setCollapsed(c => !c)}
                style={{ background: "transparent", border: 0, color: "var(--text-dim)", cursor: "pointer" }}>
          {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
      <nav style={{ display: "flex", flexDirection: "column", gap: 2, padding: "4px 8px" }}>
        {NAV_ITEMS.map(item => {
          const active = page === item.id;
          return (
            <button key={item.id} onClick={() => onNavigate(item.id)}
              aria-current={active ? "page" : undefined}
              title={item.label}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
                       borderRadius: 8, border: "1px solid transparent", cursor: "pointer",
                       fontSize: 13, textAlign: "left",
                       color: active ? "var(--gold)" : "var(--text-dim)",
                       background: active ? "var(--gold-dim)" : "transparent",
                       borderColor: active ? "var(--gold-border)" : "transparent" }}>
              <span style={{ width: 18, textAlign: "center" }}>{item.label[0]}</span>
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

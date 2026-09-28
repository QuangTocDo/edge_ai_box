import {
  BarChart3,
  Camera,
  Clock,
  FileVideo2,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Radio,
  ShieldCheck,
  Sun,
  User,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const nav = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/jobs", label: "Video Jobs", icon: FileVideo2 },
  { to: "/cameras", label: "Live Cameras", icon: Radio },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];

export function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { user, isAdmin, logout } = useAuth();
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    return (localStorage.getItem("dashboard_theme") as "dark" | "light") || "dark";
  });
  const [timeStr, setTimeStr] = useState("");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dashboard_theme", theme);
  }, [theme]);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(
        now.toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">
            <Camera size={20} />
          </div>
          <div className="brand-text">
            <strong>SignalWatch AI</strong>
            <span>Traffic Vision Ops</span>
          </div>
          <button
            className="icon-button sidebar-close"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X size={19} />
          </button>
        </div>

        <nav className="main-nav">
          <span className="nav-label">Operations Console</span>
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="account-panel">
          <div className="account-row">
            <span
              className={`account-avatar ${
                isAdmin ? "account-avatar-admin" : ""
              }`}
            >
              {isAdmin ? <ShieldCheck size={16} /> : <User size={16} />}
            </span>
            <div className="account-meta">
              <strong>{user?.name ?? "Operator"}</strong>
              <span>
                {isAdmin ? "Super Administrator" : "Operator · Read-only"}
              </span>
            </div>
          </div>
          <button className="account-logout" onClick={logout}>
            <LogOut size={15} /> Sign out
          </button>
        </div>
      </aside>

      {open && (
        <button
          className="sidebar-backdrop"
          onClick={() => setOpen(false)}
          aria-label="Close navigation"
        />
      )}

      <div className="workspace">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>

          <div className="topbar-status">
            <span className="live-dot" />
            <span className="status-text">Vision Pipeline Operational</span>
          </div>

          <div className="topbar-right">
            {timeStr && (
              <div className="topbar-clock">
                <Clock size={14} />
                <span>{timeStr}</span>
              </div>
            )}

            <button
              className="theme-toggle-btn"
              onClick={toggleTheme}
              title={
                theme === "dark"
                  ? "Switch to Light Mode"
                  : "Switch to Dark Mode"
              }
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        <main>{children}</main>
      </div>
    </div>
  );
}

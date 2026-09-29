import {
  BarChart3,
  CarFront,
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
  { to: "/objects", label: "Vehicle Explorer", icon: CarFront },
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
      {/* Sidebar */}
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">
            <ShieldCheck size={22} />
          </div>
          <div className="brand-text">
            <strong>EdgeTraffic</strong>
            <span>Traffic Operations</span>
          </div>
          <button
            className="sidebar-close"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="main-nav">
          <span className="nav-label">Monitoring</span>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => (isActive ? "active" : "")}
                onClick={() => setOpen(false)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="account-panel">
          <div className="account-row">
            <div className={`account-avatar ${isAdmin ? "account-avatar-admin" : ""}`}>
              <User size={18} />
            </div>
            <div className="account-meta">
              <strong>{user?.name || "Operator"}</strong>
              <span>{isAdmin ? "Administrator" : "Standard Operator"}</span>
            </div>
          </div>
          <button className="account-logout" onClick={logout} title="Sign Out">
            <LogOut size={14} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Workspace */}
      <div className="workspace">
        <header className="topbar">
          <button
            className="mobile-menu"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>

          <div className="topbar-status">
            <span className="live-dot" />
            <span>EDGE AI ENGINE ACTIVE</span>
          </div>

          <div className="topbar-right">
            <div className="topbar-clock">
              <Clock size={13} />
              <span>{timeStr}</span>
            </div>

            <button
              className="theme-toggle-btn"
              onClick={toggleTheme}
              title={`Switch to ${theme === "dark" ? "Light" : "Dark"} mode`}
              aria-label="Toggle Theme"
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        <main>{children}</main>
      </div>

      {open && <button className="sidebar-backdrop" onClick={() => setOpen(false)} aria-label="Close overlay" />}
    </div>
  );
}

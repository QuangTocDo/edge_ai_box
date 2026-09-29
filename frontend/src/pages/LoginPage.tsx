import { Camera, Eye, EyeOff, Lock, ShieldCheck, User } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const DEMO_ACCOUNTS = [
  { label: "Administrator", username: "admin", password: "admin123", role: "Full control", icon: ShieldCheck },
  { label: "Operator", username: "user", password: "user123", role: "Read-only", icon: User },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  function quickFill(u: string, p: string) {
    setUsername(u);
    setPassword(p);
    setError("");
  }

  return (
    <div className="login-screen">
      <div className="login-bg" aria-hidden>
        <span className="login-blob login-blob-1" />
        <span className="login-blob login-blob-2" />
        <span className="login-grid" />
        <span className="login-scan" />
      </div>

      <div className="login-content">
        <section className="login-hero">
          <div className="login-brand">
            <div className="login-brand-mark"><Camera size={22} /></div>
            <div>
              <strong>EdgeTraffic</strong>
              <span>Traffic Vision Operations</span>
            </div>
          </div>
          <h1>Intelligent intersection<br />monitoring, in real time.</h1>
          <p>Vehicle detection, red-light & speed enforcement, and live camera review — all in one operations console.</p>
          <ul className="login-feature-list">
            <li><i /> Live RTSP & camera ingestion</li>
            <li><i /> Automated violation evidence</li>
            <li><i /> Role-based operator access</li>
          </ul>
        </section>

        <section className="login-card">
          <div className="login-card-head">
            <h2>Sign in</h2>
            <p>Use a demo account or your operator credentials.</p>
          </div>

          <form onSubmit={submit} className={`login-form ${error ? "login-shake" : ""}`}>
            <label className="login-field">
              <span>Username</span>
              <div className="login-input">
                <User size={16} />
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  autoComplete="username"
                  required
                />
              </div>
            </label>

            <label className="login-field">
              <span>Password</span>
              <div className="login-input">
                <Lock size={16} />
                <input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                />
                <button type="button" className="login-eye" onClick={() => setShow((v) => !v)} aria-label="Toggle password">
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>

            {error && <div className="login-error">{error}</div>}

            <button className="login-submit" type="submit" disabled={busy}>
              {busy ? <span className="login-spinner" /> : "Sign in"}
            </button>
          </form>

          <div className="login-demo">
            <span className="login-demo-label">Quick demo access</span>
            <div className="login-demo-grid">
              {DEMO_ACCOUNTS.map(({ label, username: u, password: p, role, icon: Icon }) => (
                <button key={u} type="button" className="login-demo-card" onClick={() => quickFill(u, p)}>
                  <span className="login-demo-icon"><Icon size={17} /></span>
                  <strong>{label}</strong>
                  <small>{role}</small>
                  <code>{u} / {p}</code>
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

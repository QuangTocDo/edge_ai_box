import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { api, setAuthToken } from "../services/api";

export interface AuthUser {
  username: string;
  name: string;
  role: "admin" | "viewer" | string;
}

interface AuthState {
  user: AuthUser | null;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const STORAGE_KEY = "signalwatch.auth";

const AuthContext = createContext<AuthState | null>(null);

function readStored(): { token: string; user: AuthUser } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const stored = readStored();
  if (stored) setAuthToken(stored.token);
  const [user, setUser] = useState<AuthUser | null>(stored?.user ?? null);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password);
    const nextUser: AuthUser = { username: res.username, name: res.name, role: res.role };
    setAuthToken(res.token);
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: res.token, user: nextUser }));
    setUser(nextUser);
  }, []);

  const logout = useCallback(() => {
    api.logout().catch(() => undefined);
    setAuthToken(null);
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, isAdmin: user?.role === "admin", login, logout }),
    [user, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

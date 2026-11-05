"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, clearTokens, hasSession, onSessionExpired, saveTokens } from "./api";
import type { AuthResponse, User } from "./types";

type AuthState = {
  user: User | null;
  checking: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; username: string; full_name: string; password: string }) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      let restored: User | null = null;
      if (hasSession()) {
        try {
          restored = await api.me();
        } catch {
          // Expired or unreachable: fall through to the login page.
        }
      }
      if (active) {
        setUser(restored);
        setChecking(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => onSessionExpired(() => setUser(null)), []);

  const startSession = useCallback((session: AuthResponse) => {
    saveTokens(session.access, session.refresh);
    setUser(session.user);
  }, []);

  const login = useCallback<AuthState["login"]>(
    async (email, password) => startSession(await api.login(email, password)),
    [startSession],
  );

  const register = useCallback<AuthState["register"]>(
    async (payload) => startSession(await api.register(payload)),
    [startSession],
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, checking, login, register, logout }),
    [user, checking, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

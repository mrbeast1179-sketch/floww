import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { BACKEND_BASE } from '../config/api';

const AUTH_KEY = 'ap.authToken';
const AUTH_USER_KEY = 'ap.authUser';

const AuthContext = createContext({
  token: null,
  user: null,
  tier: null,
  login: async () => {},
  logout: () => {},
  isAuthenticated: false,
});

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => {
    try { return localStorage.getItem(AUTH_KEY); } catch { return null; }
  });
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem(AUTH_USER_KEY) || 'null'); } catch { return null; }
  });

  const login = useCallback(async (email, tier) => {
    // Use local backend for dev-token (not the real AlphaPod API)
    const base = BACKEND_BASE;
    const res = await axios.post(
      `${base}/api/auth/dev-token`,
      { email, tier }
    );
    const { access_token, subscriber } = res.data;
    localStorage.setItem(AUTH_KEY, access_token);
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(subscriber));
    setToken(access_token);
    setUser(subscriber);
    return { token: access_token, user: subscriber };
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Refresh token if expired (check on mount)
  useEffect(() => {
    if (token && user) {
      // Token is valid, set axios default header
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    }
  }, [token, user]);

  const isAuthenticated = !!token;

  return (
    <AuthContext.Provider value={{ token, user, tier: user?.tier, login, logout, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default AuthContext;

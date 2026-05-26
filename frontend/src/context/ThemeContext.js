import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { BACKEND_URL } from "../config/api";

const ThemeContext = createContext({
  theme: 'dark',
  toggleTheme: () => {},
  setTheme: () => {},
});

const THEME_KEY = 'floww_theme';
const THEME_MEDIA = '(prefers-color-scheme: light)';

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    // 1. Check localStorage first
    try {
      const stored = localStorage.getItem(THEME_KEY);
      if (stored === 'dark' || stored === 'light') return stored;
    } catch { /* noop */ }
    // 2. Check system preference
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia(THEME_MEDIA).matches ? 'light' : 'dark';
    }
    return 'dark';
  });

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* noop */ }
  }, [theme]);

  // Listen for system theme changes
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(THEME_MEDIA);
    const handler = (e) => {
      // Only auto-switch if user hasn't explicitly set a preference
      try {
        if (!localStorage.getItem(THEME_KEY)) {
          setThemeState(e.matches ? 'light' : 'dark');
        }
      } catch { /* noop */ }
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  // Sync theme to backend for cross-device persistence
  useEffect(() => {
    const syncToBackend = async () => {
      try {
        // BACKEND_URL imported from config/api.js
        await fetch(`${BACKEND_URL}/api/preferences/theme`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme }),
        });
      } catch { /* noop - backend may not be available */ }
    };
    // Debounce backend sync
    const id = setTimeout(syncToBackend, 1000);
    return () => clearTimeout(id);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState(prev => prev === 'dark' ? 'light' : 'dark');
  }, []);

  const setTheme = useCallback((t) => {
    if (t === 'dark' || t === 'light') setThemeState(t);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

export default ThemeContext;

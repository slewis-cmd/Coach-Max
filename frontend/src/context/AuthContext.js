import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Session token management
const TOKEN_KEY = 'thinkific_session_token';

const getStoredToken = () => localStorage.getItem(TOKEN_KEY);
const storeToken = (token) => localStorage.setItem(TOKEN_KEY, token);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// Axios interceptor to include session token in all requests
axios.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
      return;
    }

    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const response = await axios.get(`${API_URL}/api/auth/me`);
      setUser(response.data);
    } catch (error) {
      setUser(null);
      clearToken();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const logout = async () => {
    try {
      await axios.post(`${API_URL}/api/auth/logout`, {});
    } catch (_err) {
      // Logout API failure is non-critical
    }
    setUser(null);
    clearToken();
  };

  const saveSession = (token) => {
    storeToken(token);
  };

  const setRole = async (role) => {
    try {
      await axios.post(`${API_URL}/api/auth/set-role`, { role });
      setUser(prev => ({ ...prev, role }));
      return true;
    } catch (error) {
      return false;
    }
  };

  const value = {
    user,
    setUser,
    loading,
    login,
    logout,
    setRole,
    checkAuth,
    saveSession,
    isAuthenticated: !!user,
    isSuperAdmin: user?.role === 'super_admin',
    isInstructor: user?.role === 'instructor' || user?.role === 'super_admin',
    isStudent: user?.role === 'student'
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const DEFAULT_BRANDING = {
  app_name: 'The Boost Pad',
  ai_persona_name: 'Coach Max',
  primary_color: '#22438E',
  logo_url: '',
  favicon_url: '',
  email_sender_name: 'The Boost Pad',
  tagline: 'AI-powered learning coach',
  ai_system_prompt: '',
};

const BrandingContext = createContext({ branding: DEFAULT_BRANDING, refresh: () => {} });

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);

  const refresh = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/settings/branding`);
      if (res.data && typeof res.data === 'object') {
        setBranding({ ...DEFAULT_BRANDING, ...res.data });
      }
    } catch (err) {
      // Public endpoint — fall back to defaults but log for observability
      console.warn('Failed to load branding, using defaults:', err?.message || err);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Apply primary color as a CSS custom property so components can read it
  useEffect(() => {
    if (branding.primary_color) {
      document.documentElement.style.setProperty('--brand-primary', branding.primary_color);
    }
    if (branding.favicon_url) {
      let link = document.querySelector("link[rel='icon']");
      if (!link) {
        link = document.createElement('link');
        link.rel = 'icon';
        document.head.appendChild(link);
      }
      link.href = branding.favicon_url;
    }
    if (branding.app_name) {
      document.title = branding.app_name;
    }
  }, [branding]);

  return (
    <BrandingContext.Provider value={{ branding, refresh }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  return useContext(BrandingContext);
}

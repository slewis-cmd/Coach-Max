import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser, saveSession, login } = useAuth();
  const hasProcessed = useRef(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      const hash = location.hash;
      const sessionIdMatch = hash.match(/session_id=([^&]+)/);
      
      if (!sessionIdMatch) {
        navigate('/');
        return;
      }

      const sessionId = sessionIdMatch[1];

      // Clear the hash immediately to prevent re-processing
      window.history.replaceState(null, '', window.location.pathname);

      // Try up to 2 times with a short delay
      for (let attempt = 1; attempt <= 2; attempt++) {
        try {
          const response = await axios.post(
            `${API_URL}/api/auth/session`,
            { session_id: sessionId }
          );

          if (response.data.session_token) {
            saveSession(response.data.session_token);
          }

          setUser(response.data.user);
          
          if (!response.data.user?.role) {
            navigate('/role-selection', { replace: true });
          } else {
            navigate('/dashboard', { replace: true });
          }
          return;
        } catch (err) {
          if (attempt < 2) {
            await new Promise(r => setTimeout(r, 1000));
          }
        }
      }

      // Both attempts failed
      setError('Sign in failed. Please try again.');
    };

    processAuth();
  }, [location, navigate, setUser, saveSession]);

  if (error) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="text-center max-w-sm mx-auto px-4">
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-red-600 text-xl">!</span>
          </div>
          <p className="text-[#000000] font-medium mb-2">Sign In Failed</p>
          <p className="text-sm text-[#333333] mb-6">{error}</p>
          <Button
            onClick={login}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
            data-testid="retry-sign-in-btn"
          >
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-[#333333]">Signing you in...</p>
      </div>
    </div>
  );
}

import React, { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      const hash = location.hash;
      const sessionIdMatch = hash.match(/session_id=([^&]+)/);
      
      if (!sessionIdMatch) {
        console.error('No session_id found in hash');
        navigate('/');
        return;
      }

      const sessionId = sessionIdMatch[1];
      console.log('Processing auth with session_id:', sessionId.substring(0, 10) + '...');

      try {
        const response = await axios.post(
          `${API_URL}/api/auth/session`,
          { session_id: sessionId },
          { withCredentials: true }
        );

        console.log('Auth response:', { 
          user: response.data.user?.email, 
          role: response.data.user?.role,
          is_new_user: response.data.is_new_user 
        });

        setUser(response.data.user);
        
        // Clear hash
        window.history.replaceState(null, '', window.location.pathname);
        
        // Redirect based on whether user has a role
        if (!response.data.user?.role) {
          // New user or user without role - go to role selection
          navigate('/role-selection', { replace: true });
        } else if (response.data.user.role === 'instructor') {
          navigate('/dashboard', { replace: true });
        } else {
          navigate('/dashboard', { replace: true });
        }
      } catch (error) {
        console.error('Auth callback error:', error.response?.data || error.message);
        navigate('/');
      }
    };

    processAuth();
  }, [location, navigate, setUser]);

  return (
    <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-[#5A5A5A]">Signing you in...</p>
      </div>
    </div>
  );
}

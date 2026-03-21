import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { BookOpen, Users, ArrowRight, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function InvitePage() {
  const { code } = useParams();
  const { user, login, isAuthenticated, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [cohortInfo, setCohortInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState(null);
  const [joined, setJoined] = useState(false);

  useEffect(() => {
    const fetchInvite = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/invite/${code}`);
        setCohortInfo(res.data);
      } catch (err) {
        setError('This invite link is invalid or has expired.');
      } finally {
        setLoading(false);
      }
    };
    fetchInvite();
  }, [code]);

  // Auto-join after authentication
  useEffect(() => {
    if (!authLoading && isAuthenticated && cohortInfo && !joined && !joining) {
      handleJoin();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, isAuthenticated, cohortInfo]);

  const handleJoin = async () => {
    setJoining(true);
    try {
      const res = await axios.post(`${API_URL}/api/invite/${code}/join`);
      setJoined(true);
      if (res.data.already_enrolled) {
        toast.success("You're already enrolled in this cohort");
      } else {
        toast.success(res.data.message);
      }
      setTimeout(() => navigate('/dashboard', { replace: true }), 1500);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to join cohort');
      setJoining(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center px-4">
        <Card className="max-w-md w-full bg-white border-[#E5E5E5]">
          <CardContent className="p-8 text-center">
            <div className="w-16 h-16 bg-[#FEE2E2] rounded-2xl flex items-center justify-center mx-auto mb-4">
              <BookOpen className="w-8 h-8 text-[#991B1B]" />
            </div>
            <h2 className="text-2xl font-light text-[#1A1A1A] mb-2">Invalid Invite</h2>
            <p className="text-[#5A5A5A] mb-6">{error}</p>
            <Button onClick={() => navigate('/')} className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg">
              Go to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center px-4" data-testid="invite-page">
      <Card className="max-w-md w-full bg-white border-[#E5E5E5] shadow-lg">
        <CardContent className="p-8 text-center">
          {joined ? (
            <>
              <div className="w-16 h-16 bg-[#D1FAE5] rounded-2xl flex items-center justify-center mx-auto mb-4 animate-fade-in">
                <CheckCircle className="w-8 h-8 text-[#065F46]" />
              </div>
              <h2 className="text-2xl font-light text-[#1A1A1A] mb-2">You're In!</h2>
              <p className="text-[#5A5A5A]">Redirecting to your dashboard...</p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 bg-[#F2F0ED] rounded-2xl flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8 text-[#1A1A1A]" />
              </div>
              <h2 className="text-2xl font-light text-[#1A1A1A] mb-1">
                {cohortInfo.name}
              </h2>
              {cohortInfo.description && (
                <p className="text-[#5A5A5A] mb-4">{cohortInfo.description}</p>
              )}
              <div className="flex items-center justify-center gap-4 text-sm text-[#888] mb-6">
                <span className="flex items-center gap-1">
                  <Users className="w-4 h-4" />
                  {cohortInfo.student_count} students
                </span>
                <span>by {cohortInfo.instructor_name}</span>
              </div>

              {isAuthenticated ? (
                <Button
                  onClick={handleJoin}
                  disabled={joining}
                  className="w-full bg-[#065F46] text-white hover:bg-[#064E3B] rounded-lg py-3 text-base"
                  data-testid="join-cohort-btn"
                >
                  {joining ? 'Joining...' : (
                    <>
                      Join This Course
                      <ArrowRight className="w-4 h-4 ml-2" />
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  onClick={login}
                  className="w-full bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg py-3 text-base"
                  data-testid="sign-in-to-join-btn"
                >
                  Sign In to Join
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              )}

              <p className="text-xs text-[#888] mt-4">
                You'll be enrolled as a student in this course
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

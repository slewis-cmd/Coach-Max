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
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center px-4">
        <Card className="max-w-md w-full bg-white border-[#B8D4E8]">
          <CardContent className="p-8 text-center">
            <div className="w-16 h-16 bg-[#FEE2E2] rounded-2xl flex items-center justify-center mx-auto mb-4">
              <BookOpen className="w-8 h-8 text-[#991B1B]" />
            </div>
            <h2 className="text-2xl font-light text-[#000000] mb-2">Invalid Invite</h2>
            <p className="text-[#333333] mb-6">{error}</p>
            <Button onClick={() => navigate('/')} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">
              Go to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center px-4" data-testid="invite-page">
      <Card className="max-w-md w-full bg-white border-[#B8D4E8] shadow-lg">
        <CardContent className="p-8 text-center">
          {joined ? (
            <>
              <div className="w-16 h-16 bg-[#E1F0FF] rounded-2xl flex items-center justify-center mx-auto mb-4 animate-fade-in">
                <CheckCircle className="w-8 h-8 text-[#22438E]" />
              </div>
              <h2 className="text-2xl font-light text-[#000000] mb-2">You're In!</h2>
              <p className="text-[#333333]">Redirecting to your dashboard...</p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 bg-[#D0E6F9] rounded-2xl flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8 text-[#000000]" />
              </div>
              <h2 className="text-2xl font-light text-[#000000] mb-1">
                {cohortInfo.name}
              </h2>
              {cohortInfo.description && (
                <p className="text-[#333333] mb-4">{cohortInfo.description}</p>
              )}
              <div className="flex items-center justify-center gap-4 text-sm text-[#666666] mb-6">
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
                  className="w-full bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg py-3 text-base"
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
                  className="w-full bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg py-3 text-base"
                  data-testid="sign-in-to-join-btn"
                >
                  Sign In to Join
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              )}

              <p className="text-xs text-[#666666] mt-4">
                You'll be enrolled as a student in this course
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

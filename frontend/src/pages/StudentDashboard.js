import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { 
  BookOpen, 
  FileText, 
  LogOut,
  Upload,
  CheckCircle,
  Clock,
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function StudentDashboard() {
  const { user, logout, loading, isAuthenticated, isStudent } = useAuth();
  const navigate = useNavigate();
  const [cohorts, setCohorts] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/');
    } else if (!loading && user?.role === 'instructor') {
      navigate('/dashboard');
    }
  }, [loading, isAuthenticated, user, navigate]);

  useEffect(() => {
    if (isStudent) {
      fetchData();
    }
  }, [isStudent]);

  const fetchData = async () => {
    try {
      const [cohortsRes, submissionsRes] = await Promise.all([
        axios.get(`${API_URL}/api/cohorts`, { withCredentials: true }),
        axios.get(`${API_URL}/api/submissions`, { withCredentials: true })
      ]);
      setCohorts(cohortsRes.data);
      setSubmissions(submissionsRes.data);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const reviewedCount = submissions.filter(s => s.status === 'reviewed').length;
  const totalSubmissions = submissions.length;
  const progressPercent = totalSubmissions > 0 ? (reviewedCount / totalSubmissions) * 100 : 0;

  if (loading || loadingData) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="student-dashboard">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 bottom-0 w-64 bg-[#F2F0ED] border-r border-[#E5E5E5] p-6 hidden md:block">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-8 h-8 bg-[#1A1A1A] rounded-lg flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-[#1A1A1A]">ThinkificAI</span>
        </div>

        <nav className="space-y-2">
          <Link 
            to="/dashboard"
            className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white text-[#1A1A1A] font-medium"
          >
            <FileText className="w-5 h-5" />
            My Learning
          </Link>
          <Link 
            to="/my-submissions"
            className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#5A5A5A] hover:bg-white hover:text-[#1A1A1A] transition-colors"
          >
            <Upload className="w-5 h-5" />
            My Submissions
          </Link>
        </nav>

        <div className="absolute bottom-6 left-6 right-6">
          <div className="flex items-center gap-3 mb-4">
            {user?.picture && (
              <img src={user.picture} alt={user.name} className="w-10 h-10 rounded-full" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[#1A1A1A] truncate">{user?.name}</p>
              <p className="text-xs text-[#888] truncate">{user?.email}</p>
            </div>
          </div>
          <Button 
            variant="ghost" 
            className="w-full justify-start text-[#5A5A5A] hover:text-[#1A1A1A]"
            onClick={handleLogout}
            data-testid="logout-btn"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Sign Out
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="md:ml-64 p-6 md:p-8">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#1A1A1A] rounded-lg flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold">ThinkificAI</span>
          </div>
          <Button variant="ghost" size="icon" onClick={handleLogout}>
            <LogOut className="w-5 h-5" />
          </Button>
        </div>

        {/* Header */}
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl md:text-4xl font-light tracking-tight text-[#1A1A1A] mb-2">
            Hello, {user?.name?.split(' ')[0]}!
          </h1>
          <p className="text-[#5A5A5A]">
            Keep up the great work on your learning journey
          </p>
        </div>

        {/* Progress Card */}
        {totalSubmissions > 0 && (
          <Card className="bg-white border-[#E5E5E5] mb-8 animate-fade-in">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-medium text-[#1A1A1A]">Your Progress</h3>
                  <p className="text-sm text-[#888]">{reviewedCount} of {totalSubmissions} submissions reviewed</p>
                </div>
                <div className="w-12 h-12 bg-[#D1FAE5] rounded-full flex items-center justify-center">
                  <Sparkles className="w-6 h-6 text-[#065F46]" />
                </div>
              </div>
              <Progress value={progressPercent} className="h-2" />
            </CardContent>
          </Card>
        )}

        {/* Cohorts */}
        <div className="mb-8">
          <h2 className="text-2xl font-light text-[#1A1A1A] mb-4">My Courses</h2>
          
          {cohorts.length === 0 ? (
            <Card className="bg-white border-[#E5E5E5] border-dashed">
              <CardContent className="p-12 text-center">
                <BookOpen className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No courses yet</h3>
                <p className="text-[#5A5A5A]">
                  Your instructor will add you to a cohort soon
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid md:grid-cols-2 gap-4">
              {cohorts.map((cohort) => (
                <Card 
                  key={cohort.cohort_id}
                  className="bg-white border-[#E5E5E5] hover:shadow-md transition-shadow cursor-pointer group"
                  onClick={() => navigate(`/cohort/${cohort.cohort_id}`)}
                  data-testid={`cohort-card-${cohort.cohort_id}`}
                >
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg font-normal flex items-center justify-between">
                      {cohort.name}
                      <ChevronRight className="w-5 h-5 text-[#C4C4C4] group-hover:text-[#1A1A1A] transition-colors" />
                    </CardTitle>
                    <CardDescription>{cohort.description || 'Course materials'}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button 
                      size="sm" 
                      className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                    >
                      View Materials
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Recent Feedback */}
        {submissions.filter(s => s.status === 'reviewed').length > 0 && (
          <div>
            <h2 className="text-2xl font-light text-[#1A1A1A] mb-4">Recent Feedback</h2>
            <div className="space-y-4">
              {submissions
                .filter(s => s.status === 'reviewed')
                .slice(0, 3)
                .map((sub) => (
                  <Card 
                    key={sub.submission_id}
                    className="bg-[#F0FDF4] border-[#BBF7D0] cursor-pointer hover:shadow-sm transition-shadow"
                    onClick={() => navigate(`/submission/${sub.submission_id}`)}
                    data-testid={`feedback-${sub.submission_id}`}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 bg-[#D1FAE5] rounded-full flex items-center justify-center flex-shrink-0">
                          <CheckCircle className="w-5 h-5 text-[#065F46]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-[#166534] mb-1">
                            {sub.material?.title || 'Homework'} - Week {sub.material?.week_number || '?'}
                          </p>
                          <p className="text-sm text-[#065F46] line-clamp-2 feedback-letter">
                            {sub.ai_feedback?.substring(0, 150)}...
                          </p>
                        </div>
                        <ChevronRight className="w-5 h-5 text-[#065F46] flex-shrink-0" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
            </div>
          </div>
        )}

        {/* Pending Submissions */}
        {submissions.filter(s => s.status === 'pending').length > 0 && (
          <div className="mt-8">
            <h2 className="text-2xl font-light text-[#1A1A1A] mb-4">Awaiting Review</h2>
            <div className="space-y-3">
              {submissions
                .filter(s => s.status === 'pending')
                .map((sub) => (
                  <Card 
                    key={sub.submission_id}
                    className="bg-white border-[#E5E5E5]"
                    data-testid={`pending-${sub.submission_id}`}
                  >
                    <CardContent className="p-4 flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#FDE047] rounded-full flex items-center justify-center">
                        <Clock className="w-5 h-5 text-[#1A1A1A]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#1A1A1A]">
                          {sub.material?.title || 'Homework'}
                        </p>
                        <p className="text-sm text-[#888]">
                          Submitted • Awaiting instructor review
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

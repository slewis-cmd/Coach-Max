import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { 
  BookOpen, 
  ArrowLeft,
  Users,
  BarChart3,
  TrendingUp,
  CheckCircle,
  Clock,
  User
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function ProgressTracking() {
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [cohorts, setCohorts] = useState([]);
  const [selectedCohort, setSelectedCohort] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!authLoading && !isInstructor) {
      navigate('/dashboard');
    }
  }, [authLoading, isInstructor, navigate]);

  useEffect(() => {
    if (isInstructor) {
      fetchCohorts();
    }
  }, [isInstructor]);

  useEffect(() => {
    if (selectedCohort) {
      fetchCohortAnalytics(selectedCohort);
    }
  }, [selectedCohort]);

  const fetchCohorts = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/cohorts`, { withCredentials: true });
      setCohorts(res.data);
      if (res.data.length > 0) {
        setSelectedCohort(res.data[0].cohort_id);
      }
    } catch (error) {
      toast.error('Failed to load cohorts');
    } finally {
      setLoading(false);
    }
  };

  const fetchCohortAnalytics = async (cohortId) => {
    try {
      const res = await axios.get(`${API_URL}/api/analytics/cohort/${cohortId}`, { withCredentials: true });
      setAnalytics(res.data);
    } catch (error) {
      toast.error('Failed to load analytics');
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="progress-tracking">
      {/* Header */}
      <header className="bg-white border-b border-[#E5E5E5] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/dashboard"
              className="p-2 hover:bg-[#F2F0ED] rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-[#5A5A5A]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#1A1A1A]">Progress Tracking</h1>
              <p className="text-sm text-[#888]">Monitor student engagement and completion</p>
            </div>
          </div>
          
          {cohorts.length > 0 && (
            <Select value={selectedCohort} onValueChange={setSelectedCohort}>
              <SelectTrigger className="w-[250px]">
                <SelectValue placeholder="Select cohort" />
              </SelectTrigger>
              <SelectContent>
                {cohorts.map(cohort => (
                  <SelectItem key={cohort.cohort_id} value={cohort.cohort_id}>
                    {cohort.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {!analytics ? (
          <Card className="bg-white border-[#E5E5E5] border-dashed">
            <CardContent className="p-12 text-center">
              <BarChart3 className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No data available</h3>
              <p className="text-[#5A5A5A]">
                {cohorts.length === 0 
                  ? 'Create a cohort and add students to see progress'
                  : 'Select a cohort to view progress'}
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Overview Stats */}
            <div className="grid md:grid-cols-4 gap-4 mb-8">
              <Card className="bg-white border-[#E5E5E5]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-4 h-4 text-[#888]" />
                    <p className="text-sm text-[#888]">Students</p>
                  </div>
                  <p className="text-3xl font-light text-[#1A1A1A]">{analytics.cohort.total_students}</p>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#E5E5E5]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="w-4 h-4 text-[#888]" />
                    <p className="text-sm text-[#888]">Assignments</p>
                  </div>
                  <p className="text-3xl font-light text-[#1A1A1A]">{analytics.cohort.total_homework}</p>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#E5E5E5]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="w-4 h-4 text-[#065F46]" />
                    <p className="text-sm text-[#888]">Completed</p>
                  </div>
                  <p className="text-3xl font-light text-[#065F46]">{analytics.overview.completed_reviews}</p>
                </CardContent>
              </Card>
              <Card className="bg-[#D1FAE5] border-[#BBF7D0]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-4 h-4 text-[#065F46]" />
                    <p className="text-sm text-[#065F46]">Avg Completion</p>
                  </div>
                  <p className="text-3xl font-light text-[#065F46]">{analytics.overview.avg_completion_rate}%</p>
                </CardContent>
              </Card>
            </div>

            {/* Weekly Progress */}
            {analytics.weekly_progress?.length > 0 && (
              <Card className="bg-white border-[#E5E5E5] mb-8">
                <CardHeader>
                  <CardTitle className="text-lg font-normal">Weekly Progress</CardTitle>
                  <CardDescription>Submissions and reviews by week</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {analytics.weekly_progress.sort((a, b) => a.week - b.week).map((week) => {
                      const completionRate = week.assignments > 0 && analytics.cohort.total_students > 0
                        ? Math.round((week.submitted / (week.assignments * analytics.cohort.total_students)) * 100)
                        : 0;
                      return (
                        <div key={week.week} className="flex items-center gap-4">
                          <div className="w-20 flex-shrink-0">
                            <p className="text-sm font-medium text-[#1A1A1A]">Week {week.week}</p>
                            <p className="text-xs text-[#888]">{week.assignments} assignment{week.assignments !== 1 ? 's' : ''}</p>
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-[#888]">{week.submitted} submitted</span>
                              <span className="text-xs text-[#065F46]">{week.reviewed} reviewed</span>
                            </div>
                            <Progress value={completionRate} className="h-2" />
                          </div>
                          <div className="w-16 text-right">
                            <span className="text-sm font-medium text-[#1A1A1A]">{completionRate}%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Student Progress */}
            <Card className="bg-white border-[#E5E5E5]">
              <CardHeader>
                <CardTitle className="text-lg font-normal">Student Progress</CardTitle>
                <CardDescription>Individual completion rates and engagement</CardDescription>
              </CardHeader>
              <CardContent>
                {analytics.student_progress?.length === 0 ? (
                  <div className="text-center py-8">
                    <Users className="w-8 h-8 text-[#C4C4C4] mx-auto mb-2" />
                    <p className="text-[#888]">No students in this cohort</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {analytics.student_progress.map((student, index) => (
                      <div key={student.user_id} className="flex items-center gap-4 p-3 rounded-lg hover:bg-[#F9F8F6] transition-colors">
                        <div className="w-8 text-center text-sm text-[#888]">
                          {index + 1}
                        </div>
                        <div className="w-10 h-10 flex-shrink-0">
                          {student.picture ? (
                            <img src={student.picture} alt={student.name} className="w-10 h-10 rounded-full" />
                          ) : (
                            <div className="w-10 h-10 bg-[#F2F0ED] rounded-full flex items-center justify-center">
                              <User className="w-5 h-5 text-[#888]" />
                            </div>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-[#1A1A1A] truncate">{student.name}</p>
                          <p className="text-xs text-[#888] truncate">{student.email}</p>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="text-sm text-[#1A1A1A]">{student.submissions} submitted</p>
                            <p className="text-xs text-[#888]">{student.completed} reviewed</p>
                          </div>
                          <div className="w-32">
                            <Progress value={student.completion_rate} className="h-2" />
                          </div>
                          <div className="w-16 text-right">
                            <span className={`text-sm font-medium ${
                              student.completion_rate >= 80 ? 'text-[#065F46]' :
                              student.completion_rate >= 50 ? 'text-[#854D0E]' :
                              'text-red-600'
                            }`}>
                              {student.completion_rate}%
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}

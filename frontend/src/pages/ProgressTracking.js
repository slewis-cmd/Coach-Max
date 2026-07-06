import React, { useState, useEffect, useMemo, useCallback } from 'react';
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
  User,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  MessageSquare,
  AlertCircle
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const downloadFile = async (url, filename) => {
  const token = localStorage.getItem('thinkific_session_token');
  if (!token) { toast.error('Please log in'); return; }
  const separator = url.includes('?') ? '&' : '?';
  try {
    const response = await fetch(`${url}${separator}token=${encodeURIComponent(token)}`);
    if (!response.ok) throw new Error('Download failed');
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename || 'download';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
  } catch (err) {
    toast.error('Failed to download file');
  }
};

function getCompletionColorClass(rate) {
  if (rate >= 80) return 'text-[#22438E]';
  if (rate >= 50) return 'text-[#1A75BA]';
  return 'text-red-600';
}

function StudentWeekRow({ week }) {
  const [expanded, setExpanded] = useState(false);

  const statusColor = {
    sent: 'bg-[#E1F0FF] text-[#22438E]',
    draft: 'bg-[#E1F0FF] text-[#6B21A8]',
    pending: 'bg-[#DBEAFE] text-[#1E40AF]',
    not_submitted: 'bg-[#F3F4F6] text-[#6B7280]',
  };
  const statusLabel = {
    sent: 'Reviewed',
    draft: 'Draft Feedback',
    pending: 'Pending Review',
    not_submitted: 'Not Submitted',
  };

  const feedback = week.instructor_feedback || week.ai_feedback;

  return (
    <div className="border border-[#B8D4E8] rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-[#E1F0FF] transition-colors"
        onClick={() => setExpanded(!expanded)}
        data-testid={`week-row-${week.week_number}-${week.studentId}`}
      >
        <div className="w-16 flex-shrink-0">
          <span className="text-xs font-medium text-[#333333]">Week {week.week_number}</span>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-[#000000] truncate">{week.homework_title || `Week ${week.week_number} Homework`}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${statusColor[week.status] || statusColor.not_submitted}`}>
          {statusLabel[week.status] || week.status}
        </span>
        {expanded ? <ChevronUp className="w-4 h-4 text-[#666666]" /> : <ChevronDown className="w-4 h-4 text-[#666666]" />}
      </div>

      {expanded && (
        <div className="border-t border-[#B8D4E8] px-3 py-3 bg-[#FAFAF9] space-y-3" data-testid={`week-detail-${week.week_number}-${week.studentId}`}>
          {/* Submitted File */}
          {week.submission_id ? (
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#333333] flex-shrink-0" />
              <span className="text-sm text-[#000000] truncate flex-1">{week.file_name}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  downloadFile(
                    `${API_URL}/api/submissions/${week.submission_id}/download`,
                    week.file_name
                  );
                }}
                className="text-[#22438E] hover:text-[#1A3A7A] p-1"
                title="Download submission"
                data-testid={`download-week-${week.week_number}-${week.studentId}`}
              >
                <Download className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-[#666666]">
              <AlertCircle className="w-4 h-4" />
              <span className="text-sm">No homework submitted yet</span>
            </div>
          )}

          {/* AI / Instructor Feedback */}
          {feedback ? (
            <div className="bg-white border border-[#B8D4E8] rounded-lg p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <MessageSquare className="w-3.5 h-3.5 text-[#22438E]" />
                <span className="text-xs font-medium text-[#22438E]">
                  {week.instructor_feedback ? 'Instructor Feedback' : 'AI Feedback'}
                </span>
              </div>
              <p className="text-sm text-[#374151] whitespace-pre-wrap leading-relaxed">{feedback}</p>
            </div>
          ) : week.submission_id ? (
            <div className="flex items-center gap-2 text-[#666666]">
              <Clock className="w-4 h-4" />
              <span className="text-sm">Awaiting AI review</span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function ProgressTracking() {
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [cohorts, setCohorts] = useState([]);
  const [selectedCohort, setSelectedCohort] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedStudents, setExpandedStudents] = useState({});

  useEffect(() => {
    if (!authLoading && !isInstructor) {
      navigate('/dashboard');
    }
  }, [authLoading, isInstructor, navigate]);

  const fetchCohorts = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/cohorts`);
      setCohorts(res.data);
      if (res.data.length > 0) {
        setSelectedCohort(res.data[0].cohort_id);
      }
    } catch (error) {
      toast.error('Failed to load cohorts');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCohortAnalytics = useCallback(async (cohortId) => {
    try {
      const res = await axios.get(`${API_URL}/api/analytics/cohort/${cohortId}`);
      setAnalytics(res.data);
    } catch (error) {
      toast.error('Failed to load analytics');
    }
  }, []);

  useEffect(() => {
    if (isInstructor) {
      fetchCohorts();
    }
  }, [isInstructor, fetchCohorts]);

  useEffect(() => {
    if (selectedCohort) {
      fetchCohortAnalytics(selectedCohort);
    }
  }, [selectedCohort, fetchCohortAnalytics]);

  const toggleStudent = (userId) => {
    setExpandedStudents(prev => ({ ...prev, [userId]: !prev[userId] }));
  };

  // Memoize weekly progress sort (avoids re-sorting + prevents in-place mutation of analytics state)
  const sortedWeeklyProgress = useMemo(() => {
    if (!analytics?.weekly_progress) return [];
    return [...analytics.weekly_progress].sort((a, b) => a.week - b.week);
  }, [analytics?.weekly_progress]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="progress-tracking">
      {/* Header */}
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/dashboard"
              className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-[#333333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000000]">Progress Tracking</h1>
              <p className="text-sm text-[#666666]">Monitor student engagement and completion</p>
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
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <BarChart3 className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#000000] mb-2">No data available</h3>
              <p className="text-[#333333]">
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
              <Card className="bg-white border-[#B8D4E8]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-4 h-4 text-[#666666]" />
                    <p className="text-sm text-[#666666]">Students</p>
                  </div>
                  <p className="text-3xl font-light text-[#000000]">{analytics.cohort.total_students}</p>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#B8D4E8]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="w-4 h-4 text-[#666666]" />
                    <p className="text-sm text-[#666666]">Assignments</p>
                  </div>
                  <p className="text-3xl font-light text-[#000000]">{analytics.cohort.total_homework}</p>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#B8D4E8]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="w-4 h-4 text-[#22438E]" />
                    <p className="text-sm text-[#666666]">Completed</p>
                  </div>
                  <p className="text-3xl font-light text-[#22438E]">{analytics.overview.completed_reviews}</p>
                </CardContent>
              </Card>
              <Card className="bg-[#E1F0FF] border-[#B8D4E8]">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-4 h-4 text-[#22438E]" />
                    <p className="text-sm text-[#22438E]">Avg Completion</p>
                  </div>
                  <p className="text-3xl font-light text-[#22438E]">{analytics.overview.avg_completion_rate}%</p>
                </CardContent>
              </Card>
            </div>

            {/* Weekly Progress */}
            {analytics.weekly_progress?.length > 0 && (
              <Card className="bg-white border-[#B8D4E8] mb-8">
                <CardHeader>
                  <CardTitle className="text-lg font-normal">Weekly Progress</CardTitle>
                  <CardDescription>Submissions and reviews by week</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {sortedWeeklyProgress.map((week) => {
                      const completionRate = week.assignments > 0 && analytics.cohort.total_students > 0
                        ? Math.round((week.submitted / (week.assignments * analytics.cohort.total_students)) * 100)
                        : 0;
                      return (
                        <div key={week.week} className="flex items-center gap-4">
                          <div className="w-20 flex-shrink-0">
                            <p className="text-sm font-medium text-[#000000]">Week {week.week}</p>
                            <p className="text-xs text-[#666666]">{week.assignments} assignment{week.assignments !== 1 ? 's' : ''}</p>
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-[#666666]">{week.submitted} submitted</span>
                              <span className="text-xs text-[#22438E]">{week.reviewed} reviewed</span>
                            </div>
                            <Progress value={completionRate} className="h-2" />
                          </div>
                          <div className="w-16 text-right">
                            <span className="text-sm font-medium text-[#000000]">{completionRate}%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Student Progress */}
            <Card className="bg-white border-[#B8D4E8]">
              <CardHeader>
                <CardTitle className="text-lg font-normal">Student Progress</CardTitle>
                <CardDescription>Click a student to see their weekly submissions and feedback</CardDescription>
              </CardHeader>
              <CardContent>
                {analytics.student_progress?.length === 0 ? (
                  <div className="text-center py-8">
                    <Users className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                    <p className="text-[#666666]">No students in this cohort</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {analytics.student_progress.map((student, index) => {
                      const isExpanded = expandedStudents[student.user_id];
                      return (
                        <div key={student.user_id} className="border border-[#B8D4E8] rounded-xl overflow-hidden" data-testid={`student-row-${student.user_id}`}>
                          {/* Student Summary Row */}
                          <div
                            className="flex items-center gap-4 p-3 cursor-pointer hover:bg-[#E1F0FF] transition-colors"
                            onClick={() => toggleStudent(student.user_id)}
                          >
                            <div className="w-6 text-center text-sm text-[#666666]">
                              {index + 1}
                            </div>
                            <div className="w-10 h-10 flex-shrink-0">
                              {student.picture ? (
                                <img src={student.picture} alt={student.name} className="w-10 h-10 rounded-full" />
                              ) : (
                                <div className="w-10 h-10 bg-[#D0E6F9] rounded-full flex items-center justify-center">
                                  <User className="w-5 h-5 text-[#666666]" />
                                </div>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="font-medium text-[#000000] truncate">{student.name}</p>
                              <p className="text-xs text-[#666666] truncate">{student.email}</p>
                            </div>
                            <div className="flex items-center gap-4">
                              <div className="text-right hidden md:block">
                                <p className="text-sm text-[#000000]">{student.submissions} submitted</p>
                                <p className="text-xs text-[#666666]">{student.completed} reviewed</p>
                              </div>
                              <div className="w-24 hidden md:block">
                                <Progress value={student.completion_rate} className="h-2" />
                              </div>
                              <div className="w-14 text-right">
                                <span className={`text-sm font-medium ${getCompletionColorClass(student.completion_rate)}`}>
                                  {student.completion_rate}%
                                </span>
                              </div>
                              {isExpanded
                                ? <ChevronUp className="w-4 h-4 text-[#666666]" />
                                : <ChevronDown className="w-4 h-4 text-[#666666]" />
                              }
                            </div>
                          </div>

                          {/* Expanded Week Details */}
                          {isExpanded && student.week_details && (
                            <div className="border-t border-[#B8D4E8] px-4 py-3 bg-[#FAFAF9] space-y-2" data-testid={`student-details-${student.user_id}`}>
                              {student.week_details.length === 0 ? (
                                <p className="text-sm text-[#666666] text-center py-2">No homework assignments for this cohort</p>
                              ) : (
                                student.week_details.map(week => (
                                  <StudentWeekRow
                                    key={`${student.user_id}-${week.week_number}`}
                                    week={{ ...week, studentId: student.user_id }}
                                  />
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
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

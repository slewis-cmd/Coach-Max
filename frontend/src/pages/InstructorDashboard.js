import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { 
  BookOpen, Users, Plus, LogOut, ChevronRight, Upload,
  AlertCircle, FileEdit, Mail, TrendingUp, Download, Bell, MessageCircle
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { handleDownloadSubmission } from '../utils/download';
import { InstructorSidebar } from '../components/instructor/Sidebar';
import { CreateCohortDialog } from '../components/instructor/CreateCohortDialog';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function InstructorDashboard() {
  const { user, logout, loading, isAuthenticated, isInstructor } = useAuth();
  const isSuperAdmin = user?.role === 'super_admin';
  const navigate = useNavigate();
  const [cohorts, setCohorts] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loadingData, setLoadingData] = useState(true);
  const [showCreateCohort, setShowCreateCohort] = useState(false);
  const [newCohort, setNewCohort] = useState({ name: '', description: '' });
  const [creating, setCreating] = useState(false);
  const [sendingDigest, setSendingDigest] = useState(false);

  const handleSendDigest = async () => {
    setSendingDigest(true);
    try {
      await axios.post(`${API_URL}/api/admin/send-weekly-digest`);
      toast.success('Weekly digest is being generated and sent to info@theboostpad.org');
    } catch (_e) {
      toast.error('Failed to send digest');
    } finally {
      setSendingDigest(false);
    }
  };

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/');
    } else if (!loading && !isInstructor) {
      navigate('/role-selection');
    }
  }, [loading, isAuthenticated, isInstructor, navigate]);

  useEffect(() => {
    if (isInstructor) fetchData();
  }, [isInstructor]);

  const fetchData = async () => {
    try {
      const [cohortsRes, submissionsRes, analyticsRes] = await Promise.all([
        axios.get(`${API_URL}/api/cohorts`),
        axios.get(`${API_URL}/api/submissions`),
        axios.get(`${API_URL}/api/analytics/dashboard`)
      ]);
      setCohorts(cohortsRes.data);
      setSubmissions(submissionsRes.data);
      setAnalytics(analyticsRes.data);
    } catch (_err) {
      toast.error('Failed to load data');
    } finally {
      setLoadingData(false);
    }
  };

  const handleCreateCohort = async () => {
    if (!newCohort.name.trim()) { toast.error('Please enter a cohort name'); return; }
    setCreating(true);
    try {
      await axios.post(`${API_URL}/api/cohorts`, newCohort);
      toast.success('Cohort created successfully!');
      setShowCreateCohort(false);
      setNewCohort({ name: '', description: '' });
      fetchData();
    } catch (error) {
      toast.error('Failed to create cohort');
    } finally {
      setCreating(false);
    }
  };

  const handleLogout = async () => { await logout(); navigate('/'); };

  const pendingSubmissions = submissions.filter(s => s.status === 'pending');
  const draftSubmissions = submissions.filter(s => s.status === 'draft');
  const totalActionRequired = pendingSubmissions.length + draftSubmissions.length;

  const cohortPendingCounts = {};
  submissions.forEach(s => {
    if (s.status === 'pending' || s.status === 'draft') {
      cohortPendingCounts[s.cohort_id] = (cohortPendingCounts[s.cohort_id] || 0) + 1;
    }
  });

  if (loading || loadingData) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="instructor-dashboard">
      <InstructorSidebar user={user} isSuperAdmin={isSuperAdmin}
        totalActionRequired={totalActionRequired} onLogout={handleLogout} />

      <main className="md:ml-64 p-6 md:p-8">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#22438E] rounded-lg flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold">The Boost Pad</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => navigate('/submissions')}
              className="relative flex items-center justify-center w-9 h-9 rounded-full bg-white border border-[#B8D4E8]"
              data-testid="notification-bell-mobile">
              <Bell className="w-4 h-4 text-[#333333]" />
              {totalActionRequired > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center bg-[#DC2626] text-white text-[10px] font-semibold rounded-full px-0.5">
                  {totalActionRequired}
                </span>
              )}
            </button>
            <Button variant="ghost" size="icon" onClick={handleLogout}>
              <LogOut className="w-5 h-5" />
            </Button>
          </div>
        </div>

        {/* Header */}
        <div className="mb-8 animate-fade-in flex items-start justify-between">
          <div>
            <h1 className="text-3xl md:text-4xl font-light tracking-tight text-[#000000] mb-2">
              Welcome back, {user?.name?.split(' ')[0]}
            </h1>
            <p className="text-[#333333]">Manage your cohorts and review student submissions</p>
          </div>
          <button onClick={() => navigate('/submissions')}
            className="relative hidden md:flex items-center justify-center w-10 h-10 rounded-full bg-white border border-[#B8D4E8] hover:bg-[#D0E6F9] transition-colors"
            data-testid="notification-bell">
            <Bell className="w-5 h-5 text-[#333333]" />
            {totalActionRequired > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[20px] h-5 flex items-center justify-center bg-[#DC2626] text-white text-[11px] font-semibold rounded-full px-1"
                data-testid="notification-badge-count">{totalActionRequired}</span>
            )}
          </button>
        </div>

        {/* Action Required Alert */}
        {totalActionRequired > 0 && (
          <Card className="bg-[#FEF3C7] border-[#7CBAE6] mb-6 animate-fade-in">
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 bg-[#7CBAE6] rounded-full flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-[#1A75BA]" />
                </div>
                <div className="flex-1">
                  <p className="font-medium text-[#1A75BA]">Action Required</p>
                  <p className="text-sm text-[#92400E]">
                    {pendingSubmissions.length > 0 && `${pendingSubmissions.length} submission${pendingSubmissions.length > 1 ? 's' : ''} need AI review`}
                    {pendingSubmissions.length > 0 && draftSubmissions.length > 0 && ' • '}
                    {draftSubmissions.length > 0 && `${draftSubmissions.length} draft${draftSubmissions.length > 1 ? 's' : ''} ready to send`}
                  </p>
                </div>
                <Button onClick={() => navigate('/submissions')} className="bg-[#1A75BA] text-white hover:bg-[#713F12]">
                  Review Now
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8 stagger-children">
          <Card className="bg-white border-[#B8D4E8]">
            <CardContent className="p-4">
              <p className="text-sm text-[#666666] mb-1">Cohorts</p>
              <p className="text-2xl font-light text-[#000000]">{analytics?.cohorts || cohorts.length}</p>
            </CardContent>
          </Card>
          <Card className="bg-white border-[#B8D4E8]">
            <CardContent className="p-4">
              <p className="text-sm text-[#666666] mb-1">Students</p>
              <p className="text-2xl font-light text-[#000000]">
                {analytics?.total_students || cohorts.reduce((acc, c) => acc + (c.student_ids?.length || 0), 0)}
              </p>
            </CardContent>
          </Card>
          <Card className="bg-[#FEF9C3] border-[#7CBAE6]">
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Upload className="w-4 h-4 text-[#1A75BA]" />
                <p className="text-sm text-[#1A75BA]">Needs Review</p>
              </div>
              <p className="text-2xl font-light text-[#1A75BA]">{analytics?.submissions?.pending || pendingSubmissions.length}</p>
            </CardContent>
          </Card>
          <Card className="bg-[#E1F0FF] border-[#BAE6FD]">
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <FileEdit className="w-4 h-4 text-[#22438E]" />
                <p className="text-sm text-[#22438E]">Drafts to Send</p>
              </div>
              <p className="text-2xl font-light text-[#22438E]">{analytics?.submissions?.draft || draftSubmissions.length}</p>
            </CardContent>
          </Card>
          <Card className="bg-[#E1F0FF] border-[#B8D4E8]">
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-[#22438E]" />
                <p className="text-sm text-[#22438E]">Feedback Sent</p>
              </div>
              <p className="text-2xl font-light text-[#22438E]">
                {analytics?.submissions?.sent || submissions.filter(s => s.status === 'sent' || s.feedback_sent).length}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Weekly Activity */}
        {analytics?.recent_activity && (
          <Card className="bg-white border-[#B8D4E8] mb-8">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-normal flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-[#22438E]" />This Week
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-light text-[#000000]">{analytics.recent_activity.submissions_this_week}</p>
              <p className="text-sm text-[#666666]">new submissions received</p>
            </CardContent>
          </Card>
        )}

        {/* Cohorts Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-light text-[#000000]">Your Cohorts</h2>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSendDigest}
                disabled={sendingDigest}
                className="border-[#22438E] text-[#22438E] hover:bg-[#E1F0FF]"
                data-testid="send-digest-btn"
              >
                {sendingDigest ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin mr-1.5" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Mail className="w-3.5 h-3.5 mr-1.5" />
                    Send Weekly Digest
                  </>
                )}
              </Button>
              <Button data-testid="create-cohort-btn" onClick={() => setShowCreateCohort(true)}
                className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">
                <Plus className="w-4 h-4 mr-2" />New Cohort
              </Button>
            </div>
          </div>
          {cohorts.length === 0 ? (
            <Card className="bg-white border-[#B8D4E8] border-dashed">
              <CardContent className="p-12 text-center">
                <Users className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[#000000] mb-2">No cohorts yet</h3>
                <p className="text-[#333333] mb-4">Create your first cohort to get started</p>
                <Button onClick={() => setShowCreateCohort(true)} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">
                  Create Cohort
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {cohorts.map((cohort, index) => (
                <Card key={cohort.cohort_id}
                  className="bg-white border-[#B8D4E8] hover:shadow-md transition-shadow cursor-pointer group"
                  onClick={() => navigate(`/cohort/${cohort.cohort_id}`)}
                  style={{ animationDelay: `${index * 0.1}s` }}
                  data-testid={`cohort-card-${cohort.cohort_id}`}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg font-normal flex items-center justify-between">
                      {cohort.name}
                      <ChevronRight className="w-5 h-5 text-[#94B8D9] group-hover:text-[#000000] transition-colors" />
                    </CardTitle>
                    <CardDescription>{cohort.description || 'No description'}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-4 text-sm text-[#333333]">
                      <span className="flex items-center gap-1">
                        <Users className="w-4 h-4" />{cohort.student_ids?.length || 0} students
                      </span>
                      {cohortPendingCounts[cohort.cohort_id] > 0 && (
                        <span className="flex items-center gap-1 text-[#DC2626]"
                          data-testid={`cohort-pending-badge-${cohort.cohort_id}`}>
                          <Bell className="w-3.5 h-3.5" />{cohortPendingCounts[cohort.cohort_id]} pending
                        </span>
                      )}
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/coach-max-insights/${cohort.cohort_id}`); }}
                      className="mt-3 text-xs text-[#22438E] hover:underline flex items-center gap-1"
                      data-testid={`insights-link-${cohort.cohort_id}`}
                    >
                      <MessageCircle className="w-3 h-3" /> Coach Max Insights
                    </button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Pending & Draft Submissions */}
        {(pendingSubmissions.length > 0 || draftSubmissions.length > 0) && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-light text-[#000000]">Action Required</h2>
              <Link to="/submissions" className="text-sm text-[#333333] hover:text-[#000000] flex items-center gap-1">
                View all <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="space-y-3">
              {draftSubmissions.slice(0, 3).map((sub) => (
                <Card key={sub.submission_id}
                  className="bg-[#F0F9FF] border-[#BAE6FD] hover:shadow-sm transition-shadow cursor-pointer"
                  onClick={() => navigate(`/submission/${sub.submission_id}`)}
                  data-testid={`draft-${sub.submission_id}`}>
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
                        <FileEdit className="w-5 h-5 text-[#22438E]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#000000]">{sub.student?.name || 'Unknown'}</p>
                        <p className="text-sm text-[#666666]">{sub.material?.title || 'Homework'} • Ready to send</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={(e) => {
                        e.stopPropagation();
                        handleDownloadSubmission(sub.submission_id, sub.file_name || 'homework');
                      }} className="inline-flex items-center gap-1 text-xs text-[#333333] hover:text-[#000000] border border-[#B8D4E8] rounded-lg px-2.5 py-1.5"
                        data-testid={`download-draft-${sub.submission_id}`}>
                        <Download className="w-3.5 h-3.5" />Homework
                      </button>
                      <Button size="sm" className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">Review & Send</Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {pendingSubmissions.slice(0, 3).map((sub) => (
                <Card key={sub.submission_id}
                  className="bg-white border-[#B8D4E8] hover:shadow-sm transition-shadow cursor-pointer"
                  onClick={() => navigate(`/submission/${sub.submission_id}`)}
                  data-testid={`submission-${sub.submission_id}`}>
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#7CBAE6] rounded-lg flex items-center justify-center">
                        <Upload className="w-5 h-5 text-[#000000]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#000000]">{sub.student?.name || 'Unknown'}</p>
                        <p className="text-sm text-[#666666]">{sub.material?.title || 'Homework'} • Week {sub.material?.week_number || '?'}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={(e) => {
                        e.stopPropagation();
                        handleDownloadSubmission(sub.submission_id, sub.file_name || 'homework');
                      }} className="inline-flex items-center gap-1 text-xs text-[#333333] hover:text-[#000000] border border-[#B8D4E8] rounded-lg px-2.5 py-1.5"
                        data-testid={`download-pending-${sub.submission_id}`}>
                        <Download className="w-3.5 h-3.5" />Homework
                      </button>
                      <Button size="sm" className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">Generate Review</Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </main>

      <CreateCohortDialog open={showCreateCohort} onOpenChange={setShowCreateCohort}
        newCohort={newCohort} setNewCohort={setNewCohort} creating={creating} onSubmit={handleCreateCohort} />
    </div>
  );
}

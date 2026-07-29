import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { 
  BookOpen, LogOut, Upload, CheckCircle, Clock, MessageSquare, FileText, PlayCircle,
  ChevronDown, ChevronUp, File, Calendar, Hourglass, Send, X, MessageCircle, Download,
  Globe
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { downloadFile } from '../utils/download';
import { MAX_UPLOAD_MB, isFileTooLarge, fileSizeMbLabel, humanUploadError, tooLargeMessage } from '../lib/uploadLimits';
import { CoachMaxChat } from '../components/student/CoachMaxChat';
import { StatusBadge } from '../components/student/StatusBadge';
import { HomeworkTrackRow } from '../components/student/HomeworkTrackRow';

const API_URL = process.env.REACT_APP_BACKEND_URL;

function EmptyStateCard({ icon: Icon, title, message }) {
  return (
    <Card className="bg-white border-[#B8D4E8] border-dashed">
      <CardContent className="p-12 text-center">
        <Icon className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
        <h3 className="text-lg font-medium text-[#000000] mb-2">{title}</h3>
        <p className="text-[#333333]">{message}</p>
      </CardContent>
    </Card>
  );
}

function getWeekNumberClass(status) {
  if (status === 'feedback_provided') return 'bg-[#22438E] text-white';
  if (status === 'no_homework') return 'bg-[#B8D4E8] text-[#666666]';
  return 'bg-[#000000] text-white';
}

export default function StudentDashboard() {
  const { user, logout, loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [expandedWeek, setExpandedWeek] = useState(null);

  // Upload dialog
  const [showUpload, setShowUpload] = useState(false);
  const [uploadTarget, setUploadTarget] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Coach Max chat
  const [chatOpen, setChatOpen] = useState(null); // { submissionId, weekNumber }

  // Language preference
  const [language, setLanguage] = useState(user?.language_preference || 'en');

  const handleLanguageChange = async (lang) => {
    setLanguage(lang);
    try {
      await axios.put(`${API_URL}/api/user/language`, { language: lang });
      toast.success(lang === 'es' ? 'Idioma actualizado a Espanol' : 'Language updated to English');
    } catch (_e) {
      toast.error('Failed to update language preference');
    }
  };

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/');
    } else if (!loading && user?.role !== 'student') {
      navigate('/dashboard');
    }
  }, [loading, isAuthenticated, user, navigate]);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/student/dashboard`);
      setDashboardData(res.data);
    } catch (_err) {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    if (!loading && user?.role === 'student') {
      fetchDashboard();
    }
  }, [loading, user, fetchDashboard]);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const openUpload = (homework, cohortId) => {
    setUploadTarget({ ...homework, cohort_id: cohortId });
    setUploadFile(null);
    setShowUpload(true);
  };

  const handleSubmit = async () => {
    if (!uploadFile) {
      toast.error('Please select a file');
      return;
    }
    if (isFileTooLarge(uploadFile)) {
      toast.error(tooLargeMessage(uploadFile));
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      await axios.post(
        `${API_URL}/api/materials/${uploadTarget.material_id}/submit?cohort_id=${encodeURIComponent(uploadTarget.cohort_id)}`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 }
      );
      toast.success('Homework submitted! Your instructor will review it soon.');
      setShowUpload(false);
      setUploadTarget(null);
      setUploadFile(null);
      fetchDashboard();
    } catch (error) {
      toast.error(humanUploadError(error, 'Failed to submit homework'));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleFeedback = (weekKey) => {
    setExpandedWeek(expandedWeek === weekKey ? null : weekKey);
  };

  if (loading || loadingData) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const activeCohort = dashboardData[0];

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="student-dashboard">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 bottom-0 w-64 bg-[#D0E6F9] border-r border-[#B8D4E8] p-6 hidden md:block">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-8 h-8 bg-[#000000] rounded-lg flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-[#000000]">The Boost Pad</span>
        </div>

        <nav className="space-y-2">
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white text-[#000000] font-medium">
            <FileText className="w-5 h-5" />
            My Progress
          </div>
        </nav>

        <div className="absolute bottom-6 left-6 right-6">
          <div className="flex items-center gap-3 mb-4">
            {user?.picture && (
              <img src={user.picture} alt={user.name} className="w-10 h-10 rounded-full" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[#000000] truncate">{user?.name}</p>
              <p className="text-xs text-[#666666] truncate">{user?.email}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 mb-3 px-2" data-testid="language-selector">
            <Globe className="w-4 h-4 text-[#666666]" />
            <button
              onClick={() => handleLanguageChange('en')}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${language === 'en' ? 'bg-[#22438E] text-white' : 'bg-white text-[#333333] hover:bg-[#E1F0FF]'}`}
              data-testid="lang-en-btn"
            >EN</button>
            <button
              onClick={() => handleLanguageChange('es')}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${language === 'es' ? 'bg-[#22438E] text-white' : 'bg-white text-[#333333] hover:bg-[#E1F0FF]'}`}
              data-testid="lang-es-btn"
            >ES</button>
          </div>
          <Button
            variant="ghost"
            className="w-full justify-start text-[#333333] hover:text-[#000000]"
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
            <div className="w-8 h-8 bg-[#000000] rounded-lg flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold">The Boost Pad</span>
          </div>
          <Button variant="ghost" size="icon" onClick={handleLogout}>
            <LogOut className="w-5 h-5" />
          </Button>
        </div>

        {/* Header */}
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl md:text-4xl font-light tracking-tight text-[#000000] mb-2">
            Hello, {user?.name?.split(' ')[0]}!
          </h1>
          <p className="text-[#333333]">
            {activeCohort ? activeCohort.cohort_name : 'No courses assigned yet'}
          </p>
        </div>

        {activeCohort && activeCohort.course_resources && activeCohort.course_resources.length > 0 && (
          <Card className="mb-6 bg-white border-[#B8D4E8]" data-testid="course-resources-section">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-3">
                <BookOpen className="w-4 h-4 text-[#22438E]" />
                <h2 className="text-sm font-semibold text-[#22438E] uppercase tracking-wide">
                  Course Resources
                </h2>
                <span className="text-xs text-[#666666] ml-1">— applies across all weeks</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {activeCohort.course_resources.map((mat) => {
                  const isVideo = mat.material_type === 'video';
                  const isUrlVideo = isVideo && !!mat.video_url;
                  const handleClick = () => {
                    if (isUrlVideo) {
                      window.open(mat.video_url, '_blank', 'noopener,noreferrer');
                    } else {
                      downloadFile(
                        `${API_URL}/api/materials/${mat.material_id}/download`,
                        mat.file_name
                      );
                    }
                  };
                  return (
                    <button
                      key={mat.material_id}
                      onClick={handleClick}
                      className="inline-flex items-center gap-1.5 text-xs bg-[#E1F0FF] border border-[#B8D4E8] text-[#22438E] rounded-lg px-3 py-2 hover:bg-[#B8D4E8] transition-colors"
                      title={mat.description || mat.title}
                      data-testid={`course-resource-${mat.material_id}`}
                    >
                      {isVideo ? <PlayCircle className="w-3.5 h-3.5" /> : <FileText className="w-3.5 h-3.5" />}
                      {mat.title}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {!activeCohort && (
          <EmptyStateCard
            icon={BookOpen}
            title="No courses yet"
            message="Your instructor will add you to a cohort soon"
          />
        )}
        {activeCohort && activeCohort.weeks.length === 0 && (
          <EmptyStateCard
            icon={Clock}
            title="No weeks released yet"
            message="Your instructor will release course weeks as the program progresses"
          />
        )}
        {activeCohort && activeCohort.weeks.length > 0 && (
          <div className="space-y-3" data-testid="weekly-progress">
            {activeCohort.weeks.map((week) => {
              const weekKey = `${activeCohort.cohort_id}-${week.week_number}`;
              const homeworks = week.homeworks && week.homeworks.length > 0
                ? week.homeworks
                : (week.homework ? [{ ...week.homework, submission: week.submission, status: week.status, feedback: week.feedback }] : []);
              const hasHomework = homeworks.length > 0;
              const hasAnyFeedback = homeworks.some(h => h.status === 'feedback_provided' && h.feedback);

              return (
                <Card
                  key={week.week_number}
                  className={`bg-white border-[#B8D4E8] transition-all ${
                    hasAnyFeedback ? 'hover:shadow-md' : ''
                  } ${!hasHomework ? 'opacity-50' : ''}`}
                  data-testid={`week-${week.week_number}`}
                >
                  <CardContent className="p-4 md:p-5">
                    {/* Week Header */}
                    <div className="flex items-center gap-4 mb-3">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center font-medium text-sm flex-shrink-0 ${getWeekNumberClass(week.status)}`}>
                        {week.week_number}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <h3 className="font-medium text-[#000000] text-sm md:text-base">
                            Week {week.week_number}
                          </h3>
                          <StatusBadge status={week.status} />
                          {homeworks.length > 1 && (
                            <span className="text-xs text-[#666666]">
                              {homeworks.length} exercises
                            </span>
                          )}
                        </div>
                        {!hasHomework && (
                          <p className="text-sm text-[#666666] mt-0.5">No assignment yet</p>
                        )}
                      </div>
                    </div>

                    {/* Week Materials — downloadable when any feedback exists */}
                    {hasAnyFeedback && week.materials && week.materials.length > 0 && (
                      <div className="mb-3 pb-3 border-b border-[#B8D4E8]">
                        <p className="text-xs font-medium text-[#22438E] uppercase tracking-wide mb-2">Week Materials</p>
                        <div className="flex flex-wrap gap-2">
                          {week.materials.map(mat => (
                            <button
                              key={mat.material_id}
                              onClick={(e) => {
                                e.stopPropagation();
                                downloadFile(
                                  `${API_URL}/api/materials/${mat.material_id}/download`,
                                  mat.file_name
                                );
                              }}
                              className="inline-flex items-center gap-1.5 text-xs bg-white border border-[#B8D4E8] text-[#22438E] rounded-lg px-2.5 py-1.5 hover:bg-[#E1F0FF] transition-colors"
                              data-testid={`download-material-${mat.material_id}`}
                            >
                              <FileText className="w-3 h-3" />
                              {mat.file_name}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Homework tracks (one row per track) */}
                    {hasHomework && (
                      <div className="space-y-2">
                        {homeworks.map((hw, idx) => {
                          const trackKey = `${weekKey}-${hw.material_id}`;
                          const isExpanded = expandedWeek === trackKey;
                          const showLabel = homeworks.length > 1 ? `Exercise ${idx + 1}` : null;
                          return (
                            <HomeworkTrackRow
                              key={hw.material_id}
                              hw={hw}
                              weekNumber={week.week_number}
                              cohortId={activeCohort.cohort_id}
                              showLabel={showLabel}
                              isExpanded={isExpanded}
                              onToggleExpand={(e) => {
                                if (e) e.stopPropagation();
                                toggleFeedback(trackKey);
                              }}
                              onOpenUpload={(hwWithCohort) => openUpload(hwWithCohort, activeCohort.cohort_id)}
                              onAskCoachMax={(submissionId, weekNumber) =>
                                setChatOpen({ submissionId, weekNumber })
                              }
                            />
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </main>

      {/* Upload Dialog */}
      <Dialog open={showUpload} onOpenChange={setShowUpload}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Submit Homework</DialogTitle>
            <DialogDescription>
              {uploadTarget?.title}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label>Your Submission (PDF or Word)</Label>
            <div className="mt-1 upload-zone rounded-lg p-8 text-center cursor-pointer">
              <label htmlFor="student-homework-file" className="cursor-pointer block">
                {uploadFile ? (
                  <div className="flex items-center justify-center gap-2">
                    <File className="w-5 h-5 text-[#22438E]" />
                    <span className="text-sm text-[#000000]">{uploadFile.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload className="w-10 h-10 text-[#94B8D9] mx-auto mb-2" />
                    <p className="text-sm text-[#666666]">Click to upload your homework</p>
                    <p className="text-xs text-[#94B8D9] mt-1">PDF or DOCX &middot; Max {MAX_UPLOAD_MB} MB</p>
                  </>
                )}
              </label>
            </div>
            <input
              id="student-homework-file"
              data-testid="student-homework-file-input"
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={(e) => setUploadFile(e.target.files[0])}
            />
            {isFileTooLarge(uploadFile) && (
              <p
                className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md p-2 mt-2"
                data-testid="student-homework-too-large-warning"
              >
                Your file is {fileSizeMbLabel(uploadFile)} MB — over our {MAX_UPLOAD_MB} MB limit.
                Please compress it (Mac: QuickTime → Export → 480p; iPhone: pick Compress in Share; HandBrake Web preset) and re-select the smaller file.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUpload(false)}>
              Cancel
            </Button>
            <Button
              data-testid="submit-homework-btn"
              onClick={handleSubmit}
              disabled={submitting || isFileTooLarge(uploadFile)}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
            >
              {submitting ? 'Submitting...' : 'Submit'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Coach Max Chat */}
      {chatOpen && (
        <CoachMaxChat
          submissionId={chatOpen.submissionId}
          weekNumber={chatOpen.weekNumber}
          onClose={() => setChatOpen(null)}
        />
      )}
    </div>
  );
}

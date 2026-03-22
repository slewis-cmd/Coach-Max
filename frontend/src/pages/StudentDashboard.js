import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { 
  BookOpen, 
  LogOut,
  Upload,
  CheckCircle,
  Clock,
  MessageSquare,
  FileText,
  ChevronDown,
  ChevronUp,
  File,
  Calendar,
  Hourglass,
  Send,
  X,
  MessageCircle,
  Download
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const downloadFile = async (url, filename) => {
  const token = localStorage.getItem('thinkific_session_token');
  if (!token) {
    toast.error('Please log in to download files');
    return;
  }
  const separator = url.includes('?') ? '&' : '?';
  try {
    const response = await fetch(`${url}${separator}token=${encodeURIComponent(token)}`);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || 'Download failed');
    }
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
    console.error('Download error:', err);
    toast.error('Failed to download file');
  }
};

const STATUS_CONFIG = {
  no_homework: { label: '', color: '', icon: null },
  waiting_on_submission: {
    label: 'Waiting on Submission',
    color: 'bg-[#FEF3C7] text-[#92400E]',
    icon: Clock
  },
  submitted: {
    label: 'Submitted',
    color: 'bg-[#DBEAFE] text-[#1E40AF]',
    icon: Send
  },
  under_review: {
    label: 'Under Review',
    color: 'bg-[#F3E8FF] text-[#6B21A8]',
    icon: Hourglass
  },
  feedback_provided: {
    label: 'Feedback Provided',
    color: 'bg-[#D1FAE5] text-[#065F46]',
    icon: CheckCircle
  }
};

function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status];
  if (!config || !config.label) return null;
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${config.color}`} data-testid={`status-${status}`}>
      {Icon && <Icon className="w-3 h-3" />}
      {config.label}
    </span>
  );
}

function CoachMaxChat({ submissionId, weekNumber, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/chat/history/${submissionId}`);
        const history = res.data.map(c => ([
          { role: 'student', text: c.message },
          { role: 'coach', text: c.response }
        ])).flat();
        setMessages(history);
      } catch (e) {
        console.error('Error loading chat history:', e);
      } finally {
        setLoadingHistory(false);
      }
    };
    loadHistory();
  }, [submissionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'student', text: userMsg }]);
    setSending(true);

    try {
      const res = await axios.post(`${API_URL}/api/chat/ask-tutor`, {
        message: userMsg,
        submission_id: submissionId
      });
      setMessages(prev => [...prev, { role: 'coach', text: res.data.response }]);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Coach Max is unavailable right now');
      setMessages(prev => [...prev, { role: 'coach', text: "Sorry, I'm having trouble right now. Please try again in a moment." }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center" data-testid="coach-max-chat">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      
      {/* Chat Panel */}
      <div className="relative bg-white w-full md:w-[480px] md:max-h-[600px] h-[85vh] md:h-auto md:rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-fade-in">
        {/* Header */}
        <div className="bg-[#1A1A1A] text-white px-5 py-4 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-[#065F46] rounded-full flex items-center justify-center">
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-medium text-sm">Coach Max</h3>
              <p className="text-xs text-white/60">Week {weekNumber} feedback discussion</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="text-white/70 hover:text-white hover:bg-white/10">
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#FAFAF8]">
          {/* Welcome message */}
          {messages.length === 0 && !loadingHistory && (
            <div className="text-center py-8">
              <div className="w-14 h-14 bg-[#D1FAE5] rounded-full flex items-center justify-center mx-auto mb-3">
                <MessageCircle className="w-7 h-7 text-[#065F46]" />
              </div>
              <h4 className="font-medium text-[#1A1A1A] mb-1">Hi! I'm Coach Max</h4>
              <p className="text-sm text-[#5A5A5A] max-w-xs mx-auto">
                Ask me anything about your Week {weekNumber} feedback. I'm here to help you grow!
              </p>
            </div>
          )}

          {loadingHistory && (
            <div className="flex justify-center py-8">
              <div className="w-6 h-6 border-2 border-[#065F46] border-t-transparent rounded-full animate-spin"></div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'student' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'student'
                  ? 'bg-[#1A1A1A] text-white rounded-br-md'
                  : 'bg-white border border-[#E5E5E5] text-[#1A1A1A] rounded-bl-md shadow-sm'
              }`}>
                {msg.role === 'coach' && (
                  <p className="text-xs font-medium text-[#065F46] mb-1">Coach Max</p>
                )}
                <div className="whitespace-pre-wrap">{msg.text}</div>
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex justify-start">
              <div className="bg-white border border-[#E5E5E5] rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                <p className="text-xs font-medium text-[#065F46] mb-1">Coach Max</p>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 bg-[#065F46] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-[#065F46] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-[#065F46] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-[#E5E5E5] p-3 flex items-center gap-2 bg-white flex-shrink-0">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask Coach Max a question..."
            className="flex-1 px-4 py-2.5 bg-[#F2F0ED] rounded-full text-sm outline-none focus:ring-2 focus:ring-[#065F46]/20"
            disabled={sending}
            data-testid="coach-max-input"
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className="bg-[#065F46] text-white hover:bg-[#064E3B] rounded-full w-10 h-10 flex-shrink-0"
            data-testid="coach-max-send"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
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
    } catch (error) {
      console.error('Error fetching dashboard:', error);
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

  const openUpload = (homework) => {
    setUploadTarget(homework);
    setUploadFile(null);
    setShowUpload(true);
  };

  const handleSubmit = async () => {
    if (!uploadFile) {
      toast.error('Please select a file');
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      await axios.post(
        `${API_URL}/api/materials/${uploadTarget.material_id}/submit`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      toast.success('Homework submitted! Your instructor will review it soon.');
      setShowUpload(false);
      setUploadTarget(null);
      setUploadFile(null);
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to submit homework');
    } finally {
      setSubmitting(false);
    }
  };

  const toggleFeedback = (weekKey) => {
    setExpandedWeek(expandedWeek === weekKey ? null : weekKey);
  };

  if (loading || loadingData) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const activeCohort = dashboardData[0];

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
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white text-[#1A1A1A] font-medium">
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
            {activeCohort ? activeCohort.cohort_name : 'No courses assigned yet'}
          </p>
        </div>

        {!activeCohort ? (
          <Card className="bg-white border-[#E5E5E5] border-dashed">
            <CardContent className="p-12 text-center">
              <BookOpen className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No courses yet</h3>
              <p className="text-[#5A5A5A]">Your instructor will add you to a cohort soon</p>
            </CardContent>
          </Card>
        ) : activeCohort.weeks.length === 0 ? (
          <Card className="bg-white border-[#E5E5E5] border-dashed">
            <CardContent className="p-12 text-center">
              <Clock className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No weeks released yet</h3>
              <p className="text-[#5A5A5A]">Your instructor will release course weeks as the program progresses</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3" data-testid="weekly-progress">
            {activeCohort.weeks.map((week) => {
              const weekKey = `${activeCohort.cohort_id}-${week.week_number}`;
              const isExpanded = expandedWeek === weekKey;
              const hasFeedback = week.status === 'feedback_provided' && week.feedback;
              const hasHomework = week.status !== 'no_homework';
              const canSubmit = week.status === 'waiting_on_submission' ||
                (week.submission?.resubmission_allowed && week.status !== 'feedback_provided');

              return (
                <Card
                  key={week.week_number}
                  className={`bg-white border-[#E5E5E5] transition-all ${
                    hasFeedback ? 'hover:shadow-md' : ''
                  } ${!hasHomework ? 'opacity-50' : ''}`}
                  data-testid={`week-${week.week_number}`}
                >
                  <CardContent className="p-0">
                    {/* Week Row */}
                    <div
                      className={`flex items-center gap-4 p-4 md:p-5 ${hasFeedback ? 'cursor-pointer' : ''}`}
                      onClick={hasFeedback ? () => toggleFeedback(weekKey) : undefined}
                    >
                      {/* Week Number */}
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center font-medium text-sm flex-shrink-0 ${
                        week.status === 'feedback_provided'
                          ? 'bg-[#065F46] text-white'
                          : week.status === 'no_homework'
                            ? 'bg-[#E5E5E5] text-[#888]'
                            : 'bg-[#1A1A1A] text-white'
                      }`}>
                        {week.week_number}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <h3 className="font-medium text-[#1A1A1A] text-sm md:text-base">
                            Week {week.week_number}
                          </h3>
                          <StatusBadge status={week.status} />
                        </div>
                        {week.homework && (
                          <p className="text-sm text-[#5A5A5A] mt-0.5 truncate">
                            {week.homework.title}
                            {week.homework.due_date && (
                              <span className="inline-flex items-center gap-1 ml-3 text-xs text-[#92400E]">
                                <Calendar className="w-3 h-3" />
                                Due {new Date(week.homework.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                              </span>
                            )}
                          </p>
                        )}
                        {!hasHomework && (
                          <p className="text-sm text-[#888] mt-0.5">No assignment yet</p>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {canSubmit && (
                          <Button
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              openUpload(week.homework);
                            }}
                            className="bg-[#065F46] text-white hover:bg-[#064E3B] rounded-lg text-xs md:text-sm"
                            data-testid={`submit-week-${week.week_number}`}
                          >
                            <Upload className="w-3.5 h-3.5 mr-1.5" />
                            Submit
                          </Button>
                        )}
                        {week.submission && week.status !== 'waiting_on_submission' && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              downloadFile(
                                `${API_URL}/api/submissions/${week.submission.submission_id}/download`,
                                week.submission.file_name
                              );
                            }}
                            className="inline-flex items-center gap-1.5 text-xs text-[#5A5A5A] hover:text-[#1A1A1A] transition-colors"
                            data-testid={`download-submission-${week.week_number}`}
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span className="hidden md:inline">{week.submission.file_name}</span>
                            <span className="md:hidden">Download</span>
                          </button>
                        )}
                        {hasFeedback && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-[#065F46] hover:bg-[#D1FAE5]"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleFeedback(weekKey);
                            }}
                            data-testid={`view-feedback-${week.week_number}`}
                          >
                            <MessageSquare className="w-4 h-4 mr-1" />
                            Feedback
                            {isExpanded ? <ChevronUp className="w-4 h-4 ml-1" /> : <ChevronDown className="w-4 h-4 ml-1" />}
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Expanded Feedback */}
                    {hasFeedback && isExpanded && (
                      <div className="border-t border-[#E5E5E5] p-5 md:p-6 bg-[#F0FDF4] animate-fade-in" data-testid={`feedback-content-${week.week_number}`}>
                        {/* Week Materials - downloadable */}
                        {week.materials && week.materials.length > 0 && (
                          <div className="mb-4 pb-3 border-b border-[#BBF7D0]">
                            <p className="text-xs font-medium text-[#065F46] uppercase tracking-wide mb-2">Week Materials</p>
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
                                  className="inline-flex items-center gap-1.5 text-xs bg-white border border-[#BBF7D0] text-[#065F46] rounded-lg px-2.5 py-1.5 hover:bg-[#D1FAE5] transition-colors"
                                  data-testid={`download-material-${mat.material_id}`}
                                >
                                  <FileText className="w-3 h-3" />
                                  {mat.file_name}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <CheckCircle className="w-4 h-4 text-[#065F46]" />
                            <span className="text-sm font-medium text-[#065F46]">Instructor Feedback</span>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              setChatOpen({
                                submissionId: week.submission.submission_id,
                                weekNumber: week.week_number
                              });
                            }}
                            className="border-[#065F46] text-[#065F46] hover:bg-[#D1FAE5] rounded-lg"
                            data-testid={`ask-coach-max-${week.week_number}`}
                          >
                            <MessageCircle className="w-4 h-4 mr-1.5" />
                            Ask Coach Max
                          </Button>
                        </div>
                        <div className="text-sm text-[#1A1A1A] whitespace-pre-wrap leading-relaxed pl-6">
                          {week.feedback}
                        </div>
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
                    <File className="w-5 h-5 text-[#065F46]" />
                    <span className="text-sm text-[#1A1A1A]">{uploadFile.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload className="w-10 h-10 text-[#C4C4C4] mx-auto mb-2" />
                    <p className="text-sm text-[#888]">Click to upload your homework</p>
                    <p className="text-xs text-[#C4C4C4] mt-1">PDF or DOCX only</p>
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
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUpload(false)}>
              Cancel
            </Button>
            <Button
              data-testid="submit-homework-btn"
              onClick={handleSubmit}
              disabled={submitting}
              className="bg-[#065F46] text-white hover:bg-[#064E3B]"
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

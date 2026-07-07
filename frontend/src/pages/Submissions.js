import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { 
  BookOpen, 
  ArrowLeft,
  Upload,
  CheckCircle,
  Clock,
  Sparkles,
  FileEdit,
  Mail,
  Send
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function Submissions() {
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState(null);

  useEffect(() => {
    if (!authLoading && user) {
      fetchSubmissions();
    }
  }, [authLoading, user]);

  const fetchSubmissions = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/submissions`);
      setSubmissions(res.data);
    } catch (error) {
      toast.error('Failed to load submissions');
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (submissionId) => {
    setReviewing(submissionId);
    try {
      await axios.post(
        `${API_URL}/api/submissions/${submissionId}/review`,
        {},
      );
      toast.success('AI feedback generated! Click to review and send.');
      fetchSubmissions();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Review failed');
    } finally {
      setReviewing(null);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const pendingSubmissions = submissions.filter(s => s.status === 'pending');
  const draftSubmissions = submissions.filter(s => s.status === 'draft');
  const sentSubmissions = submissions.filter(s => s.status === 'sent' || s.feedback_sent);

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="submissions-page">
      {/* Header */}
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 md:px-12 h-16 flex items-center gap-4">
          <Link 
            to="/dashboard"
            className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-[#333333]" />
          </Link>
          <div>
            <h1 className="text-lg font-medium text-[#000000]">
              {isInstructor ? 'Student Submissions' : 'My Submissions'}
            </h1>
            <p className="text-sm text-[#666666]">
              {isInstructor ? 'Review homework and send feedback' : 'Track your homework submissions'}
            </p>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 md:px-12 py-8">
        {/* Pending */}
        {pendingSubmissions.length > 0 && (
          <div className="mb-8">
            <h2 className="text-xl font-light text-[#000000] mb-4 flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#7CBAE6]" />
              {isInstructor ? 'Needs AI Review' : 'Awaiting Review'}
              <span className="text-sm bg-[#FEF9C3] text-[#1A75BA] px-2 py-0.5 rounded-full">{pendingSubmissions.length}</span>
            </h2>
            <div className="space-y-3">
              {pendingSubmissions.map((sub) => (
                <Card 
                  key={sub.submission_id}
                  className="bg-white border-[#B8D4E8]"
                  data-testid={`submission-${sub.submission_id}`}
                >
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#7CBAE6] rounded-lg flex items-center justify-center">
                        <Upload className="w-5 h-5 text-[#000000]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#000000]">
                          {isInstructor ? sub.student?.name : sub.material?.title}
                        </p>
                        <p className="text-sm text-[#666666]">
                          {isInstructor 
                            ? `${sub.material?.title || 'Homework'} • Week ${sub.material?.week_number || '?'}`
                            : `Week ${sub.material?.week_number || '?'} • Submitted`
                          }
                        </p>
                      </div>
                    </div>
                    {isInstructor && (
                      <Button 
                        onClick={() => handleReview(sub.submission_id)}
                        disabled={reviewing === sub.submission_id}
                        className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
                        data-testid={`review-btn-${sub.submission_id}`}
                      >
                        {reviewing === sub.submission_id ? (
                          <>
                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                            Generating...
                          </>
                        ) : (
                          <>
                            <Sparkles className="w-4 h-4 mr-2" />
                            Generate AI Feedback
                          </>
                        )}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Draft - Needs Review */}
        {isInstructor && draftSubmissions.length > 0 && (
          <div className="mb-8">
            <h2 className="text-xl font-light text-[#000000] mb-4 flex items-center gap-2">
              <FileEdit className="w-5 h-5 text-[#22438E]" />
              Ready to Review & Send
              <span className="text-sm bg-[#E1F0FF] text-[#22438E] px-2 py-0.5 rounded-full">{draftSubmissions.length}</span>
            </h2>
            <div className="space-y-3">
              {draftSubmissions.map((sub) => (
                <Card 
                  key={sub.submission_id}
                  className="bg-[#F0F9FF] border-[#BAE6FD] cursor-pointer hover:shadow-sm transition-shadow"
                  onClick={() => navigate(`/submission/${sub.submission_id}`)}
                  data-testid={`draft-${sub.submission_id}`}
                >
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
                        <FileEdit className="w-5 h-5 text-[#22438E]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#000000]">{sub.student?.name}</p>
                        <p className="text-sm text-[#666666]">
                          {sub.material?.title || 'Homework'} • Week {sub.material?.week_number || '?'}
                        </p>
                      </div>
                    </div>
                    <Button 
                      className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/submission/${sub.submission_id}`);
                      }}
                    >
                      <Send className="w-4 h-4 mr-2" />
                      Review & Send
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Sent */}
        {sentSubmissions.length > 0 && (
          <div>
            <h2 className="text-xl font-light text-[#000000] mb-4 flex items-center gap-2">
              <Mail className="w-5 h-5 text-[#22438E]" />
              {isInstructor ? 'Feedback Sent' : 'Received Feedback'}
            </h2>
            <div className="space-y-4">
              {sentSubmissions.map((sub) => (
                <Card 
                  key={sub.submission_id}
                  className="bg-white border-[#B8D4E8] cursor-pointer hover:shadow-sm transition-shadow"
                  onClick={() => navigate(`/submission/${sub.submission_id}`)}
                  data-testid={`sent-${sub.submission_id}`}
                >
                  <CardContent className="p-6">
                    <div className="flex items-start gap-4 mb-4">
                      <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center flex-shrink-0">
                        <CheckCircle className="w-5 h-5 text-[#22438E]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#000000]">
                          {isInstructor ? sub.student?.name : sub.material?.title}
                        </p>
                        <p className="text-sm text-[#666666]">
                          {isInstructor 
                            ? `${sub.material?.title || 'Homework'} • Week ${sub.material?.week_number || '?'}`
                            : `Week ${sub.material?.week_number || '?'}`
                          }
                        </p>
                      </div>
                    </div>
                    {(sub.instructor_feedback || sub.ai_feedback) && (
                      <div className="bg-[#F0FDF4] border border-[#B8D4E8] rounded-lg p-4">
                        <p className="text-sm text-[#166534] feedback-letter line-clamp-3">
                          {(sub.instructor_feedback || sub.ai_feedback).substring(0, 200)}...
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {submissions.length === 0 && (
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <Upload className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#000000] mb-2">No submissions yet</h3>
              <p className="text-[#333333]">
                {isInstructor 
                  ? 'Student submissions will appear here' 
                  : 'Submit your first homework to get AI feedback'}
              </p>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

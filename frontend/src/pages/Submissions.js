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
  Sparkles
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
      const res = await axios.get(`${API_URL}/api/submissions`, { withCredentials: true });
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
      const res = await axios.post(
        `${API_URL}/api/submissions/${submissionId}/review`,
        {},
        { withCredentials: true }
      );
      toast.success('AI review complete!');
      fetchSubmissions();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Review failed');
    } finally {
      setReviewing(null);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const pendingSubmissions = submissions.filter(s => s.status === 'pending');
  const reviewedSubmissions = submissions.filter(s => s.status === 'reviewed');

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="submissions-page">
      {/* Header */}
      <header className="bg-white border-b border-[#E5E5E5] sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 md:px-12 h-16 flex items-center gap-4">
          <Link 
            to="/dashboard"
            className="p-2 hover:bg-[#F2F0ED] rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-[#5A5A5A]" />
          </Link>
          <div>
            <h1 className="text-lg font-medium text-[#1A1A1A]">
              {isInstructor ? 'Student Submissions' : 'My Submissions'}
            </h1>
            <p className="text-sm text-[#888]">
              {isInstructor ? 'Review homework and provide AI feedback' : 'Track your homework submissions'}
            </p>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 md:px-12 py-8">
        {/* Pending */}
        {pendingSubmissions.length > 0 && (
          <div className="mb-8">
            <h2 className="text-xl font-light text-[#1A1A1A] mb-4 flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#FDE047]" />
              {isInstructor ? 'Pending Reviews' : 'Awaiting Review'}
            </h2>
            <div className="space-y-3">
              {pendingSubmissions.map((sub) => (
                <Card 
                  key={sub.submission_id}
                  className="bg-white border-[#E5E5E5]"
                  data-testid={`submission-${sub.submission_id}`}
                >
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#FDE047] rounded-lg flex items-center justify-center">
                        <Upload className="w-5 h-5 text-[#1A1A1A]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#1A1A1A]">
                          {isInstructor ? sub.student?.name : sub.material?.title}
                        </p>
                        <p className="text-sm text-[#888]">
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
                        className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                        data-testid={`review-btn-${sub.submission_id}`}
                      >
                        {reviewing === sub.submission_id ? (
                          <>
                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                            Reviewing...
                          </>
                        ) : (
                          <>
                            <Sparkles className="w-4 h-4 mr-2" />
                            Generate AI Review
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

        {/* Reviewed */}
        {reviewedSubmissions.length > 0 && (
          <div>
            <h2 className="text-xl font-light text-[#1A1A1A] mb-4 flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-[#065F46]" />
              Reviewed
            </h2>
            <div className="space-y-4">
              {reviewedSubmissions.map((sub) => (
                <Card 
                  key={sub.submission_id}
                  className="bg-white border-[#E5E5E5] cursor-pointer hover:shadow-sm transition-shadow"
                  onClick={() => navigate(`/submission/${sub.submission_id}`)}
                  data-testid={`reviewed-${sub.submission_id}`}
                >
                  <CardContent className="p-6">
                    <div className="flex items-start gap-4 mb-4">
                      <div className="w-10 h-10 bg-[#D1FAE5] rounded-lg flex items-center justify-center flex-shrink-0">
                        <CheckCircle className="w-5 h-5 text-[#065F46]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#1A1A1A]">
                          {isInstructor ? sub.student?.name : sub.material?.title}
                        </p>
                        <p className="text-sm text-[#888]">
                          {isInstructor 
                            ? `${sub.material?.title || 'Homework'} • Week ${sub.material?.week_number || '?'}`
                            : `Week ${sub.material?.week_number || '?'}`
                          }
                        </p>
                      </div>
                    </div>
                    {sub.ai_feedback && (
                      <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-lg p-4">
                        <p className="text-sm text-[#166534] feedback-letter line-clamp-3">
                          {sub.ai_feedback.substring(0, 200)}...
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
          <Card className="bg-white border-[#E5E5E5] border-dashed">
            <CardContent className="p-12 text-center">
              <Upload className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No submissions yet</h3>
              <p className="text-[#5A5A5A]">
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

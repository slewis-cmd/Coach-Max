import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { 
  ArrowLeft,
  File,
  CheckCircle,
  Clock,
  Sparkles,
  User
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function SubmissionDetail() {
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [submission, setSubmission] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    if (!authLoading && user) {
      fetchSubmission();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, submissionId]);

  const fetchSubmission = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/submissions/${submissionId}`, { withCredentials: true });
      setSubmission(res.data);
    } catch (error) {
      toast.error('Failed to load submission');
      navigate('/submissions');
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async () => {
    setReviewing(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/submissions/${submissionId}/review`,
        {},
        { withCredentials: true }
      );
      toast.success('AI review complete!');
      fetchSubmission();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Review failed');
    } finally {
      setReviewing(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!submission) return null;

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="submission-detail">
      {/* Header */}
      <header className="bg-white border-b border-[#E5E5E5] sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/submissions"
              className="p-2 hover:bg-[#F2F0ED] rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-[#5A5A5A]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#1A1A1A]">
                {submission.material?.title || 'Homework Submission'}
              </h1>
              <p className="text-sm text-[#888]">Week {submission.material?.week_number}</p>
            </div>
          </div>
          
          {isInstructor && submission.status === 'pending' && (
            <Button 
              onClick={handleReview}
              disabled={reviewing}
              className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
              data-testid="generate-review-btn"
            >
              {reviewing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4 mr-2" />
                  Generate AI Review
                </>
              )}
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 md:px-12 py-8">
        {/* Submission Info */}
        <Card className="bg-white border-[#E5E5E5] mb-6">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                {isInstructor && submission.student && (
                  <>
                    {submission.student.picture ? (
                      <img 
                        src={submission.student.picture} 
                        alt={submission.student.name}
                        className="w-12 h-12 rounded-full"
                      />
                    ) : (
                      <div className="w-12 h-12 bg-[#F2F0ED] rounded-full flex items-center justify-center">
                        <User className="w-6 h-6 text-[#888]" />
                      </div>
                    )}
                    <div>
                      <p className="font-medium text-[#1A1A1A]">{submission.student.name}</p>
                      <p className="text-sm text-[#888]">{submission.student.email}</p>
                    </div>
                  </>
                )}
                {!isInstructor && (
                  <div>
                    <p className="font-medium text-[#1A1A1A]">{submission.material?.title}</p>
                    <p className="text-sm text-[#888]">Week {submission.material?.week_number}</p>
                  </div>
                )}
              </div>
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                submission.status === 'reviewed' 
                  ? 'bg-[#D1FAE5] text-[#065F46]' 
                  : 'bg-[#FEF9C3] text-[#854D0E]'
              }`}>
                {submission.status === 'reviewed' ? (
                  <CheckCircle className="w-4 h-4" />
                ) : (
                  <Clock className="w-4 h-4" />
                )}
                {submission.status === 'reviewed' ? 'Reviewed' : 'Pending Review'}
              </div>
            </div>
            
            <div className="flex items-center gap-2 text-sm text-[#5A5A5A]">
              <File className="w-4 h-4" />
              {submission.file_name}
            </div>
          </CardContent>
        </Card>

        {/* AI Feedback */}
        {submission.ai_feedback ? (
          <div className="animate-fade-in">
            <h2 className="text-xl font-light text-[#1A1A1A] mb-4 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-[#065F46]" />
              AI Feedback
            </h2>
            <Card className="bg-[#F0FDF4] border-[#BBF7D0]">
              <CardContent className="p-8">
                <div className="feedback-letter text-[#166534] whitespace-pre-wrap leading-relaxed">
                  {submission.ai_feedback}
                </div>
                <div className="mt-6 pt-6 border-t border-[#BBF7D0] text-right">
                  <p className="text-sm text-[#065F46] italic">— Your AI Tutor</p>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card className="bg-white border-[#E5E5E5] border-dashed">
            <CardContent className="p-12 text-center">
              <div className="w-16 h-16 bg-[#FDE047] rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse-soft">
                <Sparkles className="w-8 h-8 text-[#1A1A1A]" />
              </div>
              <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">Awaiting Review</h3>
              <p className="text-[#5A5A5A]">
                {isInstructor 
                  ? 'Click "Generate AI Review" to provide feedback'
                  : 'Your instructor will review this submission soon'}
              </p>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

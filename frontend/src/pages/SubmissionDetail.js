import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { 
  ArrowLeft,
  File,
  CheckCircle,
  Clock,
  Sparkles,
  User,
  Edit3,
  Send,
  Mail,
  FileEdit,
  RotateCcw,
  RefreshCw,
  FileDown
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
  const [editedFeedback, setEditedFeedback] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [allowingResubmission, setAllowingResubmission] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!authLoading && user) {
      fetchSubmission();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, submissionId]);

  const fetchSubmission = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/submissions/${submissionId}`);
      setSubmission(res.data);
      // Set edited feedback to instructor's version if exists, otherwise AI version
      setEditedFeedback(res.data.instructor_feedback || res.data.ai_feedback || '');
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
      );
      toast.success('AI feedback generated! Review and edit before sending.');
      setEditedFeedback(res.data.feedback);
      setIsEditing(true);
      fetchSubmission();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Review failed');
    } finally {
      setReviewing(false);
    }
  };

  const handleSaveFeedback = async () => {
    if (!editedFeedback.trim()) {
      toast.error('Feedback cannot be empty');
      return;
    }
    
    setSaving(true);
    try {
      await axios.put(
        `${API_URL}/api/submissions/${submissionId}/feedback`,
        { feedback: editedFeedback },
      );
      toast.success('Feedback saved');
      setIsEditing(false);
      fetchSubmission();
    } catch (error) {
      toast.error('Failed to save feedback');
    } finally {
      setSaving(false);
    }
  };

  const handleSendFeedback = async () => {
    if (!window.confirm('Send this feedback to the student via email? This action cannot be undone.')) {
      return;
    }
    
    setSending(true);
    try {
      await axios.post(
        `${API_URL}/api/submissions/${submissionId}/send-feedback`,
        {},
      );
      toast.success('Feedback sent to student!');
      fetchSubmission();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send feedback');
    } finally {
      setSending(false);
    }
  };

  const handleAllowResubmission = async () => {
    if (!window.confirm('Allow this student to resubmit their homework? They will be notified via email.')) {
      return;
    }
    
    setAllowingResubmission(true);
    try {
      await axios.post(
        `${API_URL}/api/submissions/${submissionId}/allow-resubmission`,
        {},
      );
      toast.success('Resubmission allowed. Student has been notified.');
      fetchSubmission();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to allow resubmission');
    } finally {
      setAllowingResubmission(false);
    }
  };

  const handleExportPDF = async () => {
    setExporting(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/submissions/${submissionId}/export-pdf`,
        {},
        { responseType: 'blob' }
      );
      // Download the PDF for instructor
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const disposition = response.headers['content-disposition'];
      const filename = disposition
        ? disposition.split('filename=')[1]?.replace(/"/g, '')
        : `Feedback_${submissionId}.pdf`;
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('PDF exported and emailed to student!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to export PDF');
    } finally {
      setExporting(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!submission) return null;

  const currentFeedback = submission.instructor_feedback || submission.ai_feedback;
  const isDraft = submission.status === 'draft';
  const isSent = submission.status === 'sent' || submission.feedback_sent;

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="submission-detail">
      {/* Header */}
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/submissions"
              className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-[#333333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000000]">
                {submission.material?.title || 'Homework Submission'}
              </h1>
              <p className="text-sm text-[#666666]">Week {submission.material?.week_number}</p>
            </div>
          </div>
          
          {isInstructor && submission.status === 'pending' && (
            <Button 
              onClick={handleReview}
              disabled={reviewing}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
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
                  Generate AI Feedback
                </>
              )}
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 md:px-12 py-8">
        {/* Submission Info */}
        <Card className="bg-white border-[#B8D4E8] mb-6">
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
                      <div className="w-12 h-12 bg-[#D0E6F9] rounded-full flex items-center justify-center">
                        <User className="w-6 h-6 text-[#666666]" />
                      </div>
                    )}
                    <div>
                      <p className="font-medium text-[#000000]">{submission.student.name}</p>
                      <p className="text-sm text-[#666666]">{submission.student.email}</p>
                    </div>
                  </>
                )}
                {!isInstructor && (
                  <div>
                    <p className="font-medium text-[#000000]">{submission.material?.title}</p>
                    <p className="text-sm text-[#666666]">Week {submission.material?.week_number}</p>
                  </div>
                )}
              </div>
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                isSent || isDraft
                  ? 'bg-[#E1F0FF] text-[#22438E]' 
                  : 'bg-[#FEF9C3] text-[#1A75BA]'
              }`}>
                {isSent ? (
                  <>
                    <Mail className="w-4 h-4" />
                    Sent to Student
                  </>
                ) : isDraft ? (
                  <>
                    <FileEdit className="w-4 h-4" />
                    Draft - Review Required
                  </>
                ) : (
                  <>
                    <Clock className="w-4 h-4" />
                    Pending Review
                  </>
                )}
              </div>
            </div>
            
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-[#333333]">
                <File className="w-4 h-4" />
                {submission.file_name}
                {submission.resubmission_count > 0 && (
                  <span className="bg-[#E1F0FF] text-[#22438E] px-2 py-0.5 rounded text-xs ml-2">
                    Resubmission #{submission.resubmission_count}
                  </span>
                )}
              </div>
              {isInstructor && isSent && !submission.resubmission_allowed && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleAllowResubmission}
                  disabled={allowingResubmission}
                  className="border-[#B8D4E8] text-[#333333]"
                  data-testid="allow-resubmission-btn"
                >
                  {allowingResubmission ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <RotateCcw className="w-4 h-4 mr-2" />
                      Allow Resubmission
                    </>
                  )}
                </Button>
              )}
              {submission.resubmission_allowed && (
                <span className="text-sm text-[#22438E] flex items-center gap-1">
                  <RotateCcw className="w-4 h-4" />
                  Resubmission allowed
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        {/* AI Feedback / Editor */}
        {currentFeedback || isDraft ? (
          <div className="animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-light text-[#000000] flex items-center gap-2">
                {isSent ? (
                  <>
                    <CheckCircle className="w-5 h-5 text-[#22438E]" />
                    Feedback Sent
                  </>
                ) : (
                  <>
                    <Sparkles className="w-5 h-5 text-[#22438E]" />
                    {isEditing ? 'Edit Feedback' : 'AI Feedback (Draft)'}
                  </>
                )}
              </h2>
              
              {isInstructor && !isSent && currentFeedback && !isEditing && (
                <div className="flex items-center gap-2">
                  <Button 
                    variant="outline"
                    onClick={() => {
                      setEditedFeedback(currentFeedback);
                      setIsEditing(true);
                    }}
                    className="border-[#B8D4E8]"
                    data-testid="edit-feedback-btn"
                  >
                    <Edit3 className="w-4 h-4 mr-2" />
                    Edit
                  </Button>
                  <Button 
                    variant="outline"
                    onClick={handleExportPDF}
                    disabled={exporting}
                    className="border-[#1A75BA] text-[#1A75BA] hover:bg-[#E1F0FF]"
                    data-testid="export-pdf-btn"
                  >
                    {exporting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-[#1A75BA] border-t-transparent rounded-full animate-spin mr-2"></div>
                        Exporting...
                      </>
                    ) : (
                      <>
                        <FileDown className="w-4 h-4 mr-2" />
                        Export & Email PDF
                      </>
                    )}
                  </Button>
                  <Button 
                    onClick={handleSendFeedback}
                    disabled={sending}
                    className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
                    data-testid="send-feedback-btn"
                  >
                    {sending ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                        Sending...
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4 mr-2" />
                        Send to Student
                      </>
                    )}
                  </Button>
                </div>
              )}
              
              {isInstructor && isSent && currentFeedback && (
                <Button 
                  variant="outline"
                  onClick={handleExportPDF}
                  disabled={exporting}
                  className="border-[#1A75BA] text-[#1A75BA] hover:bg-[#E1F0FF]"
                  data-testid="export-pdf-btn"
                >
                  {exporting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-[#1A75BA] border-t-transparent rounded-full animate-spin mr-2"></div>
                      Exporting...
                    </>
                  ) : (
                    <>
                      <FileDown className="w-4 h-4 mr-2" />
                      Export & Email PDF
                    </>
                  )}
                </Button>
              )}
            </div>

            {isEditing ? (
              <Card className="bg-white border-[#B8D4E8]">
                <CardContent className="p-6">
                  <Label className="text-sm text-[#333333] mb-2 block">
                    Review and edit the AI-generated feedback before sending to the student
                  </Label>
                  <Textarea
                    value={editedFeedback}
                    onChange={(e) => setEditedFeedback(e.target.value)}
                    className="min-h-[300px] mb-4 font-normal"
                    placeholder="Enter feedback for the student..."
                    data-testid="feedback-editor"
                  />
                  <div className="flex items-center justify-end gap-2">
                    <Button 
                      variant="outline"
                      onClick={() => {
                        setIsEditing(false);
                        setEditedFeedback(currentFeedback);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button 
                      onClick={handleSaveFeedback}
                      disabled={saving}
                      className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
                      data-testid="save-feedback-btn"
                    >
                      {saving ? 'Saving...' : 'Save Changes'}
                    </Button>
                    <Button 
                      onClick={async () => {
                        await handleSaveFeedback();
                        if (editedFeedback.trim()) {
                          handleSendFeedback();
                        }
                      }}
                      disabled={saving || sending}
                      className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
                    >
                      <Send className="w-4 h-4 mr-2" />
                      Save & Send
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card className={isSent ? "bg-[#F0FDF4] border-[#B8D4E8]" : "bg-[#F0F9FF] border-[#BAE6FD]"}>
                <CardContent className="p-8">
                  <div className="feedback-letter text-[#166534] whitespace-pre-wrap leading-relaxed">
                    {currentFeedback}
                  </div>
                  <div className="mt-6 pt-6 border-t border-[#B8D4E8] text-right">
                    <p className="text-sm text-[#22438E] italic">
                      {isSent ? '— Feedback sent to student' : '— Draft (Not yet sent to student)'}
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <div className="w-16 h-16 bg-[#7CBAE6] rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse-soft">
                <Sparkles className="w-8 h-8 text-[#000000]" />
              </div>
              <h3 className="text-lg font-medium text-[#000000] mb-2">Awaiting Review</h3>
              <p className="text-[#333333]">
                {isInstructor 
                  ? 'Click "Generate AI Feedback" to create a draft for review'
                  : 'Your instructor will review this submission soon'}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Workflow info for instructors */}
        {isInstructor && !isSent && (
          <div className="mt-6 p-4 bg-[#D0E6F9] rounded-lg">
            <h3 className="text-sm font-medium text-[#000000] mb-2">Review Workflow</h3>
            <ol className="text-sm text-[#333333] space-y-1">
              <li className={`flex items-center gap-2 ${currentFeedback ? 'text-[#22438E]' : ''}`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${currentFeedback ? 'bg-[#E1F0FF] text-[#22438E]' : 'bg-[#B8D4E8] text-[#666666]'}`}>1</span>
                Generate AI feedback
              </li>
              <li className={`flex items-center gap-2 ${submission.instructor_feedback ? 'text-[#22438E]' : ''}`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${submission.instructor_feedback ? 'bg-[#E1F0FF] text-[#22438E]' : 'bg-[#B8D4E8] text-[#666666]'}`}>2</span>
                Review and edit feedback
              </li>
              <li className={`flex items-center gap-2 ${isSent ? 'text-[#22438E]' : ''}`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${isSent ? 'bg-[#E1F0FF] text-[#22438E]' : 'bg-[#B8D4E8] text-[#666666]'}`}>3</span>
                Send feedback to student via email
              </li>
            </ol>
          </div>
        )}
      </main>
    </div>
  );
}

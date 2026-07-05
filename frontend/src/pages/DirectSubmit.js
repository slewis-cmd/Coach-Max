import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../components/ui/select';
import { Upload, CheckCircle, FileText, ArrowLeft, LogIn, FolderOpen } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function DirectSubmit() {
  const { materialId } = useParams();
  const [searchParams] = useSearchParams();
  const cohortParam = searchParams.get('cohort');
  const { user, isAuthenticated, loading: authLoading, login } = useAuth();

  const [info, setInfo] = useState(null);
  const [loadingInfo, setLoadingInfo] = useState(true);
  const [selectedCohort, setSelectedCohort] = useState(cohortParam || '');
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const fetchInfo = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/submit-link/${materialId}`);
        setInfo(res.data);
        if (res.data.cohorts?.length === 1) {
          setSelectedCohort(res.data.cohorts[0].cohort_id);
        }
        if (cohortParam) {
          setSelectedCohort(cohortParam);
        }
      } catch {
        setInfo(null);
      } finally {
        setLoadingInfo(false);
      }
    };
    fetchInfo();
  }, [materialId, cohortParam]);

  const handleSubmit = async () => {
    if (!file) { toast.error('Please select a file'); return; }
    if (!selectedCohort) { toast.error('Please select your cohort'); return; }

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(
        `${API_URL}/api/materials/${materialId}/submit?cohort_id=${encodeURIComponent(selectedCohort)}`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      setSubmitted(true);
      toast.success('Homework submitted successfully!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || loadingInfo) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!info) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6">
        <Card className="bg-white border-[#B8D4E8] max-w-md w-full">
          <CardContent className="p-8 text-center">
            <FileText className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
            <h2 className="text-xl font-medium text-[#000] mb-2">Assignment Not Found</h2>
            <p className="text-[#666] mb-4">This submission link may be invalid or expired.</p>
            <Link to="/">
              <Button variant="outline" className="border-[#22438E] text-[#22438E]">Go Home</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6" data-testid="direct-submit-page">
      <Card className="bg-white border-[#B8D4E8] max-w-lg w-full shadow-sm">
        <CardContent className="p-8">
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-[#22438E]" />
            </div>
            <div>
              <h1 className="text-xl font-medium text-[#000]">{info.title}</h1>
              <p className="text-sm text-[#666]">Week {info.week_number} Homework</p>
            </div>
          </div>

          {/* Not logged in */}
          {!isAuthenticated && (
            <div className="text-center py-6">
              <LogIn className="w-10 h-10 text-[#22438E] mx-auto mb-3" />
              <h3 className="text-lg font-medium text-[#000] mb-2">Sign in to submit</h3>
              <p className="text-sm text-[#666] mb-4">You need to sign in with your Google account to upload your homework.</p>
              <Button onClick={login} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] w-full" data-testid="login-to-submit">
                Sign in with Google
              </Button>
            </div>
          )}

          {/* Submitted successfully */}
          {isAuthenticated && submitted && (
            <div className="text-center py-6">
              <CheckCircle className="w-14 h-14 text-[#22438E] mx-auto mb-3" />
              <h3 className="text-xl font-medium text-[#000] mb-2">Submitted!</h3>
              <p className="text-sm text-[#666] mb-4">
                Your homework has been submitted for review. Coach Max will provide AI feedback shortly.
              </p>
              <div className="flex justify-center">
                <Link to="/dashboard">
                  <Button className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">Go to Dashboard</Button>
                </Link>
              </div>
            </div>
          )}

          {/* Upload form */}
          {isAuthenticated && !submitted && (
            <div className="space-y-4">
              <p className="text-sm text-[#666]">
                Hi <strong>{user?.name}</strong>! Upload your completed homework below.
              </p>

              {info.drive_folder_url && (
                <div className="rounded-lg border border-[#22438E] bg-[#E1F0FF] p-4" data-testid="drive-upload-hint">
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center flex-shrink-0">
                      <FolderOpen className="w-5 h-5 text-[#22438E]" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-[#000000]">Step 1 · Upload to Google Drive</p>
                      <p className="text-xs text-[#333333] mt-0.5">
                        Save your homework in the shared class Drive folder, then upload the same file here so {info.title ? '' : 'the AI tutor'} can review it.
                      </p>
                      <a
                        href={info.drive_folder_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 mt-2 text-xs font-medium text-white bg-[#22438E] hover:bg-[#1A3A7A] px-3 py-1.5 rounded-md"
                        data-testid="drive-folder-link"
                      >
                        <FolderOpen className="w-3.5 h-3.5" />
                        Open Drive Folder
                      </a>
                    </div>
                  </div>
                </div>
              )}

              {/* Cohort selector (if multiple) */}
              {info.cohorts?.length > 1 && (
                <div>
                  <label className="text-sm font-medium text-[#000] block mb-1">Your Cohort</label>
                  <Select value={selectedCohort} onValueChange={setSelectedCohort}>
                    <SelectTrigger><SelectValue placeholder="Select your cohort..." /></SelectTrigger>
                    <SelectContent>
                      {info.cohorts.map(c => (
                        <SelectItem key={c.cohort_id} value={c.cohort_id}>{c.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* File upload */}
              <div>
                <label htmlFor="direct-submit-file" className="flex flex-col items-center gap-2 p-6 border-2 border-dashed border-[#B8D4E8] rounded-lg cursor-pointer hover:border-[#22438E] hover:bg-[#E1F0FF] transition-colors">
                  <Upload className="w-8 h-8 text-[#666]" />
                  <span className="text-sm font-medium text-[#000]">
                    {file ? file.name : 'Click to select your homework file'}
                  </span>
                  <span className="text-xs text-[#666]">PDF or DOCX</span>
                </label>
                <input id="direct-submit-file" type="file" accept=".pdf,.docx,.doc"
                  className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)}
                  data-testid="direct-submit-file-input" />
              </div>

              <Button
                onClick={handleSubmit}
                disabled={submitting || !file}
                className="bg-[#22438E] text-white hover:bg-[#1A3A7A] w-full"
                data-testid="direct-submit-btn"
              >
                {submitting ? 'Submitting...' : 'Submit Homework'}
              </Button>
            </div>
          )}

          {/* Footer */}
          <div className="mt-6 pt-4 border-t border-[#B8D4E8] text-center">
            <p className="text-xs text-[#666]">Powered by <strong>The Boost Pad</strong> &middot; Coach Max AI Tutor</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

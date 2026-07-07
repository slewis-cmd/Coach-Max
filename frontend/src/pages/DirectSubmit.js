import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../components/ui/select';
import { Upload, CheckCircle, FileText, LogIn, FolderOpen, ListChecks, Mic, Presentation, Star } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { getSubmissionTypeConfig } from '../config/submissionTypes';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ICONS = { Mic, Presentation, FileText, ListChecks };

export default function DirectSubmit() {
  const { materialId } = useParams();
  const [searchParams] = useSearchParams();
  const cohortParam = searchParams.get('cohort');
  const { user, isAuthenticated, loading: authLoading, login } = useAuth();

  const [info, setInfo] = useState(null);
  const [loadingInfo, setLoadingInfo] = useState(true);
  const [selectedCohort, setSelectedCohort] = useState(cohortParam || '');
  const [file, setFile] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const fetchInfo = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/submit-link/${materialId}`);
        setInfo(res.data);
        if (res.data.cohorts?.length === 1) setSelectedCohort(res.data.cohorts[0].cohort_id);
        if (cohortParam) setSelectedCohort(cohortParam);
      } catch {
        setInfo(null);
      } finally {
        setLoadingInfo(false);
      }
    };
    fetchInfo();
  }, [materialId, cohortParam]);

  const config = getSubmissionTypeConfig(info?.submission_type);
  const isQuestionnaire = info?.submission_type === 'business_questionnaire';
  const fields = info?.questionnaire_fields || [];

  const missingRequired = isQuestionnaire && fields.some(
    (f) => f.required && !(answers[f.id] || '').trim()
  );

  const validateAnswers = () => {
    for (const f of fields) {
      if (f.required && !(answers[f.id] || '').trim()) {
        toast.error(`Please answer: ${f.label}`);
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async () => {
    if (!selectedCohort) { toast.error('Please select your cohort'); return; }
    if (isQuestionnaire) {
      if (!validateAnswers()) return;
    } else {
      if (!file) { toast.error('Please select a file'); return; }
    }

    setSubmitting(true);
    try {
      const formData = new FormData();
      if (isQuestionnaire) {
        formData.append('questionnaire_answers', JSON.stringify(answers));
      } else {
        formData.append('file', file);
      }
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

  const HeaderIcon = ICONS[config?.icon] || FileText;
  const acceptAttr = config?.accept || '.pdf,.docx,.doc';
  const extHint = config?.extensions?.length ? config.extensions.map(e => e.toUpperCase()).join(', ') : 'PDF or DOCX';

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6" data-testid="direct-submit-page">
      <Card className="bg-white border-[#B8D4E8] max-w-lg w-full shadow-sm">
        <CardContent className="p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
              <HeaderIcon className="w-6 h-6 text-[#22438E]" />
            </div>
            <div>
              <h1 className="text-xl font-medium text-[#000]" data-testid="direct-submit-title">{info.title}</h1>
              <p className="text-sm text-[#666]">
                Week {info.week_number}{config ? ` · ${config.label}` : ' Homework'}
              </p>
            </div>
          </div>

          {!isAuthenticated && (
            <div className="text-center py-6">
              <LogIn className="w-10 h-10 text-[#22438E] mx-auto mb-3" />
              <h3 className="text-lg font-medium text-[#000] mb-2">Sign in to submit</h3>
              <p className="text-sm text-[#666] mb-4">You need to sign in with your Google account to submit.</p>
              <Button onClick={login} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] w-full" data-testid="login-to-submit">
                Sign in with Google
              </Button>
            </div>
          )}

          {isAuthenticated && submitted && (
            <div className="text-center py-6">
              <CheckCircle className="w-14 h-14 text-[#22438E] mx-auto mb-3" />
              <h3 className="text-xl font-medium text-[#000] mb-2">Submitted!</h3>
              <p className="text-sm text-[#666] mb-4">Your submission is in. Coach Max will provide AI feedback shortly.</p>
              <Link to="/dashboard">
                <Button className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">Go to Dashboard</Button>
              </Link>
            </div>
          )}

          {isAuthenticated && !submitted && (
            <div className="space-y-4">
              <p className="text-sm text-[#666]">Hi <strong>{user?.name}</strong>! {isQuestionnaire ? 'Answer the questions below.' : 'Upload your completed homework.'}</p>

              {info.drive_folder_url && !isQuestionnaire && (
                <div className="rounded-lg border border-[#22438E] bg-[#E1F0FF] p-4" data-testid="drive-upload-hint">
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center flex-shrink-0">
                      <FolderOpen className="w-5 h-5 text-[#22438E]" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-[#000000]">Step 1 · Upload to Google Drive</p>
                      <p className="text-xs text-[#333333] mt-0.5">
                        Save your homework in the shared class Drive folder, then upload the same file here for AI review.
                      </p>
                      <a href={info.drive_folder_url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 mt-2 text-xs font-medium text-white bg-[#22438E] hover:bg-[#1A3A7A] px-3 py-1.5 rounded-md"
                        data-testid="drive-folder-link">
                        <FolderOpen className="w-3.5 h-3.5" /> Open Drive Folder
                      </a>
                    </div>
                  </div>
                </div>
              )}

              {info.cohorts?.length > 1 && (
                <div>
                  <Label className="text-sm font-medium text-[#000] block mb-1">Your Cohort</Label>
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

              {isQuestionnaire ? (
                <div className="space-y-4" data-testid="questionnaire-form">
                  {fields.length === 0 && (
                    <p className="text-sm text-[#666] italic">This questionnaire has no questions yet. Please check back later.</p>
                  )}
                  {fields.map((f, idx) => (
                    <div key={f.id} data-testid={`questionnaire-field-${f.id}`}>
                      <Label className="text-sm font-medium text-[#000]">
                        {idx + 1}. {f.label}
                        {f.required && <span className="text-red-600 ml-1">*</span>}
                      </Label>
                      {f.type === 'longtext' ? (
                        <Textarea
                          value={answers[f.id] || ''}
                          onChange={(e) => setAnswers({ ...answers, [f.id]: e.target.value })}
                          rows={4}
                          className="mt-1"
                          maxLength={5000}
                          data-testid={`questionnaire-input-${f.id}`}
                        />
                      ) : (
                        <Input
                          value={answers[f.id] || ''}
                          onChange={(e) => setAnswers({ ...answers, [f.id]: e.target.value })}
                          className="mt-1"
                          maxLength={5000}
                          data-testid={`questionnaire-input-${f.id}`}
                        />
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div>
                  <label htmlFor="direct-submit-file" className="flex flex-col items-center gap-2 p-6 border-2 border-dashed border-[#B8D4E8] rounded-lg cursor-pointer hover:border-[#22438E] hover:bg-[#E1F0FF] transition-colors">
                    <Upload className="w-8 h-8 text-[#666]" />
                    <span className="text-sm font-medium text-[#000]">
                      {file ? file.name : 'Click to select your file'}
                    </span>
                    <span className="text-xs text-[#666]">{extHint}</span>
                  </label>
                  <input id="direct-submit-file" type="file" accept={acceptAttr}
                    className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)}
                    data-testid="direct-submit-file-input" />
                </div>
              )}

              <Button
                onClick={handleSubmit}
                disabled={
                  submitting ||
                  (isQuestionnaire ? (fields.length === 0 || missingRequired) : !file)
                }
                className="bg-[#22438E] text-white hover:bg-[#1A3A7A] w-full"
                data-testid="direct-submit-btn"
              >
                {submitting ? 'Submitting...' : 'Submit'}
              </Button>
            </div>
          )}

          <div className="mt-6 pt-4 border-t border-[#B8D4E8] text-center">
            <p className="text-xs text-[#666]">Powered by <strong>The Boost Pad</strong> &middot; Coach Max AI Tutor</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


/**
 * Stable per-week-per-type link resolver: /submit/w/:week/:type
 * Looks up the actual material and redirects to /submit/{material_id}?cohort=...
 */
export function DirectSubmitStable() {
  const { week, submissionType } = useParams();
  const [searchParams] = useSearchParams();
  const cohortParam = searchParams.get('cohort');
  const navigate = useNavigate();
  const [error, setError] = useState(null);

  useEffect(() => {
    const resolve = async () => {
      try {
        const qs = cohortParam ? `?cohort_id=${encodeURIComponent(cohortParam)}` : '';
        const res = await axios.get(`${API_URL}/api/submit-link/w/${week}/${submissionType}${qs}`);
        const url = `/submit/${res.data.material_id}${cohortParam ? `?cohort=${encodeURIComponent(cohortParam)}` : ''}`;
        navigate(url, { replace: true });
      } catch (err) {
        setError(err?.response?.data?.detail || 'This week + submission type has no assignment yet.');
      }
    };
    resolve();
  }, [week, submissionType, cohortParam, navigate]);

  return _resolverView(error);
}


/**
 * Assignment + week resolver: /submit/a/:assignmentId/w/:week
 * Looks up the milestone and renders MilestoneSubmit inline.
 */
export function AssignmentMilestoneSubmit() {
  const { assignmentId, week } = useParams();
  const [searchParams] = useSearchParams();
  const cohortParam = searchParams.get('cohort');
  const { user, isAuthenticated, loading: authLoading, login } = useAuth();

  const [resolved, setResolved] = useState(null); // {assignment, milestone, cohort_id}
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const resolve = async () => {
      try {
        const qs = cohortParam ? `?cohort_id=${encodeURIComponent(cohortParam)}` : '';
        const linkRes = await axios.get(`${API_URL}/api/submit-link/a/${assignmentId}/w/${week}${qs}`);
        // Fetch the assignment itself (student is enrolled → has access)
        const cohortId = cohortParam || linkRes.data.cohort_id;
        const asgnListRes = await axios.get(`${API_URL}/api/cohorts/${cohortId}/assignments`);
        const asgn = (asgnListRes.data || []).find(a => a.assignment_id === assignmentId);
        if (!asgn) throw new Error('Assignment not accessible');
        const ms = (asgn.milestones || []).find(m => m.milestone_id === linkRes.data.milestone_id);
        if (!ms) throw new Error('Milestone not found');
        setResolved({ assignment: asgn, milestone: ms, cohort_id: cohortId });
      } catch (err) {
        setError(err?.response?.data?.detail || err?.message || 'Milestone not published yet.');
      }
    };
    if (!authLoading && isAuthenticated) resolve();
  }, [assignmentId, week, cohortParam, authLoading, isAuthenticated]);

  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6" data-testid="milestone-submit-signin">
        <Card className="bg-white border-[#B8D4E8] max-w-md w-full">
          <CardContent className="p-8 text-center">
            <LogIn className="w-10 h-10 text-[#22438E] mx-auto mb-3" />
            <h3 className="text-lg font-medium text-[#000] mb-2">Sign in to submit</h3>
            <p className="text-sm text-[#666] mb-4">You need to sign in with your Google account to submit your milestone.</p>
            <Button onClick={login} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] w-full" data-testid="milestone-login-btn">
              Sign in with Google
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) return _resolverView(error);
  if (!resolved) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const { assignment, milestone, cohort_id } = resolved;
  const config = getSubmissionTypeConfig(assignment.submission_type);
  const isQuestionnaire = assignment.submission_type === 'business_questionnaire';
  const fields = assignment.questionnaire_fields || [];
  const driveUrl = milestone.drive_folder_url_override || assignment.drive_folder_url || '';
  const HeaderIcon = ICONS[config?.icon] || FileText;
  const acceptAttr = config?.accept || '.pdf,.docx,.doc';
  const extHint = config?.extensions?.length ? config.extensions.map(e => e.toUpperCase()).join(', ') : 'PDF or DOCX';

  const missingRequired = isQuestionnaire && fields.some(
    (f) => f.required && !(answers[f.id] || '').trim()
  );

  const handleSubmit = async () => {
    if (isQuestionnaire) {
      for (const f of fields) {
        if (f.required && !(answers[f.id] || '').trim()) {
          toast.error(`Please answer: ${f.label}`);
          return;
        }
      }
    } else {
      if (!file) { toast.error('Please select a file'); return; }
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      if (isQuestionnaire) {
        fd.append('questionnaire_answers', JSON.stringify(answers));
      } else {
        fd.append('file', file);
      }
      const params = new URLSearchParams({
        cohort_id,
        assignment_id: assignment.assignment_id,
      });
      // Milestone-scoped submit endpoint (no material_id required)
      await axios.post(`${API_URL}/api/milestones/${milestone.milestone_id}/submit?${params.toString()}`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSubmitted(true);
      toast.success('Milestone submitted!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6" data-testid="milestone-submitted">
        <Card className="bg-white border-[#B8D4E8] max-w-md w-full">
          <CardContent className="p-8 text-center">
            <CheckCircle className="w-14 h-14 text-[#22438E] mx-auto mb-3" />
            <h3 className="text-xl font-medium text-[#000] mb-2">Submitted!</h3>
            <p className="text-sm text-[#666] mb-4">Coach Max will review shortly.</p>
            <Link to="/dashboard">
              <Button className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">Back to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6" data-testid="milestone-submit-page">
      <Card className="bg-white border-[#B8D4E8] max-w-lg w-full shadow-sm">
        <CardContent className="p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
              <HeaderIcon className="w-6 h-6 text-[#22438E]" />
            </div>
            <div>
              <h1 className="text-xl font-medium text-[#000]" data-testid="milestone-submit-title">{assignment.title}</h1>
              <p className="text-sm text-[#666]">
                Week {milestone.week_number}
                {milestone.title && !/^Week \d+$/.test(milestone.title) && (
                  <> · {milestone.title}</>
                )}
                {milestone.is_final_capstone && <Star className="inline w-3.5 h-3.5 ml-1 text-[#7C3AED]" />}
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {milestone.description && (
              <p className="text-sm text-[#333] whitespace-pre-wrap bg-[#F8FBFF] border border-[#E5E7EB] rounded-md p-3">
                {milestone.description}
              </p>
            )}

            {driveUrl && !isQuestionnaire && (
              <div className="rounded-lg border border-[#22438E] bg-[#E1F0FF] p-4">
                <p className="text-sm font-medium text-[#000]">Step 1 · Upload to Google Drive</p>
                <p className="text-xs text-[#333] mt-0.5">Save your work in the shared class Drive folder, then upload the same file here for AI review.</p>
                <a href={driveUrl} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 mt-2 text-xs font-medium text-white bg-[#22438E] hover:bg-[#1A3A7A] px-3 py-1.5 rounded-md"
                  data-testid="milestone-drive-link">
                  <FolderOpen className="w-3.5 h-3.5" /> Open Drive Folder
                </a>
              </div>
            )}

            {isQuestionnaire ? (
              <div className="space-y-3" data-testid="milestone-questionnaire-form">
                {fields.length === 0 && (
                  <p className="text-sm text-[#666] italic">This questionnaire has no questions yet.</p>
                )}
                {fields.map((f, idx) => (
                  <div key={f.id} data-testid={`milestone-questionnaire-field-${f.id}`}>
                    <Label className="text-sm font-medium text-[#000]">
                      {idx + 1}. {f.label}
                      {f.required && <span className="text-red-600 ml-1">*</span>}
                    </Label>
                    {f.type === 'longtext' ? (
                      <Textarea
                        value={answers[f.id] || ''}
                        onChange={(e) => setAnswers({ ...answers, [f.id]: e.target.value })}
                        rows={4}
                        className="mt-1"
                        maxLength={5000}
                        data-testid={`milestone-questionnaire-input-${f.id}`}
                      />
                    ) : (
                      <Input
                        value={answers[f.id] || ''}
                        onChange={(e) => setAnswers({ ...answers, [f.id]: e.target.value })}
                        className="mt-1"
                        maxLength={5000}
                        data-testid={`milestone-questionnaire-input-${f.id}`}
                      />
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div>
                <label htmlFor="milestone-file" className="flex flex-col items-center gap-2 p-6 border-2 border-dashed border-[#B8D4E8] rounded-lg cursor-pointer hover:border-[#22438E] hover:bg-[#E1F0FF] transition-colors">
                  <Upload className="w-8 h-8 text-[#666]" />
                  <span className="text-sm font-medium text-[#000]">
                    {file ? file.name : 'Click to select your file'}
                  </span>
                  <span className="text-xs text-[#666]">{extHint}</span>
                </label>
                <input id="milestone-file" type="file" accept={acceptAttr}
                  className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)}
                  data-testid="milestone-file-input" />
              </div>
            )}

            <Button
              onClick={handleSubmit}
              disabled={submitting || (isQuestionnaire ? (fields.length === 0 || missingRequired) : !file)}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A] w-full"
              data-testid="milestone-submit-btn"
            >
              {submitting ? 'Submitting...' : 'Submit'}
            </Button>
          </div>

          <div className="mt-6 pt-4 border-t border-[#B8D4E8] text-center">
            <p className="text-xs text-[#666]">Powered by <strong>The Boost Pad</strong> &middot; Coach Max AI Tutor</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


function _resolverView(error) {
  if (!error) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }
  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6">
      <Card className="bg-white border-[#B8D4E8] max-w-md w-full">
        <CardContent className="p-8 text-center" data-testid="stable-link-not-found">
          <FileText className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
          <h2 className="text-xl font-medium text-[#000] mb-2">Not published yet</h2>
          <p className="text-[#666] mb-4">{error}</p>
          <Link to="/dashboard">
            <Button variant="outline" className="border-[#22438E] text-[#22438E]">Back to Dashboard</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

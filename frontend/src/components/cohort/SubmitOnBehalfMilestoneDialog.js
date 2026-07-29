import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Upload, Sparkles } from 'lucide-react';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '../ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { getSubmissionTypeConfig } from '../../config/submissionTypes';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Dialog: instructor submits a file on behalf of a student for a specific assignment+milestone.
 * Auto-triggers AI review server-side.
 *
 * NOTE: business_questionnaire is intentionally NOT supported here per product decision —
 *       questionnaires must be filled by the student themselves.
 */
export function SubmitOnBehalfMilestoneDialog({
  open,
  onOpenChange,
  assignment,
  milestone,
  cohortId,
  students,
  onSubmitted,
}) {
  const [studentId, setStudentId] = useState('');
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setStudentId('');
      setFile(null);
      setSubmitting(false);
    }
  }, [open]);

  if (!assignment || !milestone) return null;

  const typeConfig = getSubmissionTypeConfig(assignment.submission_type);
  const isQuestionnaire = assignment.submission_type === 'business_questionnaire';
  // Per-assignment allowed_extensions override wins over the type default.
  const effectiveExtensions = (assignment.allowed_extensions && assignment.allowed_extensions.length > 0)
    ? assignment.allowed_extensions
    : (typeConfig?.extensions || ['pdf', 'docx']);
  const acceptAttr = effectiveExtensions.map((e) => `.${e}`).join(',');

  // Platform upload ceiling. Ingresses / CDNs (including Cloudflare Free)
  // typically reject request bodies > ~100 MB before they reach FastAPI, so
  // the backend never gets a chance to return a proper error. We surface a
  // clear client-side warning + block so instructors don't burn time on an
  // upload that can't succeed.
  const MAX_UPLOAD_MB = 100;
  const fileTooLarge = file && file.size > MAX_UPLOAD_MB * 1024 * 1024;

  const handleSubmit = async () => {
    if (!studentId) {
      toast.error('Please select a student');
      return;
    }
    if (!file) {
      toast.error('Please choose a file to submit');
      return;
    }
    if (fileTooLarge) {
      const mb = (file.size / 1024 / 1024).toFixed(0);
      toast.error(
        `File is ${mb} MB — our upload proxy caps at ${MAX_UPLOAD_MB} MB. `
        + `Please compress the video (e.g. QuickTime → Export → 480p) or trim it, then retry.`
      );
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('student_id', studentId);
      formData.append('assignment_id', assignment.assignment_id);
      formData.append('cohort_id', cohortId);
      const res = await axios.post(
        `${API_URL}/api/milestones/${milestone.milestone_id}/submit-on-behalf`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 },
      );
      toast.success(res.data?.message || 'Submitted. Coach Max is reviewing.');
      if (onSubmitted) onSubmitted(res.data);
      onOpenChange(false);
    } catch (err) {
      // Surface the real cause rather than a generic "Failed to submit".
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      let msg;
      if (detail) {
        msg = detail;
      } else if (status === 413) {
        msg = 'Upload rejected: file is too large for the proxy. Compress the video and retry.';
      } else if (err?.code === 'ECONNABORTED' || /timeout/i.test(err?.message || '')) {
        msg = 'Upload timed out. This usually means the file is too large for the network — compress it and retry.';
      } else if (!err?.response) {
        msg = `Upload failed (network / proxy). ${err?.message || ''} — likely the file exceeds the upload proxy limit.`;
      } else {
        msg = `Failed to submit on behalf${status ? ` (HTTP ${status})` : ''}`;
      }
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-white" data-testid="submit-on-behalf-milestone-dialog">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Submit on behalf of a student</DialogTitle>
          <DialogDescription>
            <strong>{assignment.title}</strong> · Week {milestone.week_number}: {milestone.title || `Week ${milestone.week_number}`}
          </DialogDescription>
        </DialogHeader>

        {isQuestionnaire ? (
          <div className="p-4 bg-[#FEF3C7] border border-[#F59E0B] rounded-lg text-sm text-[#78350F]">
            The Business Questionnaire must be filled in by the student themselves — instructors cannot submit questionnaires on behalf of students.
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor="sob-student">Student</Label>
              <Select value={studentId} onValueChange={setStudentId}>
                <SelectTrigger className="mt-1" data-testid="sob-student-select">
                  <SelectValue placeholder="Select a student..." />
                </SelectTrigger>
                <SelectContent>
                  {(students || []).length === 0 ? (
                    <SelectItem value="__none" disabled>No students in this cohort</SelectItem>
                  ) : (
                    (students || []).map((s) => (
                      <SelectItem key={s.user_id} value={s.user_id} data-testid={`sob-student-option-${s.user_id}`}>
                        {s.name || s.email} <span className="text-xs text-[#666]">· {s.email}</span>
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>File</Label>
              <div className="mt-1">
                <label
                  htmlFor="sob-file-upload"
                  className="flex items-center justify-center gap-2 p-4 border-2 border-dashed border-[#B8D4E8] rounded-lg cursor-pointer hover:border-[#22438E] transition-colors"
                >
                  <Upload className="w-5 h-5 text-[#666]" />
                  <span className="text-sm text-[#333]">
                    {file ? file.name : 'Click to select file'}
                  </span>
                </label>
                <input
                  id="sob-file-upload"
                  data-testid="sob-file-input"
                  type="file"
                  accept={acceptAttr}
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </div>
              <p className="text-xs text-[#666] mt-1">
                Allowed: {effectiveExtensions.map((e) => `.${e}`).join(', ')} · Max file size: {MAX_UPLOAD_MB} MB
              </p>
              {fileTooLarge && (
                <p
                  className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md p-2 mt-2"
                  data-testid="sob-file-too-large-warning"
                >
                  This file is {(file.size / 1024 / 1024).toFixed(0)} MB — over the {MAX_UPLOAD_MB} MB
                  upload cap. Compress the video (QuickTime → Export → 480p, or use HandBrake) and
                  reselect it before submitting.
                </p>
              )}
            </div>

            <div className="flex items-start gap-2 p-3 bg-[#E1F0FF] rounded-lg">
              <Sparkles className="w-4 h-4 text-[#22438E] flex-shrink-0 mt-0.5" />
              <p className="text-xs text-[#22438E]">
                Coach Max will run an AI review automatically after upload. You&apos;ll be able to review and edit
                the feedback before it&apos;s sent to the student.
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          {!isQuestionnaire && (
            <Button
              onClick={handleSubmit}
              disabled={submitting || !studentId || !file || fileTooLarge}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
              data-testid="sob-submit-btn"
            >
              {submitting ? 'Submitting...' : 'Submit & Auto-Review'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

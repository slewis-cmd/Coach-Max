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
import { MAX_UPLOAD_MB, isFileTooLarge, fileSizeMbLabel, humanUploadError, tooLargeMessage } from '../../lib/uploadLimits';

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
  // When no specific milestone is passed, let the instructor pick one from the
  // assignment's milestone list inside the dialog.
  const [pickedMilestoneId, setPickedMilestoneId] = useState('');

  useEffect(() => {
    if (!open) {
      setStudentId('');
      setFile(null);
      setSubmitting(false);
      setPickedMilestoneId('');
    } else if (!milestone) {
      // Auto-select first non-questionnaire milestone for convenience
      const first = (assignment?.milestones || []).find(m => m);
      setPickedMilestoneId(first?.milestone_id || '');
    }
  }, [open, milestone, assignment]);

  if (!assignment) return null;

  // Effective milestone = the one passed in OR the one picked inside the dialog.
  const effectiveMilestone =
    milestone
    || (assignment.milestones || []).find(m => m.milestone_id === pickedMilestoneId)
    || null;

  const typeConfig = getSubmissionTypeConfig(assignment.submission_type);
  const isQuestionnaire = assignment.submission_type === 'business_questionnaire';
  // Per-assignment allowed_extensions override wins over the type default.
  // For Generic Homework (empty submission_type), fall back to the broad
  // "any-file" set so the OS file picker doesn't gray out spreadsheets, etc.
  const GENERIC_HOMEWORK_EXTENSIONS = [
    'pdf', 'doc', 'docx', 'txt', 'md', 'rtf',
    'xlsx', 'xls', 'csv',
    'ppt', 'pptx',
    'mp4', 'mov', 'm4v', 'webm', 'mp3', 'm4a', 'wav',
  ];
  const effectiveExtensions = (assignment.allowed_extensions && assignment.allowed_extensions.length > 0)
    ? assignment.allowed_extensions
    : (typeConfig?.extensions || GENERIC_HOMEWORK_EXTENSIONS);
  const acceptAttr = effectiveExtensions.map((e) => `.${e}`).join(',');

  // Platform upload ceiling. Ingresses / CDNs (including Cloudflare Free)
  // typically reject request bodies > ~100 MB before they reach FastAPI, so
  // the backend never gets a chance to return a proper error. We surface a
  // clear client-side warning + block so instructors don't burn time on an
  // upload that can't succeed.
  const fileTooLarge = isFileTooLarge(file);

  const handleSubmit = async () => {
    if (!studentId) {
      toast.error('Please select a student');
      return;
    }
    if (!effectiveMilestone) {
      toast.error('Please pick which milestone to submit for');
      return;
    }
    if (!file) {
      toast.error('Please choose a file to submit');
      return;
    }
    if (fileTooLarge) {
      toast.error(tooLargeMessage(file));
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
        `${API_URL}/api/milestones/${effectiveMilestone.milestone_id}/submit-on-behalf`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 },
      );
      toast.success(res.data?.message || 'Submitted. Coach Max is reviewing.');
      if (onSubmitted) onSubmitted(res.data);
      onOpenChange(false);
    } catch (err) {
      toast.error(humanUploadError(err, 'Failed to submit on behalf'));
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
            <strong>{assignment.title}</strong>
            {milestone && (
              <> · Week {milestone.week_number}: {milestone.title || `Week ${milestone.week_number}`}</>
            )}
          </DialogDescription>
        </DialogHeader>

        {isQuestionnaire ? (
          <div className="p-4 bg-[#FEF3C7] border border-[#F59E0B] rounded-lg text-sm text-[#78350F]">
            The Business Questionnaire must be filled in by the student themselves — instructors cannot submit questionnaires on behalf of students.
          </div>
        ) : (
          <div className="space-y-4 py-2">
            {/* Milestone picker — shown only when the dialog was opened without a
                specific milestone (e.g. from the assignment-header quick action). */}
            {!milestone && (assignment.milestones || []).length > 0 && (
              <div>
                <Label htmlFor="sob-milestone">Milestone</Label>
                <Select value={pickedMilestoneId} onValueChange={setPickedMilestoneId}>
                  <SelectTrigger className="mt-1" data-testid="sob-milestone-select">
                    <SelectValue placeholder="Select a milestone..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(assignment.milestones || []).map(m => (
                      <SelectItem key={m.milestone_id} value={m.milestone_id}>
                        Week {m.week_number} — {m.title || `Week ${m.week_number}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
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
                  This file is {fileSizeMbLabel(file)} MB — over the {MAX_UPLOAD_MB} MB
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
              disabled={submitting || !studentId || !file || fileTooLarge || !effectiveMilestone}
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

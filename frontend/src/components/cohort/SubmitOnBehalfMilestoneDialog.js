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

  const handleSubmit = async () => {
    if (!studentId) {
      toast.error('Please select a student');
      return;
    }
    if (!file) {
      toast.error('Please choose a file to submit');
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
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      toast.success(res.data?.message || 'Submitted. Coach Max is reviewing.');
      if (onSubmitted) onSubmitted(res.data);
      onOpenChange(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to submit on behalf');
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
                  accept={typeConfig?.accept || '.pdf,.docx'}
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </div>
              {typeConfig && (
                <p className="text-xs text-[#666] mt-1">
                  Allowed: {typeConfig.extensions.map((e) => `.${e}`).join(', ')}
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
              disabled={submitting || !studentId || !file}
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

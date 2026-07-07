import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ChevronDown, ChevronRight, Copy, Trash2, Sparkles, FolderOpen, Star, Mic, Presentation, FileText, ListChecks, Plus
} from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from '../ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../ui/select';
import { SUBMISSION_TYPES, SUBMISSION_TYPE_BY_ID } from '../../config/submissionTypes';
import { FeedbackTemplateField } from '../rubric/FeedbackTemplateField';
import { SubmissionTypeFields } from '../material/SubmissionTypeFields';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const ICONS = { Mic, Presentation, FileText, ListChecks };

export function AssignmentsTab({ cohortId, cohort, isInstructor }) {
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [milestoneEditing, setMilestoneEditing] = useState(null); // {assignment, milestone}

  const fetchAssignments = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/cohorts/${cohortId}/assignments`);
      setAssignments(res.data || []);
    } catch (err) {
      toast.error('Failed to load assignments');
    } finally {
      setLoading(false);
    }
  }, [cohortId]);

  useEffect(() => {
    fetchAssignments();
  }, [fetchAssignments]);

  const toggleExpand = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  const copyStableLink = (asgn, milestone) => {
    const link = `${window.location.origin}/submit/a/${asgn.assignment_id}/w/${milestone.week_number}?cohort=${cohortId}`;
    navigator.clipboard.writeText(link)
      .then(() => toast.success('Thinkific-stable link copied!'))
      .catch(() => toast.error('Failed to copy link'));
  };

  const handleDeactivate = async (asgn) => {
    if (!window.confirm(`Deactivate "${asgn.title}"? Students will no longer see it. You can add a custom assignment later.`)) return;
    try {
      await axios.delete(`${API_URL}/api/assignments/${asgn.assignment_id}`);
      toast.success('Assignment deactivated');
      fetchAssignments();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to deactivate');
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const activeAssignments = assignments.filter((a) => a.is_active !== false);

  return (
    <div className="space-y-4" data-testid="assignments-tab">
      {isInstructor && (
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-lg font-medium text-[#000]">Student Assignments</h2>
            <p className="text-sm text-[#666]">The 4 named exercises + any custom ones. Each has weekly milestones.</p>
          </div>
          <Button
            onClick={() => setCreating(true)}
            className="bg-[#22438E] hover:bg-[#1A3A7A] rounded-full"
            data-testid="new-assignment-btn"
          >
            <Plus className="w-4 h-4 mr-1.5" /> New Assignment
          </Button>
        </div>
      )}

      {activeAssignments.length === 0 && (
        <Card className="bg-white border-[#B8D4E8] border-dashed">
          <CardContent className="p-12 text-center">
            <Star className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
            <p className="text-[#333] mb-4">No active assignments yet.</p>
            {isInstructor && (
              <Button onClick={() => setCreating(true)} className="bg-[#22438E] hover:bg-[#1A3A7A]">
                <Plus className="w-4 h-4 mr-1.5" /> Create an Assignment
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {activeAssignments.map((asgn) => {
        const config = SUBMISSION_TYPE_BY_ID[asgn.submission_type];
        const HeaderIcon = ICONS[config?.icon] || FileText;
        const isOpen = expanded[asgn.assignment_id];
        return (
          <Card key={asgn.assignment_id} className="bg-white border-[#B8D4E8]" data-testid={`assignment-card-${asgn.assignment_id}`}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-3">
                <button
                  className="flex items-start gap-3 flex-1 text-left"
                  onClick={() => toggleExpand(asgn.assignment_id)}
                  data-testid={`assignment-expand-${asgn.assignment_id}`}
                >
                  {isOpen ? <ChevronDown className="w-5 h-5 text-[#666] mt-0.5" /> : <ChevronRight className="w-5 h-5 text-[#666] mt-0.5" />}
                  <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center flex-shrink-0">
                    <HeaderIcon className="w-5 h-5 text-[#22438E]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-base font-medium">{asgn.title}</CardTitle>
                    <CardDescription className="text-xs text-[#666]">
                      {config?.label || asgn.submission_type} · {(asgn.milestones || []).length} milestones
                      {asgn.feedback_template ? ' · Custom rubric' : ''}
                    </CardDescription>
                  </div>
                </button>
                {isInstructor && (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <Button
                      variant="ghost" size="icon"
                      onClick={() => setEditing(asgn)}
                      title="Edit assignment"
                      data-testid={`edit-assignment-${asgn.assignment_id}`}
                    >
                      <Sparkles className="w-4 h-4 text-[#22438E]" />
                    </Button>
                    <Button
                      variant="ghost" size="icon"
                      onClick={() => handleDeactivate(asgn)}
                      title="Deactivate"
                      data-testid={`deactivate-assignment-${asgn.assignment_id}`}
                    >
                      <Trash2 className="w-4 h-4 text-red-600" />
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            {isOpen && (
              <CardContent className="pt-0">
                {asgn.description && (
                  <p className="text-sm text-[#333] mb-3 whitespace-pre-wrap">{asgn.description}</p>
                )}
                <div className="space-y-2">
                  {(asgn.milestones || []).map((ms) => (
                    <div
                      key={ms.milestone_id}
                      className="flex items-center gap-3 border border-[#E5E7EB] rounded-lg p-3 hover:bg-[#F8FBFF]"
                      data-testid={`milestone-row-${ms.milestone_id}`}
                    >
                      <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-medium ${
                        ms.is_final_capstone ? 'bg-[#7C3AED] text-white' : 'bg-[#E1F0FF] text-[#22438E]'
                      }`}>
                        {ms.is_final_capstone ? <Star className="w-4 h-4" /> : ms.week_number}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[#000] truncate">
                          {ms.title || `Week ${ms.week_number}`}
                        </p>
                        {ms.description && (
                          <p className="text-xs text-[#666] truncate">{ms.description}</p>
                        )}
                      </div>
                      {isInstructor && (
                        <>
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => copyStableLink(asgn, ms)}
                            className="text-[#7C3AED] hover:bg-[#F5EBFF] h-8 text-xs"
                            title="Copy Thinkific-stable link — always resolves to the current milestone"
                            data-testid={`copy-milestone-link-${ms.milestone_id}`}
                          >
                            <Copy className="w-3.5 h-3.5 mr-1" /> Link
                          </Button>
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => setMilestoneEditing({ assignment: asgn, milestone: ms })}
                            className="text-[#22438E] hover:bg-[#E1F0FF] h-8 text-xs"
                            data-testid={`edit-milestone-${ms.milestone_id}`}
                          >
                            <Sparkles className="w-3.5 h-3.5 mr-1" /> Edit
                          </Button>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            )}
          </Card>
        );
      })}

      <AssignmentFormDialog
        open={creating || !!editing}
        editing={editing}
        onOpenChange={(open) => { if (!open) { setEditing(null); setCreating(false); } }}
        onSaved={() => { setEditing(null); setCreating(false); fetchAssignments(); }}
        cohortId={cohortId}
      />
      <MilestoneEditDialog
        open={!!milestoneEditing}
        milestoneEditing={milestoneEditing}
        onOpenChange={(open) => { if (!open) setMilestoneEditing(null); }}
        onSaved={() => { setMilestoneEditing(null); fetchAssignments(); }}
      />
    </div>
  );
}

function AssignmentFormDialog({ open, editing, onOpenChange, onSaved, cohortId }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [submissionType, setSubmissionType] = useState('60_second_pitch');
  const [feedbackTemplate, setFeedbackTemplate] = useState('');
  const [driveFolderUrl, setDriveFolderUrl] = useState('');
  const [questionnaireFields, setQuestionnaireFields] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setTitle(editing?.title || '');
      setDescription(editing?.description || '');
      setSubmissionType(editing?.submission_type || '60_second_pitch');
      setFeedbackTemplate(editing?.feedback_template || '');
      setDriveFolderUrl(editing?.drive_folder_url || '');
      setQuestionnaireFields(editing?.questionnaire_fields || []);
    }
  }, [open, editing]);

  const handleSave = async () => {
    if (!title.trim()) return toast.error('Title is required');
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`${API_URL}/api/assignments/${editing.assignment_id}`, {
          title: title.trim(),
          description: description.trim(),
          feedback_template: feedbackTemplate,
          drive_folder_url: driveFolderUrl,
          questionnaire_fields: submissionType === 'business_questionnaire' ? questionnaireFields : null,
        });
        toast.success('Assignment updated');
      } else {
        await axios.post(`${API_URL}/api/cohorts/${cohortId}/assignments`, {
          title: title.trim(),
          description: description.trim(),
          submission_type: submissionType,
          feedback_template: feedbackTemplate,
          drive_folder_url: driveFolderUrl,
          questionnaire_fields: submissionType === 'business_questionnaire' ? questionnaireFields : null,
        });
        toast.success('Assignment created');
      }
      onSaved();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="assignment-form-dialog">
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit Assignment' : 'New Assignment'}</DialogTitle>
          <DialogDescription>
            {editing
              ? "You can rename the assignment, change its description, and set an AI feedback rubric that applies to all milestones."
              : "Pick a file format and give your assignment a name. Weekly milestones will be created automatically — you can edit each one separately."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label htmlFor="asgn-title">Title</Label>
            <Input
              id="asgn-title"
              data-testid="assignment-title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1"
              placeholder="e.g., Weekly Product Demo Video"
              autoFocus
            />
          </div>
          <div>
            <Label htmlFor="asgn-desc">Description (optional)</Label>
            <Textarea
              id="asgn-desc"
              data-testid="assignment-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1"
              placeholder="What is this assignment about?"
            />
          </div>
          {!editing && (
            <SubmissionTypeFields
              submissionType={submissionType}
              onSubmissionTypeChange={(v) => setSubmissionType(v || '60_second_pitch')}
              questionnaireFields={questionnaireFields}
              onQuestionnaireFieldsChange={setQuestionnaireFields}
              idPrefix="asgn-submission-type"
            />
          )}
          {editing && submissionType === 'business_questionnaire' && (
            <SubmissionTypeFields
              submissionType={submissionType}
              onSubmissionTypeChange={() => {}}
              questionnaireFields={questionnaireFields}
              onQuestionnaireFieldsChange={setQuestionnaireFields}
              idPrefix="asgn-submission-type-edit"
            />
          )}
          <div>
            <Label htmlFor="asgn-drive">Google Drive Folder URL (optional)</Label>
            <Input
              id="asgn-drive"
              data-testid="assignment-drive-input"
              value={driveFolderUrl}
              onChange={(e) => setDriveFolderUrl(e.target.value)}
              className="mt-1"
              placeholder="https://drive.google.com/..."
            />
          </div>
          <FeedbackTemplateField
            value={feedbackTemplate}
            onChange={setFeedbackTemplate}
            idPrefix="asgn-feedback-template"
            label="Default AI Feedback Rubric"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="assignment-form-cancel-btn">Cancel</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="assignment-form-save-btn">
            {saving ? 'Saving…' : editing ? 'Save Changes' : 'Create Assignment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MilestoneEditDialog({ open, milestoneEditing, onOpenChange, onSaved }) {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && milestoneEditing?.milestone) {
      setForm({ ...milestoneEditing.milestone });
    }
  }, [open, milestoneEditing]);

  if (!milestoneEditing || !form) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(
        `${API_URL}/api/assignments/${milestoneEditing.assignment.assignment_id}/milestones/${milestoneEditing.milestone.milestone_id}`,
        {
          week_number: form.week_number,
          title: form.title || '',
          description: form.description || '',
          feedback_template_override: form.feedback_template_override || '',
          drive_folder_url_override: form.drive_folder_url_override || '',
          is_final_capstone: !!form.is_final_capstone,
          due_date: form.due_date || null,
        }
      );
      toast.success('Milestone updated');
      onSaved();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save milestone');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="milestone-edit-dialog">
        <DialogHeader>
          <DialogTitle>Edit Milestone — Week {form.week_number}</DialogTitle>
          <DialogDescription>
            Milestone-specific overrides. Leave blank to inherit from the assignment.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <Label>Title</Label>
            <Input
              value={form.title || ''}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              data-testid="milestone-title-input"
              className="mt-1"
            />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              value={form.description || ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={2}
              className="mt-1"
              data-testid="milestone-description-input"
            />
          </div>
          <div>
            <Label>Drive Folder URL Override (optional)</Label>
            <Input
              value={form.drive_folder_url_override || ''}
              onChange={(e) => setForm({ ...form, drive_folder_url_override: e.target.value })}
              className="mt-1"
              placeholder="Leave blank to inherit from the assignment"
              data-testid="milestone-drive-input"
            />
          </div>
          <div>
            <Label>Feedback Template Override (optional)</Label>
            <Textarea
              value={form.feedback_template_override || ''}
              onChange={(e) => setForm({ ...form, feedback_template_override: e.target.value })}
              rows={3}
              className="mt-1"
              placeholder="Leave blank to inherit the assignment-level rubric"
              data-testid="milestone-feedback-template-input"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.is_final_capstone}
              onChange={(e) => setForm({ ...form, is_final_capstone: e.target.checked })}
              data-testid="milestone-capstone-checkbox"
            />
            Final capstone (the combined whole-deck / final submission)
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="milestone-cancel-btn">Cancel</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="milestone-save-btn">
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


/** Cohort settings dialog — auto_send_feedback toggle + total_weeks */
export function CohortSettingsDialog({ open, onOpenChange, cohort, onSaved, isSuperAdmin = false }) {
  const [autoSend, setAutoSend] = useState(false);
  const [totalWeeks, setTotalWeeks] = useState(14);
  const [saving, setSaving] = useState(false);
  const [migrating, setMigrating] = useState(false);

  useEffect(() => {
    if (open && cohort) {
      setAutoSend(!!cohort.auto_send_feedback);
      setTotalWeeks(cohort.total_weeks || 14);
    }
  }, [open, cohort]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API_URL}/api/cohorts/${cohort.cohort_id}`, {
        auto_send_feedback: autoSend,
        total_weeks: parseInt(totalWeeks, 10) || 14,
      });
      toast.success('Cohort settings saved');
      onSaved();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="cohort-settings-dialog">
        <DialogHeader>
          <DialogTitle>Cohort Settings</DialogTitle>
          <DialogDescription>
            Configure how feedback is delivered and how many weeks this cohort runs for.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label htmlFor="total-weeks">Total Weeks</Label>
            <Input
              id="total-weeks"
              type="number"
              min="1"
              max="52"
              value={totalWeeks}
              onChange={(e) => setTotalWeeks(e.target.value)}
              className="mt-1 w-32"
              data-testid="total-weeks-input"
            />
          </div>
          <div className="border-t border-[#E5E7EB] pt-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={autoSend}
                onChange={(e) => setAutoSend(e.target.checked)}
                className="mt-1"
                data-testid="auto-send-feedback-toggle"
              />
              <div>
                <div className="text-sm font-medium text-[#000]">Auto-send AI feedback to students (self-paced mode)</div>
                <p className="text-xs text-[#666] mt-1">
                  When enabled, AI-generated feedback is sent directly to the student&apos;s inbox as soon as the review runs — no instructor review step. Use this for self-paced cohorts.
                </p>
                <p className="text-xs text-[#7C3AED] mt-1 italic">
                  When disabled (default), AI feedback is saved as a <strong>draft</strong> for the instructor to review and edit before sending.
                </p>
              </div>
            </label>
          </div>
          {isSuperAdmin && (
            <div className="border-t border-[#E5E7EB] pt-4">
              <div className="text-sm font-medium text-[#000] mb-1">Migrate Existing Homework to Assignments</div>
              <p className="text-xs text-[#666] mb-2">
                One-time: seed the 4 default assignments in every cohort and move existing homework materials + submissions into &ldquo;Your Business Questionnaire&rdquo;. Idempotent — safe to run again.
              </p>
              <Button
                variant="outline"
                onClick={async () => {
                  if (!window.confirm('Run migration across ALL cohorts? This is idempotent (safe to re-run).')) return;
                  setMigrating(true);
                  try {
                    const res = await axios.post(`${API_URL}/api/admin/migrate-to-assignments`);
                    const s = res.data;
                    toast.success(`Migration complete — ${s.cohorts_seeded} cohorts seeded, ${s.submissions_linked} submissions linked`);
                  } catch (err) {
                    toast.error(err?.response?.data?.detail || 'Migration failed');
                  } finally {
                    setMigrating(false);
                  }
                }}
                disabled={migrating}
                className="border-[#7C3AED] text-[#7C3AED] hover:bg-[#F5EBFF]"
                data-testid="run-migration-btn"
              >
                {migrating ? 'Migrating…' : 'Run Migration'}
              </Button>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cohort-settings-cancel-btn">Cancel</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="cohort-settings-save-btn">
            {saving ? 'Saving…' : 'Save Settings'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

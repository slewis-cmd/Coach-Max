import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ArrowLeft, Plus, Trash2, Pencil, Star, User, Layers, ChevronDown, ChevronRight
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from '../components/ui/dialog';
import { SUBMISSION_TYPES, SUBMISSION_TYPE_BY_ID } from '../config/submissionTypes';
import { SubmissionTypeFields } from '../components/material/SubmissionTypeFields';
import { FeedbackTemplateField } from '../components/rubric/FeedbackTemplateField';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const emptyMilestone = (wk) => ({
  milestone_id: `ms_new_${Math.random().toString(36).slice(2, 10)}`,
  week_number: wk,
  title: `Week ${wk}`,
  description: '',
  feedback_template_override: '',
  drive_folder_url_override: '',
  is_final_capstone: false,
  due_date: null,
});

export default function AssignmentTemplatesPage() {
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!authLoading && !isInstructor) navigate('/dashboard');
  }, [authLoading, isInstructor, navigate]);

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/assignment-templates`);
      setTemplates(res.data || []);
    } catch (err) {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isInstructor) fetchTemplates();
  }, [authLoading, isInstructor, fetchTemplates]);

  const handleDelete = async (t) => {
    if (!window.confirm(`Delete template "${t.name}"? Existing assignments already applied from this template are unaffected.`)) return;
    try {
      await axios.delete(`${API_URL}/api/assignment-templates/${t.template_id}`);
      setTemplates((prev) => prev.filter((x) => x.template_id !== t.template_id));
      toast.success('Template deleted');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to delete');
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="assignment-templates-page">
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/dashboard" className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors" data-testid="back-to-dashboard-btn">
              <ArrowLeft className="w-5 h-5 text-[#333333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000] flex items-center gap-2">
                <Layers className="w-5 h-5 text-[#7C3AED]" />
                Assignment Templates
              </h1>
              <p className="text-sm text-[#666]">Reusable assignments — apply to any cohort with per-week milestone remapping</p>
            </div>
          </div>
          <Button onClick={() => setCreating(true)} className="bg-[#22438E] hover:bg-[#1A3A7A] rounded-full" data-testid="new-template-btn">
            <Plus className="w-4 h-4 mr-1.5" /> New Template
          </Button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {templates.length === 0 ? (
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <Layers className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#000] mb-2">No templates yet</h3>
              <p className="text-[#333] mb-6 max-w-md mx-auto">
                Save any existing assignment as a template — or create one from scratch — and reuse it (with editable week assignments) across new cohorts.
              </p>
              <Button onClick={() => setCreating(true)} className="bg-[#22438E] hover:bg-[#1A3A7A]" data-testid="empty-new-template-btn">
                <Plus className="w-4 h-4 mr-1.5" /> Create your first template
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {templates.map((t) => {
              const config = SUBMISSION_TYPE_BY_ID[t.submission_type];
              return (
                <Card key={t.template_id} className="bg-white border-[#B8D4E8]" data-testid={`template-card-${t.template_id}`}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <CardTitle className="text-base font-medium truncate">{t.name}</CardTitle>
                        <CardDescription className="text-xs mt-1 flex items-center gap-2">
                          <span className="uppercase tracking-wide text-[#7C3AED]">{config?.label || t.submission_type}</span>
                          <span>·</span>
                          <span>{(t.milestones || []).length} milestones</span>
                        </CardDescription>
                      </div>
                      {t.can_edit && (
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <Button variant="ghost" size="icon" onClick={() => setEditing(t)} title="Edit template" data-testid={`edit-template-${t.template_id}`}>
                            <Pencil className="w-4 h-4 text-[#22438E]" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handleDelete(t)} title="Delete template" data-testid={`delete-template-${t.template_id}`}>
                            <Trash2 className="w-4 h-4 text-red-600" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0">
                    {t.description && (
                      <p className="text-sm text-[#333] mb-2 line-clamp-2">{t.description}</p>
                    )}
                    <div className="flex flex-wrap gap-1 mb-3">
                      {(t.milestones || []).slice(0, 8).map((m) => (
                        <span key={m.milestone_id} className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full ${m.is_final_capstone ? 'bg-[#7C3AED] text-white' : 'bg-[#E1F0FF] text-[#22438E]'}`}>
                          {m.is_final_capstone && <Star className="w-2.5 h-2.5" />}W{m.week_number}
                        </span>
                      ))}
                      {(t.milestones || []).length > 8 && (
                        <span className="text-[10px] text-[#666] px-2">+{t.milestones.length - 8} more</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[#666]">
                      <User className="w-3 h-3" />
                      <span>{t.created_by_name || 'Unknown'}</span>
                      {t.created_by === user?.user_id && (
                        <span className="ml-1 px-1.5 py-0.5 bg-[#E1F0FF] text-[#22438E] rounded text-[10px] uppercase tracking-wide">You</span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </main>

      <TemplateFormDialog
        open={creating || !!editing}
        editing={editing}
        onOpenChange={(open) => { if (!open) { setCreating(false); setEditing(null); } }}
        onSaved={() => { setCreating(false); setEditing(null); fetchTemplates(); }}
      />
    </div>
  );
}


function TemplateFormDialog({ open, editing, onOpenChange, onSaved }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submissionType, setSubmissionType] = useState('60_second_pitch');
  const [feedbackTemplate, setFeedbackTemplate] = useState('');
  const [driveFolderUrl, setDriveFolderUrl] = useState('');
  const [questionnaireFields, setQuestionnaireFields] = useState([]);
  const [milestones, setMilestones] = useState([emptyMilestone(1)]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setName(editing?.name || '');
      setDescription(editing?.description || '');
      setSubmissionType(editing?.submission_type || '60_second_pitch');
      setFeedbackTemplate(editing?.feedback_template || '');
      setDriveFolderUrl(editing?.drive_folder_url || '');
      setQuestionnaireFields(editing?.questionnaire_fields || []);
      setMilestones(editing?.milestones?.length ? editing.milestones : [emptyMilestone(1)]);
    }
  }, [open, editing]);

  const addWeeklyGrid = (weeks, kawasakiCapstone = false) => {
    const grid = Array.from({ length: weeks }, (_, i) => emptyMilestone(i + 1));
    if (kawasakiCapstone && grid.length > 0) grid[grid.length - 1].is_final_capstone = true;
    setMilestones(grid);
  };

  const updateMilestone = (idx, patch) => {
    const next = [...milestones];
    next[idx] = { ...next[idx], ...patch };
    setMilestones(next);
  };

  const addMilestone = () => {
    const nextWeek = (milestones[milestones.length - 1]?.week_number || 0) + 1;
    setMilestones([...milestones, emptyMilestone(nextWeek)]);
  };

  const removeMilestone = (idx) => {
    setMilestones(milestones.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    if (!name.trim()) return toast.error('Name is required');
    if (milestones.length === 0) return toast.error('Add at least one milestone');
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        submission_type: submissionType,
        feedback_template: feedbackTemplate,
        drive_folder_url: driveFolderUrl,
        questionnaire_fields: submissionType === 'business_questionnaire' ? questionnaireFields : null,
        milestones,
      };
      if (editing) {
        await axios.put(`${API_URL}/api/assignment-templates/${editing.template_id}`, payload);
        toast.success('Template updated');
      } else {
        await axios.post(`${API_URL}/api/assignment-templates`, payload);
        toast.success('Template created');
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
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="template-form-dialog">
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit Template' : 'New Template'}</DialogTitle>
          <DialogDescription>
            Templates are shared across all instructors. Only you or a super admin can edit or delete your own templates.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label htmlFor="tpl-name">Name</Label>
            <Input id="tpl-name" data-testid="template-name-input" value={name} onChange={(e) => setName(e.target.value)} className="mt-1" autoFocus />
          </div>
          <div>
            <Label htmlFor="tpl-desc">Description (optional)</Label>
            <Textarea id="tpl-desc" data-testid="template-description-input" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="mt-1" />
          </div>
          {!editing && (
            <SubmissionTypeFields
              submissionType={submissionType}
              onSubmissionTypeChange={(v) => setSubmissionType(v || '60_second_pitch')}
              questionnaireFields={questionnaireFields}
              onQuestionnaireFieldsChange={setQuestionnaireFields}
              idPrefix="tpl-submission-type"
            />
          )}
          {editing && submissionType === 'business_questionnaire' && (
            <SubmissionTypeFields
              submissionType={submissionType}
              onSubmissionTypeChange={() => {}}
              questionnaireFields={questionnaireFields}
              onQuestionnaireFieldsChange={setQuestionnaireFields}
              idPrefix="tpl-submission-type-edit"
            />
          )}
          <div>
            <Label htmlFor="tpl-drive">Default Drive Folder URL (optional)</Label>
            <Input id="tpl-drive" data-testid="template-drive-input" value={driveFolderUrl} onChange={(e) => setDriveFolderUrl(e.target.value)} className="mt-1" placeholder="https://drive.google.com/..." />
          </div>
          <FeedbackTemplateField
            value={feedbackTemplate}
            onChange={setFeedbackTemplate}
            idPrefix="tpl-feedback-template"
            label="Default AI Feedback Rubric"
          />

          <div className="border-t border-[#E5E7EB] pt-3">
            <div className="flex items-center justify-between mb-2">
              <div>
                <Label>Milestones</Label>
                <p className="text-xs text-[#666]">Each milestone becomes one submission slot when applied. Weeks can be remapped at apply time.</p>
              </div>
              <div className="flex gap-1">
                <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => addWeeklyGrid(14)} data-testid="template-preset-14">14 wk</Button>
                <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => addWeeklyGrid(10)} data-testid="template-preset-10">10 wk</Button>
                <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => addWeeklyGrid(14, true)} data-testid="template-preset-kawasaki">Kawasaki 14+capstone</Button>
              </div>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {milestones.map((m, idx) => (
                <div key={m.milestone_id} className="flex items-start gap-2 bg-[#F8FBFF] border border-[#E5E7EB] rounded-md p-2" data-testid={`template-milestone-${idx}`}>
                  <div className="flex flex-col items-center gap-1 pt-1">
                    <Input type="number" min="1" max="52" value={m.week_number} onChange={(e) => updateMilestone(idx, { week_number: parseInt(e.target.value, 10) || 1 })} className="h-8 w-14 text-center text-sm" data-testid={`template-milestone-${idx}-week`} />
                    <label className="text-[10px] text-[#666] flex items-center gap-1">
                      <input type="checkbox" checked={!!m.is_final_capstone} onChange={(e) => updateMilestone(idx, { is_final_capstone: e.target.checked })} data-testid={`template-milestone-${idx}-capstone`} />
                      Capstone
                    </label>
                  </div>
                  <div className="flex-1 space-y-1">
                    <Input placeholder="Milestone title" value={m.title} onChange={(e) => updateMilestone(idx, { title: e.target.value })} className="h-8 text-sm" data-testid={`template-milestone-${idx}-title`} />
                    <Input placeholder="Short description (optional)" value={m.description || ''} onChange={(e) => updateMilestone(idx, { description: e.target.value })} className="h-8 text-sm" data-testid={`template-milestone-${idx}-description`} />
                  </div>
                  <Button type="button" variant="ghost" size="icon" onClick={() => removeMilestone(idx)} className="text-red-600 hover:bg-red-50 h-7 w-7" data-testid={`template-milestone-${idx}-remove`}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              ))}
            </div>
            <Button type="button" variant="outline" size="sm" onClick={addMilestone} className="mt-2 h-7 text-xs" data-testid="template-add-milestone-btn">
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Milestone
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="template-form-cancel-btn">Cancel</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="template-form-save-btn">
            {saving ? 'Saving…' : editing ? 'Save Changes' : 'Create Template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

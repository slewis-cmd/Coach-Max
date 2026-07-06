import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { BookmarkPlus, Sparkles, ChevronDown } from 'lucide-react';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from '../ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../ui/select';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const NONE = '__none__';

/**
 * Reusable field that lets an instructor:
 *  - Pick a saved rubric from the Rubric Library to prefill AI feedback instructions
 *  - Write / edit the instructions in a textarea
 *  - Save the current text as a new named rubric (Save as… button)
 *
 * Controlled input — `value` is the current feedback_template string.
 */
export function FeedbackTemplateField({ value, onChange, idPrefix = 'feedback-template', label = 'AI Feedback Instructions (optional)' }) {
  const [rubrics, setRubrics] = useState([]);
  const [selectedId, setSelectedId] = useState(NONE);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchRubrics = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/rubrics`);
      setRubrics(res.data || []);
    } catch (err) {
      console.warn('Failed to load rubric library:', err?.message || err);
    }
  }, []);

  useEffect(() => {
    fetchRubrics();
  }, [fetchRubrics]);

  const handlePick = (rubricId) => {
    setSelectedId(rubricId);
    if (rubricId === NONE) return;
    const r = rubrics.find((x) => x.rubric_id === rubricId);
    if (r) {
      onChange(r.content);
      toast.success(`Loaded rubric: ${r.name}`);
    }
  };

  const handleSaveAs = async () => {
    const name = saveName.trim();
    const content = (value || '').trim();
    if (!name) return toast.error('Rubric name is required');
    if (!content) return toast.error('Add some instructions to the textarea first');
    setSaving(true);
    try {
      const res = await axios.post(`${API_URL}/api/rubrics`, {
        name,
        content,
        description: saveDesc.trim(),
      });
      setRubrics((prev) => [res.data, ...prev]);
      setSelectedId(res.data.rubric_id);
      setSaveOpen(false);
      setSaveName('');
      setSaveDesc('');
      toast.success('Rubric saved to library');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save rubric');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid={`${idPrefix}-wrapper`}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <Label htmlFor={idPrefix}>{label}</Label>
        <div className="flex items-center gap-2">
          <Select value={selectedId} onValueChange={handlePick} data-testid={`${idPrefix}-picker`}>
            <SelectTrigger className="h-8 text-xs w-[220px]" data-testid={`${idPrefix}-picker-trigger`}>
              <div className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[#7C3AED]" />
                <SelectValue placeholder="Load from Rubric Library" />
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE} data-testid={`${idPrefix}-picker-none`}>— None (custom) —</SelectItem>
              {rubrics.length === 0 && (
                <SelectItem value="__empty__" disabled>Rubric Library is empty</SelectItem>
              )}
              {rubrics.map((r) => (
                <SelectItem key={r.rubric_id} value={r.rubric_id} data-testid={`${idPrefix}-picker-option-${r.rubric_id}`}>
                  {r.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs border-[#B8D4E8] text-[#22438E] hover:bg-[#E1F0FF]"
            onClick={() => setSaveOpen(true)}
            data-testid={`${idPrefix}-save-as-btn`}
          >
            <BookmarkPlus className="w-3.5 h-3.5 mr-1" />
            Save as…
          </Button>
        </div>
      </div>
      <Textarea
        id={idPrefix}
        data-testid={`${idPrefix}-input`}
        placeholder="Override the default rubric. e.g., 'Grade specifically on how the submission compares to the Kawasaki Model on slide 4.'"
        value={value || ''}
        onChange={(e) => {
          onChange(e.target.value);
          if (selectedId !== NONE) setSelectedId(NONE); // user diverged from picked rubric
        }}
        rows={3}
      />
      <p className="text-xs text-[#666666] mt-1">
        Leave blank for the default (3 things done well / 3 areas to improve). Custom instructions replace the default rubric for this assignment only.
      </p>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent data-testid={`${idPrefix}-save-dialog`}>
          <DialogHeader>
            <DialogTitle>Save as Rubric</DialogTitle>
            <DialogDescription>
              Save the current AI feedback instructions to your Rubric Library so any instructor can reuse them on future homework.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor={`${idPrefix}-save-name`}>Name</Label>
              <Input
                id={`${idPrefix}-save-name`}
                data-testid={`${idPrefix}-save-name-input`}
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder="e.g., Kawasaki Model Comparison"
                className="mt-1"
                autoFocus
              />
            </div>
            <div>
              <Label htmlFor={`${idPrefix}-save-desc`}>Description (optional)</Label>
              <Input
                id={`${idPrefix}-save-desc`}
                data-testid={`${idPrefix}-save-desc-input`}
                value={saveDesc}
                onChange={(e) => setSaveDesc(e.target.value)}
                placeholder="When would you use this rubric?"
                className="mt-1"
              />
            </div>
            <div className="text-xs text-[#666666] p-3 bg-[#E1F0FF] rounded-lg border border-[#B8D4E8]">
              <p className="font-medium text-[#22438E] mb-1">Preview</p>
              <p className="line-clamp-4 whitespace-pre-wrap">{value || '(empty)'}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveOpen(false)} data-testid={`${idPrefix}-save-cancel-btn`}>Cancel</Button>
            <Button onClick={handleSaveAs} disabled={saving} data-testid={`${idPrefix}-save-confirm-btn`}>
              {saving ? 'Saving…' : 'Save Rubric'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Standalone dialog used to EDIT the feedback_template on an existing homework material
 * (replaces the old window.prompt UX in MaterialsTab and MaterialLibrary).
 *
 * Props:
 *  open, onOpenChange, material {material_id, title, feedback_template}, onSaved(newTemplate)
 */
export function EditFeedbackTemplateDialog({ open, onOpenChange, material, onSaved }) {
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && material) setValue(material.feedback_template || '');
  }, [open, material]);

  const handleSave = async () => {
    if (!material) return;
    setSaving(true);
    try {
      await axios.put(`${API_URL}/api/materials/${material.material_id}/feedback-template`, {
        feedback_template: value,
      });
      toast.success(value.trim() ? 'AI instructions saved' : 'Restored default rubric');
      onOpenChange(false);
      if (onSaved) onSaved(value);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to update AI instructions');
    } finally {
      setSaving(false);
    }
  };

  const handleClear = () => setValue('');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="edit-feedback-template-dialog">
        <DialogHeader>
          <DialogTitle>Custom AI Feedback Instructions</DialogTitle>
          <DialogDescription>
            {material?.title ? `Assignment: ${material.title}` : 'Override the default 3-well / 3-improve rubric for this assignment.'}
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <FeedbackTemplateField
            value={value}
            onChange={setValue}
            idPrefix="edit-feedback-template"
            label="AI Feedback Instructions"
          />
        </div>
        <DialogFooter className="justify-between sm:justify-between">
          <Button
            variant="ghost"
            onClick={handleClear}
            className="text-[#666666] hover:text-red-600"
            data-testid="edit-feedback-template-clear-btn"
          >
            Restore default rubric
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="edit-feedback-template-cancel-btn">
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving} data-testid="edit-feedback-template-save-btn">
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

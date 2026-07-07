import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Star, Layers } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from '../ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../ui/select';
import { SUBMISSION_TYPE_BY_ID } from '../../config/submissionTypes';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Dialog to apply a template to the current cohort with per-milestone week remapping.
 * Props: open, onOpenChange, cohortId, cohort, onApplied()
 */
export function ApplyTemplateDialog({ open, onOpenChange, cohortId, cohort, onApplied }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [weekMap, setWeekMap] = useState({}); // {template_milestone_id: number|null}
  const [titleOverride, setTitleOverride] = useState('');
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [applying, setApplying] = useState(false);

  const selectedTemplate = templates.find((t) => t.template_id === selectedId);

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
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
    if (open) {
      fetchTemplates();
      setSelectedId('');
      setWeekMap({});
      setTitleOverride('');
      setReplaceExisting(true);
    }
  }, [open, fetchTemplates]);

  useEffect(() => {
    if (selectedTemplate) {
      const initial = {};
      (selectedTemplate.milestones || []).forEach((m) => {
        initial[m.milestone_id] = m.week_number;
      });
      setWeekMap(initial);
      setTitleOverride('');
    }
  }, [selectedTemplate]);

  const totalWeeks = cohort?.total_weeks || 14;
  const activeCount = Object.values(weekMap).filter((v) => v != null).length;

  const handleWeekChange = (msId, val) => {
    const parsed = val === '' ? null : parseInt(val, 10);
    setWeekMap({ ...weekMap, [msId]: Number.isFinite(parsed) ? parsed : null });
  };

  const toggleSkip = (msId, checked) => {
    setWeekMap({ ...weekMap, [msId]: checked ? null : (selectedTemplate.milestones.find((m) => m.milestone_id === msId)?.week_number || 1) });
  };

  const rescaleTo = (targetWeeks) => {
    if (!selectedTemplate) return;
    const originals = selectedTemplate.milestones || [];
    if (originals.length === 0) return;
    const originalMax = Math.max(...originals.map((m) => m.week_number || 1));
    const next = {};
    originals.forEach((m, i) => {
      // Proportional map: original week 1..originalMax → 1..targetWeeks
      const proportional = Math.round(((m.week_number || 1) / originalMax) * targetWeeks);
      next[m.milestone_id] = Math.max(1, Math.min(targetWeeks, proportional || (i + 1)));
    });
    setWeekMap(next);
    toast.success(`Milestones rescaled to ${targetWeeks} weeks`);
  };

  const handleApply = async () => {
    if (!selectedTemplate) return toast.error('Select a template first');
    setApplying(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/assignments/from-template/${selectedTemplate.template_id}`,
        {
          week_map: weekMap,
          replace_existing_by_type: replaceExisting,
          title_override: titleOverride || null,
        }
      );
      toast.success(res.data?.message || 'Template applied');
      onApplied();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to apply template');
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="apply-template-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-[#7C3AED]" /> Apply Assignment Template
          </DialogTitle>
          <DialogDescription>
            Pick a template. You can remap which week each milestone lands on before applying — perfect for reusing a 14-week template in a shorter cohort, or shifting content to align with your schedule.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div>
            <Label>Template</Label>
            <Select value={selectedId} onValueChange={setSelectedId}>
              <SelectTrigger className="mt-1" data-testid="apply-template-select">
                <SelectValue placeholder={loading ? 'Loading…' : (templates.length === 0 ? 'No templates saved yet' : 'Pick a template')} />
              </SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t.template_id} value={t.template_id} data-testid={`apply-template-option-${t.template_id}`}>
                    {t.name} · {SUBMISSION_TYPE_BY_ID[t.submission_type]?.shortLabel || t.submission_type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedTemplate && (
            <>
              <div>
                <Label htmlFor="tpl-title-override">Assignment title in this cohort (optional)</Label>
                <Input
                  id="tpl-title-override"
                  data-testid="apply-template-title-override"
                  value={titleOverride}
                  onChange={(e) => setTitleOverride(e.target.value)}
                  placeholder={selectedTemplate.name}
                  className="mt-1"
                />
              </div>

              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={replaceExisting}
                  onChange={(e) => setReplaceExisting(e.target.checked)}
                  className="mt-1"
                  data-testid="apply-template-replace-existing"
                />
                <span className="text-[#333]">
                  Replace the existing <span className="font-medium">{SUBMISSION_TYPE_BY_ID[selectedTemplate.submission_type]?.label}</span> assignment in this cohort (preserves student submissions). Uncheck to create a NEW assignment alongside the existing one.
                </span>
              </label>

              <div className="border-t border-[#E5E7EB] pt-3">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <Label>Milestone Week Mapping</Label>
                    <p className="text-xs text-[#666]">
                      {activeCount} of {selectedTemplate.milestones.length} milestones enabled · cohort has {totalWeeks} weeks
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => rescaleTo(totalWeeks)} data-testid="apply-template-rescale-btn">
                      Rescale to {totalWeeks} weeks
                    </Button>
                    <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => {
                      const orig = {};
                      selectedTemplate.milestones.forEach((m) => { orig[m.milestone_id] = m.week_number; });
                      setWeekMap(orig);
                    }} data-testid="apply-template-reset-btn">
                      Reset to Original
                    </Button>
                  </div>
                </div>
                <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
                  {(selectedTemplate.milestones || []).map((m, idx) => {
                    const currentWeek = weekMap[m.milestone_id];
                    const skipped = currentWeek === null || currentWeek === undefined;
                    return (
                      <div key={m.milestone_id}
                        className={`flex items-center gap-2 border rounded-md p-2 text-sm ${skipped ? 'bg-[#F3F4F6] border-[#E5E7EB] opacity-60' : 'bg-white border-[#B8D4E8]'}`}
                        data-testid={`apply-template-milestone-row-${idx}`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            {m.is_final_capstone && <Star className="w-3.5 h-3.5 text-[#7C3AED]" />}
                            <span className="font-medium truncate">{m.title || `Week ${m.week_number}`}</span>
                          </div>
                          {m.description && <div className="text-xs text-[#666] truncate">{m.description}</div>}
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span className="text-xs text-[#94B8D9]">orig W{m.week_number} →</span>
                          <Input
                            type="number"
                            min="1"
                            max="52"
                            disabled={skipped}
                            value={skipped ? '' : currentWeek}
                            onChange={(e) => handleWeekChange(m.milestone_id, e.target.value)}
                            className="h-7 w-16 text-center text-sm"
                            data-testid={`apply-template-week-input-${idx}`}
                          />
                          <label className="text-xs flex items-center gap-1 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={skipped}
                              onChange={(e) => toggleSkip(m.milestone_id, e.target.checked)}
                              data-testid={`apply-template-skip-${idx}`}
                            />
                            Skip
                          </label>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="apply-template-cancel-btn">Cancel</Button>
          <Button
            onClick={handleApply}
            disabled={!selectedTemplate || applying || activeCount === 0}
            data-testid="apply-template-confirm-btn"
          >
            {applying ? 'Applying…' : `Apply ${activeCount} milestone${activeCount === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

import React from 'react';
import { Plus, Trash2, GripVertical } from 'lucide-react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../ui/select';
import { SUBMISSION_TYPES, SUBMISSION_TYPE_BY_ID } from '../../config/submissionTypes';

/**
 * Two related fields:
 *  - Submission Type select (5 options: generic homework + 4 named types)
 *  - Questionnaire Field builder (only shown when type === 'business_questionnaire')
 */
export function SubmissionTypeFields({
  submissionType,
  onSubmissionTypeChange,
  questionnaireFields,
  onQuestionnaireFieldsChange,
  idPrefix = 'submission-type',
}) {
  const config = SUBMISSION_TYPE_BY_ID[submissionType] || null;
  const isQuestionnaire = submissionType === 'business_questionnaire';

  const updateField = (idx, patch) => {
    const next = [...questionnaireFields];
    next[idx] = { ...next[idx], ...patch };
    onQuestionnaireFieldsChange(next);
  };

  const addField = () => {
    if (questionnaireFields.length >= 20) return;
    onQuestionnaireFieldsChange([
      ...questionnaireFields,
      { id: `q_${questionnaireFields.length + 1}_${Date.now().toString(36).slice(-4)}`, label: '', type: 'text', required: false },
    ]);
  };

  const removeField = (idx) => {
    const next = questionnaireFields.filter((_, i) => i !== idx);
    onQuestionnaireFieldsChange(next);
  };

  return (
    <div className="space-y-3" data-testid={`${idPrefix}-wrapper`}>
      <div>
        <Label htmlFor={`${idPrefix}-select`}>Homework Format</Label>
        <Select
          value={submissionType || '__generic__'}
          onValueChange={(v) => onSubmissionTypeChange(v === '__generic__' ? '' : v)}
        >
          <SelectTrigger className="mt-1" data-testid={`${idPrefix}-select`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__generic__" data-testid={`${idPrefix}-option-generic`}>
              Generic Homework (any file)
            </SelectItem>
            {SUBMISSION_TYPES.map((t) => (
              <SelectItem key={t.id} value={t.id} data-testid={`${idPrefix}-option-${t.id}`}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {config && (
          <p className="text-xs text-[#666666] mt-1" data-testid={`${idPrefix}-description`}>
            {config.description}
          </p>
        )}
      </div>

      {isQuestionnaire && (
        <div className="border border-[#B8D4E8] rounded-lg p-3 bg-[#F8FBFF] space-y-2" data-testid={`${idPrefix}-questionnaire-builder`}>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Questionnaire Questions</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addField}
              disabled={questionnaireFields.length >= 20}
              className="h-7 text-xs"
              data-testid={`${idPrefix}-add-question-btn`}
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Question
            </Button>
          </div>
          {questionnaireFields.length === 0 && (
            <p className="text-xs text-[#666666] italic">
              No questions yet — add at least one question. Students will see these on the submission page.
            </p>
          )}
          {questionnaireFields.map((f, idx) => (
            <div
              key={f.id}
              className="flex items-start gap-2 bg-white border border-[#E5E7EB] rounded-md p-2"
              data-testid={`${idPrefix}-question-${idx}`}
            >
              <GripVertical className="w-4 h-4 text-[#94B8D9] mt-2 flex-shrink-0" />
              <div className="flex-1 space-y-2">
                <Input
                  placeholder={`Question ${idx + 1} — e.g., "What problem does your business solve?"`}
                  value={f.label}
                  maxLength={300}
                  onChange={(e) => updateField(idx, { label: e.target.value })}
                  data-testid={`${idPrefix}-question-${idx}-label`}
                  className="h-8 text-sm"
                />
                <div className="flex items-center gap-3 text-xs">
                  <Select value={f.type || 'text'} onValueChange={(v) => updateField(idx, { type: v })}>
                    <SelectTrigger className="h-7 w-32" data-testid={`${idPrefix}-question-${idx}-type`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="text">Short answer</SelectItem>
                      <SelectItem value="longtext">Long answer</SelectItem>
                    </SelectContent>
                  </Select>
                  <label className="flex items-center gap-1 text-[#333333]">
                    <input
                      type="checkbox"
                      checked={!!f.required}
                      onChange={(e) => updateField(idx, { required: e.target.checked })}
                      data-testid={`${idPrefix}-question-${idx}-required`}
                    />
                    Required
                  </label>
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => removeField(idx)}
                className="text-red-600 hover:bg-red-50 h-7 w-7"
                data-testid={`${idPrefix}-question-${idx}-remove`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

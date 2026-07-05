import React from 'react';
import { Calendar, File, Download, Upload, MessageSquare, MessageCircle, ChevronUp, ChevronDown, CheckCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { downloadFile } from '../../utils/download';
import { StatusBadge } from './StatusBadge';
import { useBranding } from '../../context/BrandingContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function HomeworkTrackRow({
  hw,
  weekNumber,
  cohortId,
  showLabel,
  isExpanded,
  onToggleExpand,
  onOpenUpload,
  onAskCoachMax,
}) {
  const { branding } = useBranding();
  const persona = branding.ai_persona_name || 'Coach Max';
  const hasFeedback = hw.status === 'feedback_provided' && hw.feedback;
  const hasSubmission = !!hw.submission;
  const canSubmit = hw.status === 'waiting_on_submission' || hw.status === 'submitted' || hw.status === 'under_review' || hw.status === 'feedback_provided';

  return (
    <div
      className="flex items-start gap-3 p-3 rounded-md bg-[#FAFAFA] border border-[#EAEAEA]"
      data-testid={`homework-track-${weekNumber}-${hw.material_id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {showLabel && (
            <span className="text-[10px] font-semibold text-[#22438E] uppercase tracking-wide bg-[#E1F0FF] px-1.5 py-0.5 rounded">
              {showLabel}
            </span>
          )}
          <span className="text-sm font-medium text-[#000000] truncate">{hw.title || 'Homework'}</span>
          <StatusBadge status={hw.status} />
          {hw.due_date && (
            <span className="inline-flex items-center gap-1 text-xs text-[#92400E]">
              <Calendar className="w-3 h-3" />
              Due {new Date(hw.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </span>
          )}
        </div>
        {hw.submission && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              downloadFile(
                `${API_URL}/api/submissions/${hw.submission.submission_id}/download`,
                hw.submission.file_name
              );
            }}
            className="inline-flex items-center gap-1.5 mt-1 text-xs text-[#22438E] hover:text-[#1A3A7A] transition-colors"
            data-testid={`download-submission-${weekNumber}-${hw.material_id}`}
          >
            <File className="w-3 h-3" />
            Your submission: {hw.submission.file_name}
            <Download className="w-3 h-3 ml-0.5" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        {canSubmit && (
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onOpenUpload({ ...hw, cohort_id: cohortId, week_number: weekNumber });
            }}
            className={`rounded-lg text-xs ${
              hasSubmission
                ? 'bg-[#1A75BA] text-white hover:bg-[#713F12]'
                : 'bg-[#22438E] text-white hover:bg-[#1A3A7A]'
            }`}
            data-testid={`submit-week-${weekNumber}-${hw.material_id}`}
          >
            <Upload className="w-3.5 h-3.5 mr-1.5" />
            {hasSubmission ? 'Resubmit' : 'Submit'}
          </Button>
        )}
        {hasFeedback && (
          <Button
            variant="ghost"
            size="sm"
            className="text-[#22438E] hover:bg-[#E1F0FF]"
            onClick={onToggleExpand}
            data-testid={`view-feedback-${weekNumber}-${hw.material_id}`}
          >
            <MessageSquare className="w-4 h-4 mr-1" />
            Feedback
            {isExpanded ? <ChevronUp className="w-4 h-4 ml-1" /> : <ChevronDown className="w-4 h-4 ml-1" />}
          </Button>
        )}
      </div>

      {hasFeedback && isExpanded && (
        <div
          className="basis-full mt-2 rounded-md bg-[#F0FDF4] border border-[#B8D4E8] p-4 animate-fade-in"
          data-testid={`feedback-content-${weekNumber}-${hw.material_id}`}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-[#22438E]" />
              <span className="text-sm font-medium text-[#22438E]">Instructor Feedback</span>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={(e) => {
                e.stopPropagation();
                onAskCoachMax(hw.submission.submission_id, weekNumber);
              }}
              className="border-[#1A75BA] text-[#1A75BA] hover:bg-[#E1F0FF] rounded-lg"
              data-testid={`ask-coach-max-${weekNumber}-${hw.material_id}`}
            >
              <MessageCircle className="w-4 h-4 mr-1.5" />
              Ask {persona}
            </Button>
          </div>
          <div className="text-sm text-[#000000] whitespace-pre-wrap leading-relaxed">
            {hw.feedback}
          </div>
        </div>
      )}
    </div>
  );
}

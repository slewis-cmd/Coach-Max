import React from 'react';
import { Clock, Send, Hourglass, CheckCircle } from 'lucide-react';

const STATUS_CONFIG = {
  no_homework: { label: '', color: '', icon: null },
  waiting_on_submission: {
    label: 'Waiting on Submission',
    color: 'bg-[#FEF3C7] text-[#92400E]',
    icon: Clock
  },
  submitted: {
    label: 'Submitted',
    color: 'bg-[#DBEAFE] text-[#1E40AF]',
    icon: Send
  },
  under_review: {
    label: 'Under Review',
    color: 'bg-[#E1F0FF] text-[#6B21A8]',
    icon: Hourglass
  },
  feedback_provided: {
    label: 'Feedback Provided',
    color: 'bg-[#E1F0FF] text-[#22438E]',
    icon: CheckCircle
  }
};

export function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status];
  if (!config || !config.label) return null;
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${config.color}`}
      data-testid={`status-${status}`}
    >
      {Icon && <Icon className="w-3 h-3" />}
      {config.label}
    </span>
  );
}

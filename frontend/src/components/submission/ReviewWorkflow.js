import React from 'react';

function WorkflowStep({ number, label, active }) {
  const numCls = active ? 'bg-[#E1F0FF] text-[#22438E]' : 'bg-[#B8D4E8] text-[#666666]';
  const liCls = active ? 'text-[#22438E]' : '';
  return (
    <li className={`flex items-center gap-2 ${liCls}`}>
      <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${numCls}`}>
        {number}
      </span>
      {label}
    </li>
  );
}

export function ReviewWorkflow({ hasFeedback, hasInstructorFeedback, isSent }) {
  return (
    <div className="mt-6 p-4 bg-[#D0E6F9] rounded-lg">
      <h3 className="text-sm font-medium text-[#000000] mb-2">Review Workflow</h3>
      <ol className="text-sm text-[#333333] space-y-1">
        <WorkflowStep number={1} label="Generate AI feedback" active={hasFeedback} />
        <WorkflowStep number={2} label="Review and edit feedback" active={hasInstructorFeedback} />
        <WorkflowStep number={3} label="Send feedback to student via email" active={isSent} />
      </ol>
    </div>
  );
}

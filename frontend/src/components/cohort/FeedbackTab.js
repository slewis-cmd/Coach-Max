import React, { useState } from 'react';
import { Card, CardContent } from '../ui/card';
import { useNavigate } from 'react-router-dom';
import { MessageCircle, Eye, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { Button } from '../ui/button';

const statusColors = {
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Pending Review' },
  draft: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Draft' },
  sent: { bg: 'bg-green-100', text: 'text-green-800', label: 'Sent' },
};

function FeedbackRow({ sub, mat }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const status = statusColors[sub.status] || statusColors.pending;
  const feedback = sub.instructor_feedback || sub.ai_feedback;

  return (
    <div data-testid={`feedback-row-${sub.submission_id}`}>
      {/* Row header — always visible */}
      <div
        className={`px-5 py-3 flex items-center gap-3 cursor-pointer transition-colors ${expanded ? 'bg-[#FAFAF8]' : 'hover:bg-[#FAFAF8]'}`}
        onClick={() => feedback && setExpanded(!expanded)}
      >
        {/* Week badge */}
        <div className="w-10 h-10 rounded-lg bg-[#22438E] text-white flex flex-col items-center justify-center flex-shrink-0">
          <span className="text-[10px] leading-none uppercase">Wk</span>
          <span className="text-sm font-semibold leading-none">{mat.week_number || '?'}</span>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[#000000] truncate">{mat.title || sub.file_name}</p>
          <p className="text-xs text-[#666666]">
            {sub.submitted_at ? new Date(sub.submitted_at).toLocaleDateString() : 'No date'}
            {sub.submitted_by && sub.submitted_by !== sub.student_id && ' · Submitted by instructor'}
          </p>
        </div>

        {/* Status */}
        <span className={`text-xs px-2 py-1 rounded-full ${status.bg} ${status.text} flex-shrink-0`}>
          {status.label}
        </span>

        {/* Expand/collapse */}
        {feedback ? (
          <button className="text-[#22438E] p-1" data-testid={`toggle-feedback-${sub.submission_id}`}>
            {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </button>
        ) : (
          <span className="text-xs text-[#94B8D9] italic px-2">No feedback yet</span>
        )}
      </div>

      {/* Expanded feedback content */}
      {expanded && feedback && (
        <div className="px-5 pb-4 pt-1 bg-[#FAFAF8]">
          <div className="ml-[52px] rounded-lg border border-[#BBF7D0] bg-[#F0FDF4] p-4">
            <p className="text-xs font-medium text-[#22438E] mb-2 uppercase tracking-wide">
              {sub.instructor_feedback ? 'Instructor Feedback' : 'AI Feedback (Coach Max)'}
            </p>
            <div className="text-sm text-[#166534] whitespace-pre-wrap leading-relaxed">
              {feedback}
            </div>
            {sub.sent_at && (
              <p className="text-xs text-[#666666] mt-3">
                Sent on {new Date(sub.sent_at).toLocaleDateString()}
              </p>
            )}
          </div>
          <div className="ml-[52px] mt-2">
            <Button variant="ghost" size="sm"
              onClick={() => navigate(`/submissions/${sub.submission_id}`)}
              className="text-[#22438E] hover:bg-[#E1F0FF] text-xs"
              data-testid={`open-detail-${sub.submission_id}`}>
              <ExternalLink className="w-3 h-3 mr-1" />Open full detail
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FeedbackTab({ cohortSubmissions, materials }) {
  // Build a lookup: material_id → { title, week_number }
  const materialMap = {};
  (materials || []).forEach(week => {
    [...(week.homework || []), ...(week.workbooks || []), ...(week.case_studies || [])].forEach(m => {
      materialMap[m.material_id] = { title: m.title, week_number: m.week_number };
    });
  });

  // Group submissions by student
  const byStudent = {};
  (cohortSubmissions || []).forEach(sub => {
    const key = sub.student_id || 'unknown';
    if (!byStudent[key]) {
      byStudent[key] = {
        name: sub.student?.name || sub.student?.email || 'Unknown Student',
        email: sub.student?.email || '',
        submissions: []
      };
    }
    byStudent[key].submissions.push(sub);
  });

  // Sort students alphabetically, then sort each student's submissions by week
  const sortedStudents = Object.entries(byStudent)
    .sort(([, a], [, b]) => a.name.localeCompare(b.name))
    .map(([studentId, data]) => ({
      studentId,
      ...data,
      submissions: data.submissions.sort((a, b) => {
        const weekA = materialMap[a.material_id]?.week_number || 99;
        const weekB = materialMap[b.material_id]?.week_number || 99;
        return weekA - weekB;
      })
    }));

  if (sortedStudents.length === 0) {
    return (
      <div className="text-center py-16">
        <MessageCircle className="w-12 h-12 text-[#94B8D9] mx-auto mb-3" />
        <h3 className="text-lg font-medium text-[#333333] mb-1">No feedback yet</h3>
        <p className="text-sm text-[#666666]">Submissions will appear here once students submit homework.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="feedback-tab">
      <p className="text-sm text-[#666666]">
        {sortedStudents.length} student{sortedStudents.length !== 1 ? 's' : ''} · {cohortSubmissions.length} submission{cohortSubmissions.length !== 1 ? 's' : ''}
      </p>
      {sortedStudents.map(student => (
        <Card key={student.studentId} className="bg-white border-[#B8D4E8]" data-testid={`feedback-student-${student.studentId}`}>
          <CardContent className="p-0">
            {/* Student header */}
            <div className="px-5 py-3 border-b border-[#E1F0FF] flex items-center justify-between">
              <div>
                <h3 className="text-base font-medium text-[#000000]">{student.name}</h3>
                {student.email && <p className="text-xs text-[#666666]">{student.email}</p>}
              </div>
              <span className="text-xs text-[#94B8D9] bg-[#E1F0FF] px-2 py-1 rounded-full">
                {student.submissions.length} submission{student.submissions.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Submissions sorted by week */}
            <div className="divide-y divide-[#E1F0FF]">
              {student.submissions.map(sub => (
                <FeedbackRow
                  key={sub.submission_id}
                  sub={sub}
                  mat={materialMap[sub.material_id] || {}}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

import React from 'react';
import { Card, CardContent } from '../ui/card';
import { useNavigate } from 'react-router-dom';
import { FileDown, MessageCircle, Eye } from 'lucide-react';
import { Button } from '../ui/button';

const statusColors = {
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Pending Review' },
  draft: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Draft' },
  sent: { bg: 'bg-green-100', text: 'text-green-800', label: 'Sent' },
};

export default function FeedbackTab({ cohortSubmissions, materials }) {
  const navigate = useNavigate();

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
              {student.submissions.map(sub => {
                const mat = materialMap[sub.material_id] || {};
                const status = statusColors[sub.status] || statusColors.pending;
                const hasFeedback = sub.ai_feedback || sub.instructor_feedback;

                return (
                  <div key={sub.submission_id} className="px-5 py-3 flex items-center gap-3 hover:bg-[#FAFAF8] transition-colors"
                    data-testid={`feedback-row-${sub.submission_id}`}>
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

                    {/* Actions */}
                    <Button variant="ghost" size="sm"
                      onClick={() => navigate(`/submissions/${sub.submission_id}`)}
                      className="text-[#22438E] hover:bg-[#E1F0FF] flex-shrink-0"
                      data-testid={`view-feedback-${sub.submission_id}`}>
                      {hasFeedback ? <><Eye className="w-4 h-4 mr-1" />View</> : <><FileDown className="w-4 h-4 mr-1" />Review</>}
                    </Button>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

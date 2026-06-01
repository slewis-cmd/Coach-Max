import React from 'react';
import { Card, CardContent } from '../ui/card';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function SubmissionPreviewPane({ submission, submissionId, previewText }) {
  if (!submission) return null;

  const ext = (submission.file_name || '').toLowerCase().split('.').pop();

  if (ext === 'pdf') {
    const token = localStorage.getItem('thinkific_session_token');
    const src = `${API_URL}/api/submissions/${submissionId}/download?inline=1&token=${encodeURIComponent(token || '')}`;
    return (
      <Card className="mb-6 bg-white border-[#B8D4E8] lg:sticky lg:top-20 lg:mb-0" data-testid="preview-pdf">
        <CardContent className="p-0">
          <iframe
            title="Submission preview"
            src={src}
            className="w-full h-[720px] rounded-md"
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mb-6 bg-white border-[#B8D4E8] lg:sticky lg:top-20 lg:mb-0" data-testid="preview-docx">
      <CardContent className="p-6">
        <pre className="whitespace-pre-wrap text-sm text-[#1A1A1A] font-sans leading-relaxed max-h-[720px] overflow-auto">
          {previewText || 'No extractable text in this file.'}
        </pre>
      </CardContent>
    </Card>
  );
}

import React from 'react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import {
  Trash2, Download, Copy, Eye, RefreshCw, Link2, Unlink, CheckCircle, Sparkles,
} from 'lucide-react';

export function LibraryMaterialCard({
  mat,
  previewLoading,
  previewMat,
  typeIcon,
  typeBg,
  typeLabel,
  apiUrl,
  downloadFile,
  onPreview,
  onDuplicate,
  onEditFeedbackTemplate,
  onDelete,
  onUnassign,
  onOpenAssign,
}) {
  return (
    <Card className="bg-white border-[#B8D4E8]" data-testid={`library-material-${mat.material_id}`}>
      <CardContent className="p-5">
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 ${typeBg(mat.material_type)} rounded-lg flex items-center justify-center flex-shrink-0`}>
            {typeIcon(mat.material_type)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between mb-1">
              <div>
                <h3 className="font-medium text-[#000000] flex items-center gap-2 flex-wrap">
                  {mat.title}
                  {mat.is_global && (
                    <span
                      className="inline-flex items-center gap-1 text-[10px] font-medium bg-[#22438E] text-white px-2 py-0.5 rounded-full uppercase tracking-wide"
                      data-testid={`global-badge-${mat.material_id}`}
                    >
                      Course-Wide
                    </span>
                  )}
                  {mat.material_type === 'video' && mat.video_url && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-[#EF4444] text-white px-2 py-0.5 rounded-full uppercase tracking-wide">
                      External Link
                    </span>
                  )}
                  {mat.material_type === 'video' && mat.transcription_status === 'pending' && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-[#F59E0B] text-white px-2 py-0.5 rounded-full">
                      <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                      Transcribing…
                    </span>
                  )}
                  {mat.material_type === 'video' && mat.transcription_status === 'done' && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-[#22438E] text-white px-2 py-0.5 rounded-full">
                      Transcript ready
                    </span>
                  )}
                  {mat.material_type === 'video' && (mat.transcription_status === 'failed' || mat.transcription_status === 'failed_too_large') && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-[#EF4444] text-white px-2 py-0.5 rounded-full">
                      Transcription failed
                    </span>
                  )}
                  {mat.material_type === 'homework' && mat.feedback_template && (
                    <span
                      className="inline-flex items-center gap-1 text-[10px] font-medium bg-[#7C3AED] text-white px-2 py-0.5 rounded-full uppercase tracking-wide"
                      title={mat.feedback_template}
                      data-testid={`custom-rubric-badge-${mat.material_id}`}
                    >
                      <Sparkles className="w-2.5 h-2.5" />
                      Custom Rubric
                    </span>
                  )}
                </h3>
                <p className="text-xs text-[#666666]">
                  {mat.is_global ? 'All weeks' : `Week ${mat.week_number}`} · {typeLabel(mat.material_type)} · {mat.material_type === 'video' && mat.video_url ? mat.video_url : mat.file_name}
                </p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0 ml-4">
                <Button
                  variant="ghost" size="icon"
                  onClick={() => onPreview(mat)}
                  disabled={previewLoading}
                  title="View / Read"
                  data-testid={`view-lib-${mat.material_id}`}
                >
                  {previewLoading && previewMat?.material_id === mat.material_id ? (
                    <RefreshCw className="w-4 h-4 text-[#22438E] animate-spin" />
                  ) : (
                    <Eye className="w-4 h-4 text-[#22438E]" />
                  )}
                </Button>
                {!(mat.material_type === 'video' && mat.video_url) && (
                  <Button
                    variant="ghost" size="icon"
                    onClick={() => downloadFile(`${apiUrl}/api/materials/${mat.material_id}/download`, mat.file_name)}
                    title="Download"
                    data-testid={`download-lib-${mat.material_id}`}
                  >
                    <Download className="w-4 h-4 text-[#333333]" />
                  </Button>
                )}
                <Button
                  variant="ghost" size="icon"
                  onClick={() => onDuplicate(mat.material_id)}
                  title="Duplicate / Save as Template"
                  data-testid={`duplicate-lib-${mat.material_id}`}
                >
                  <Copy className="w-4 h-4 text-[#22438E]" />
                </Button>
                {mat.material_type === 'homework' && (
                  <Button
                    variant="ghost" size="icon"
                    onClick={() => onEditFeedbackTemplate(mat)}
                    title={mat.feedback_template ? 'Edit AI feedback instructions' : 'Add custom AI feedback instructions'}
                    data-testid={`edit-feedback-template-lib-${mat.material_id}`}
                  >
                    <Sparkles className={`w-4 h-4 ${mat.feedback_template ? 'text-[#22438E]' : 'text-[#666666]'}`} />
                  </Button>
                )}
                <Button
                  variant="ghost" size="icon"
                  onClick={() => onDelete(mat.material_id)}
                  data-testid={`delete-lib-${mat.material_id}`}
                >
                  <Trash2 className="w-4 h-4 text-red-500" />
                </Button>
              </div>
            </div>
            {mat.description && (
              <p className="text-sm text-[#333333] mb-3">{mat.description}</p>
            )}

            {/* Assigned Cohorts */}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <span className="text-xs text-[#666666] mr-1">Assigned to:</span>
              {mat.assigned_cohorts?.length > 0 ? (
                mat.assigned_cohorts.map((c) => (
                  <span key={c.cohort_id} className="inline-flex items-center gap-1 text-xs bg-[#E1F0FF] text-[#22438E] px-2 py-1 rounded-full">
                    <CheckCircle className="w-3 h-3" />
                    {c.name}
                    <button
                      onClick={() => onUnassign(mat.material_id, c.cohort_id)}
                      className="ml-0.5 hover:text-red-600"
                      title="Remove from cohort"
                      data-testid={`unassign-${mat.material_id}-${c.cohort_id}`}
                    >
                      <Unlink className="w-3 h-3" />
                    </button>
                  </span>
                ))
              ) : (
                <span className="text-xs text-[#94B8D9]">None yet</span>
              )}
              <button
                onClick={() => onOpenAssign(mat.material_id)}
                className="inline-flex items-center gap-1 text-xs text-[#22438E] hover:text-[#1A3A7A] bg-[#E1F0FF] px-2 py-1 rounded-full"
                data-testid={`assign-btn-${mat.material_id}`}
              >
                <Link2 className="w-3 h-3" />
                Assign
              </button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

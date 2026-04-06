import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { 
  BookMarked, ClipboardList, Upload, Trash2, File, Download, Calendar, Eye, EyeOff, Copy 
} from 'lucide-react';
import { toast } from 'sonner';

const STATUS_STYLES = {
  sent: { className: 'bg-[#E1F0FF] text-[#22438E]', label: 'Reviewed' },
  draft: { className: 'bg-[#E1F0FF] text-[#6B21A8]', label: 'Draft' },
  pending: { className: 'bg-[#DBEAFE] text-[#1E40AF]', label: 'Pending' },
};

function SubmissionStatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${style.className}`}>
      {style.label}
    </span>
  );
}

export function MaterialsTab({
  materials, cohort, isInstructor, cohortSubmissions,
  onDownloadMaterial, onDeleteMaterial, onSelectHomework, onToggleWeek, onUploadMaterial
}) {
  const downloadFile = async (url, filename) => {
    const token = localStorage.getItem('thinkific_session_token');
    if (!token) { toast.error('Please log in to download files'); return; }
    const sep = url.includes('?') ? '&' : '?';
    try {
      const res = await fetch(`${url}${sep}token=${encodeURIComponent(token)}`);
      if (!res.ok) throw new Error(await res.text() || 'Download failed');
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = filename || 'download';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      toast.error('Failed to download file');
    }
  };

  const API_URL = process.env.REACT_APP_BACKEND_URL;

  if (materials.length === 0) {
    return (
      <Card className="bg-white border-[#B8D4E8] border-dashed">
        <CardContent className="p-12 text-center">
          <File className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
          <h3 className="text-lg font-medium text-[#000000] mb-2">No materials yet</h3>
          <p className="text-[#333333] mb-4">
            {isInstructor ? 'Upload your first workbook, case study, or homework assignment' : 'Your instructor will upload materials soon'}
          </p>
          {isInstructor && (
            <Button onClick={onUploadMaterial} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">
              Upload Material
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  return materials.sort((a, b) => a.week_number - b.week_number).map((week) => (
    <div key={week.week_number} className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-[#000000] text-white rounded-full flex items-center justify-center font-medium">
          {week.week_number}
        </div>
        <h2 className="text-xl font-light text-[#000000]">Week {week.week_number}</h2>
        {isInstructor && (
          <Button
            variant="ghost" size="sm"
            onClick={() => onToggleWeek(week.week_number)}
            className={`ml-auto rounded-lg text-xs ${
              (cohort?.released_weeks || []).includes(week.week_number)
                ? 'text-[#22438E] hover:bg-[#E1F0FF]' : 'text-[#666666] hover:bg-[#D0E6F9]'
            }`}
            data-testid={`toggle-week-${week.week_number}`}
          >
            {(cohort?.released_weeks || []).includes(week.week_number) ? (
              <><Eye className="w-4 h-4 mr-1.5" />Visible to students</>
            ) : (
              <><EyeOff className="w-4 h-4 mr-1.5" />Hidden from students</>
            )}
          </Button>
        )}
      </div>

      <div className="grid md:grid-cols-3 gap-4 pl-12">
        {/* Workbooks */}
        {week.workbooks?.map((mat) => (
          <Card key={mat.material_id} className="bg-white border-[#B8D4E8] group">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
                  <BookMarked className="w-5 h-5 text-[#22438E]" />
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => onDownloadMaterial(mat.material_id, mat.file_name)} data-testid={`download-${mat.material_id}`}>
                    <Download className="w-4 h-4 text-[#22438E]" />
                  </Button>
                  {isInstructor && (
                    <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => onDeleteMaterial(mat.material_id)}>
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </Button>
                  )}
                </div>
              </div>
              <CardTitle className="text-base font-medium mt-2">{mat.title}</CardTitle>
              <CardDescription className="text-xs uppercase tracking-wide">
                Workbook{mat.is_library ? ' · Shared from Library' : ''}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[#333333] mb-3">{mat.description || 'No description'}</p>
              <div className="flex items-center justify-between">
                <p className="text-xs text-[#666666]"><File className="w-3 h-3 inline mr-1" />{mat.file_name}</p>
                <Button variant="ghost" size="sm" className="text-[#22438E] hover:text-[#1A3A7A] h-7 px-2"
                  onClick={() => onDownloadMaterial(mat.material_id, mat.file_name)}>
                  <Download className="w-3 h-3 mr-1" />Download
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}

        {/* Case Studies */}
        {week.case_studies?.map((mat) => (
          <Card key={mat.material_id} className="bg-white border-[#B8D4E8] group">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="w-10 h-10 bg-[#7CBAE6] rounded-lg flex items-center justify-center">
                  <ClipboardList className="w-5 h-5 text-[#000000]" />
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => onDownloadMaterial(mat.material_id, mat.file_name)} data-testid={`download-${mat.material_id}`}>
                    <Download className="w-4 h-4 text-[#1A75BA]" />
                  </Button>
                  {isInstructor && (
                    <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => onDeleteMaterial(mat.material_id)}>
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </Button>
                  )}
                </div>
              </div>
              <CardTitle className="text-base font-medium mt-2">{mat.title}</CardTitle>
              <CardDescription className="text-xs uppercase tracking-wide">
                Case Study{mat.is_library ? ' · Shared from Library' : ''}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[#333333] mb-3">{mat.description || 'No description'}</p>
              <div className="flex items-center justify-between">
                <p className="text-xs text-[#666666]"><File className="w-3 h-3 inline mr-1" />{mat.file_name}</p>
                <Button variant="ghost" size="sm" className="text-[#1A75BA] hover:text-[#713F12] h-7 px-2"
                  onClick={() => onDownloadMaterial(mat.material_id, mat.file_name)}>
                  <Download className="w-3 h-3 mr-1" />Download
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}

        {/* Homework */}
        {week.homework?.map((mat) => (
          <Card key={mat.material_id} className="bg-white border-[#B8D4E8] group">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
                  <Upload className="w-5 h-5 text-[#22438E]" />
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => onDownloadMaterial(mat.material_id, mat.file_name)} data-testid={`download-${mat.material_id}`}>
                    <Download className="w-4 h-4 text-[#22438E]" />
                  </Button>
                  {isInstructor && (
                    <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => onDeleteMaterial(mat.material_id)}>
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </Button>
                  )}
                </div>
              </div>
              <CardTitle className="text-base font-medium mt-2">{mat.title}</CardTitle>
              <CardDescription className="text-xs uppercase tracking-wide">Homework Assignment</CardDescription>
              {mat.due_date && (
                <div className={`flex items-center gap-1 mt-2 text-xs ${
                  new Date(mat.due_date) < new Date() ? 'text-red-500' : 'text-[#1A75BA]'
                }`}>
                  <Calendar className="w-3 h-3" />
                  Due: {new Date(mat.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  {new Date(mat.due_date) < new Date() && ' (Past due)'}
                </div>
              )}
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[#333333] mb-3">{mat.description || 'No description'}</p>
              {!isInstructor ? (
                <Button size="sm"
                  onClick={() => onSelectHomework(mat)}
                  className="w-full bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
                  data-testid={`submit-homework-${mat.material_id}`}>
                  Submit Homework
                </Button>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-xs text-[#666666]"><File className="w-3 h-3 inline mr-1" />{mat.file_name}</p>
                    <Button variant="ghost" size="sm" className="text-[#22438E] hover:text-[#1A3A7A] h-7 px-2"
                      onClick={() => onDownloadMaterial(mat.material_id, mat.file_name)}>
                      <Download className="w-3 h-3 mr-1" />Download
                    </Button>
                  </div>
                  <Button
                    variant="outline" size="sm"
                    className="w-full border-[#1A75BA] text-[#1A75BA] hover:bg-[#E1F0FF] rounded-lg mb-3"
                    data-testid={`copy-submit-link-${mat.material_id}`}
                    onClick={() => {
                      const link = `${window.location.origin}/submit/${mat.material_id}?cohort=${cohort.cohort_id}`;
                      navigator.clipboard.writeText(link).then(() => {
                        toast.success('Submission link copied!');
                      }).catch(() => {
                        toast.error('Failed to copy link');
                      });
                    }}>
                    <Copy className="w-3.5 h-3.5 mr-1.5" />Copy Submission Link for Thinkific
                  </Button>
                  {/* Student Submissions */}
                  {(() => {
                    const subs = cohortSubmissions.filter(s => s.material_id === mat.material_id);
                    if (subs.length === 0) return (
                      <p className="text-xs text-[#666666] italic pt-2 border-t border-[#B8D4E8]">No submissions yet</p>
                    );
                    return (
                      <div className="pt-2 border-t border-[#B8D4E8] space-y-2" data-testid={`submissions-${mat.material_id}`}>
                        <p className="text-xs font-medium text-[#333333] uppercase tracking-wide">Submissions ({subs.length})</p>
                        {subs.map(sub => (
                          <div key={sub.submission_id} className="rounded-lg bg-[#E1F0FF] overflow-hidden" data-testid={`sub-row-${sub.submission_id}`}>
                            <div className="flex items-center gap-2 py-2 px-3">
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-[#000000] truncate">{sub.student?.name || 'Unknown'}</p>
                                <p className="text-xs text-[#666666] truncate">{sub.file_name}</p>
                              </div>
                              <SubmissionStatusBadge status={sub.status} />
                              <button
                                onClick={() => downloadFile(
                                  `${API_URL}/api/submissions/${sub.submission_id}/download`,
                                  sub.file_name
                                )}
                                className="text-[#22438E] hover:text-[#1A3A7A] p-1 flex-shrink-0"
                                title="Download submission"
                                data-testid={`download-sub-${sub.submission_id}`}>
                                <Download className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  ));
}

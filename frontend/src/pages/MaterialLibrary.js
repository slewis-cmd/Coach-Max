import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { 
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter
} from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { 
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../components/ui/select';
import { 
  ArrowLeft, Upload, BookMarked, ClipboardList, File, RefreshCw, Video, Play, Plus
} from 'lucide-react';
import { FeedbackTemplateField, EditFeedbackTemplateDialog } from '../components/rubric/FeedbackTemplateField';
import { SubmissionTypeFields } from '../components/material/SubmissionTypeFields';
import { LibraryMaterialCard } from '../components/material/LibraryMaterialCard';
import { AssignCohortDialog } from '../components/material/AssignCohortDialog';
import { LibraryPreviewDialog } from '../components/material/LibraryPreviewDialog';
import { SUBMISSION_TYPE_BY_ID } from '../config/submissionTypes';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const downloadFile = async (url, filename) => {
  const token = localStorage.getItem('thinkific_session_token');
  if (!token) { toast.error('Please log in'); return; }
  const sep = url.includes('?') ? '&' : '?';
  try {
    const response = await fetch(`${url}${sep}token=${encodeURIComponent(token)}`);
    if (!response.ok) throw new Error('Download failed');
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename || 'download';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  } catch { toast.error('Failed to download file'); }
};

export default function MaterialLibrary() {
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [materials, setMaterials] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [showAssign, setShowAssign] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', week_number: 1, material_type: 'workbook', file: null, is_global: false, video_url: '', feedback_template: '', submission_type: '', questionnaire_fields: []
  });
  // Filter: show all | week-based | course-wide only
  const [filter, setFilter] = useState('all');
  // Inline preview state
  const [previewMat, setPreviewMat] = useState(null);     // material being previewed (null when closed)
  const [previewText, setPreviewText] = useState('');     // DOCX extracted text
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [matRes, cohortRes] = await Promise.all([
        axios.get(`${API_URL}/api/library/materials`),
        axios.get(`${API_URL}/api/cohorts`)
      ]);
      setMaterials(matRes.data);
      setCohorts(cohortRes.data);
    } catch (error) {
      toast.error('Failed to load library');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isInstructor) {
      fetchData();
    }
  }, [authLoading, isInstructor, fetchData]);

  const handleUpload = async () => {
    if (!form.title.trim()) {
      toast.error('Please provide a title');
      return;
    }
    const isVideo = form.material_type === 'video';
    const usingUrl = isVideo && !!form.video_url.trim();
    if (isVideo) {
      if (!form.file && !usingUrl) {
        toast.error('For a video, either upload a file or paste a YouTube/Vimeo URL');
        return;
      }
    } else if (!form.file) {
      toast.error('Please select a file');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      if (form.file && !usingUrl) formData.append('file', form.file);
      // Backend expects non-file fields as query parameters
      const params = new URLSearchParams({
        title: form.title,
        description: form.description || '',
        week_number: form.week_number,
        material_type: form.material_type,
        is_global: form.is_global ? 'true' : 'false',
        video_url: usingUrl ? form.video_url.trim() : '',
        feedback_template: form.material_type === 'homework' ? (form.feedback_template || '') : '',
        submission_type: form.material_type === 'homework' ? (form.submission_type || '') : '',
        questionnaire_fields: (form.material_type === 'homework' && form.submission_type === 'business_questionnaire')
          ? JSON.stringify(form.questionnaire_fields || [])
          : ''
      });
      await axios.post(`${API_URL}/api/library/materials?${params.toString()}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      toast.success(isVideo && !usingUrl ? 'Video uploaded — transcription in progress' : 'Material added to library!');
      setShowUpload(false);
      setForm({ title: '', description: '', week_number: 1, material_type: 'workbook', file: null, is_global: false, video_url: '', feedback_template: '', submission_type: '', questionnaire_fields: [] });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (materialId) => {
    if (!window.confirm('Delete this material from the library? It will be removed from all cohorts.')) return;
    try {
      await axios.delete(`${API_URL}/api/library/materials/${materialId}`);
      toast.success('Material deleted');
      fetchData();
    } catch (error) {
      toast.error('Failed to delete');
    }
  };

  const [editingRubricMaterial, setEditingRubricMaterial] = useState(null);

  const handleEditFeedbackTemplate = (mat) => {
    setEditingRubricMaterial(mat);
  };

  const handleDuplicate = async (materialId) => {
    try {
      await axios.post(`${API_URL}/api/library/materials/${materialId}/duplicate`);
      toast.success('Material duplicated as template');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to duplicate');
    }
  };

  const handlePreview = async (mat) => {
    // Videos: open dialog directly, no text extraction
    if (mat.material_type === 'video') {
      setPreviewMat(mat);
      setPreviewText('');
      return;
    }
    const ext = (mat.file_name || '').toLowerCase().split('.').pop();
    if (ext === 'pdf') {
      setPreviewMat(mat);
      setPreviewText('');
      return;
    }
    // DOCX: fetch extracted text
    setPreviewLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/materials/${mat.material_id}/preview-text`);
      setPreviewText(res.data.text || '');
      setPreviewMat(mat);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Could not load preview');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleAssign = async (materialId, cohortId) => {
    try {
      await axios.post(`${API_URL}/api/library/materials/${materialId}/assign`, {
        cohort_ids: [cohortId]
      });
      toast.success('Material assigned to cohort');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to assign');
    }
  };

  const handleUnassign = async (materialId, cohortId) => {
    try {
      await axios.post(`${API_URL}/api/library/materials/${materialId}/unassign`, {
        cohort_id: cohortId
      });
      toast.success('Material removed from cohort');
      fetchData();
    } catch (error) {
      toast.error('Failed to remove');
    }
  };

  // Memoize filtered materials to avoid re-filtering on every render
  const filteredMaterials = useMemo(() => {
    return materials.filter((m) => {
      if (filter === 'all') return true;
      if (filter === 'global') return !!m.is_global;
      if (filter === 'video') return m.material_type === 'video';
      return !m.is_global;
    });
  }, [materials, filter]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const typeIcon = (type) => {
    if (type === 'workbook') return <BookMarked className="w-5 h-5 text-[#22438E]" />;
    if (type === 'case_study') return <ClipboardList className="w-5 h-5 text-[#1A75BA]" />;
    if (type === 'video') return <Video className="w-5 h-5 text-[#22438E]" />;
    return <File className="w-5 h-5 text-[#22438E]" />;
  };

  const typeBg = (type) => {
    if (type === 'workbook') return 'bg-[#E1F0FF]';
    if (type === 'case_study') return 'bg-[#7CBAE6]';
    if (type === 'video') return 'bg-[#FDE68A]';
    return 'bg-[#E1F0FF]';
  };

  const typeLabel = (type) => {
    if (type === 'workbook') return 'Workbook';
    if (type === 'case_study') return 'Case Study';
    if (type === 'video') return 'Video';
    return 'Homework';
  };

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="material-library">
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/dashboard" className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors">
              <ArrowLeft className="w-5 h-5 text-[#333333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000000]">Material Library</h1>
              <p className="text-sm text-[#666666]">Upload once, share across cohorts</p>
            </div>
          </div>
          <Button 
            onClick={() => setShowUpload(true)}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
            data-testid="upload-library-btn"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Material
          </Button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 md:px-12 py-8">
        {/* Filter tabs */}
        {materials.length > 0 && (
          <div className="mb-5 flex items-center gap-2" data-testid="library-filter">
            {[
              { key: 'all', label: 'All' },
              { key: 'week', label: 'Weekly' },
              { key: 'global', label: 'Course-Wide' },
              { key: 'video', label: 'Videos' },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                  filter === key
                    ? 'bg-[#22438E] text-white border-[#22438E]'
                    : 'bg-white text-[#22438E] border-[#B8D4E8] hover:bg-[#E1F0FF]'
                }`}
                data-testid={`library-filter-${key}`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {materials.length === 0 ? (
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <BookMarked className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#000000] mb-2">Library is empty</h3>
              <p className="text-[#333333] mb-4">Upload workbooks, case studies, and homework to share across cohorts</p>
              <Button onClick={() => setShowUpload(true)} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">
                Add First Material
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {filteredMaterials.map((mat) => (
              <LibraryMaterialCard
                key={mat.material_id}
                mat={mat}
                previewLoading={previewLoading}
                previewMat={previewMat}
                typeIcon={typeIcon}
                typeBg={typeBg}
                typeLabel={typeLabel}
                apiUrl={API_URL}
                downloadFile={downloadFile}
                onPreview={handlePreview}
                onDuplicate={handleDuplicate}
                onEditFeedbackTemplate={handleEditFeedbackTemplate}
                onDelete={handleDelete}
                onUnassign={handleUnassign}
                onOpenAssign={setShowAssign}
              />
            ))}
          </div>
        )}
      </main>

      {/* Upload Dialog */}
      <Dialog open={showUpload} onOpenChange={setShowUpload}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Add to Library</DialogTitle>
            <DialogDescription>Upload a workbook, case study, or homework to share across cohorts.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="lib-title">Title</Label>
              <Input id="lib-title" data-testid="lib-title-input" placeholder="e.g., Leadership Foundations Workbook"
                value={form.title} onChange={(e) => setForm({...form, title: e.target.value})} className="mt-1" />
            </div>
            <div>
              <Label htmlFor="lib-desc">Description (optional)</Label>
              <Textarea id="lib-desc" data-testid="lib-desc-input" placeholder="Brief description..."
                value={form.description} onChange={(e) => setForm({...form, description: e.target.value})} className="mt-1" rows={2} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Week Number</Label>
                <Select
                  value={String(form.week_number)}
                  onValueChange={(v) => setForm({...form, week_number: parseInt(v)})}
                  disabled={form.is_global}
                >
                  <SelectTrigger className="mt-1" data-testid="lib-week-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Array.from({length: 14}, (_, i) => (
                      <SelectItem key={i+1} value={String(i+1)}>Week {i+1}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Type</Label>
                <Select value={form.material_type} onValueChange={(v) => setForm({...form, material_type: v})}>
                  <SelectTrigger className="mt-1" data-testid="lib-material-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="workbook">Workbook</SelectItem>
                    <SelectItem value="case_study">Case Study</SelectItem>
                    <SelectItem value="homework">Homework</SelectItem>
                    <SelectItem value="video">Video</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {form.material_type === 'homework' && (
              <SubmissionTypeFields
                submissionType={form.submission_type || ''}
                onSubmissionTypeChange={(v) => setForm({ ...form, submission_type: v })}
                questionnaireFields={form.questionnaire_fields || []}
                onQuestionnaireFieldsChange={(v) => setForm({ ...form, questionnaire_fields: v })}
                idPrefix="lib-submission-type"
              />
            )}
            {form.material_type === 'homework' && (
              <FeedbackTemplateField
                value={form.feedback_template}
                onChange={(v) => setForm({ ...form, feedback_template: v })}
                idPrefix="lib-feedback-template"
              />
            )}
            <label className="flex items-start gap-3 p-3 border border-[#B8D4E8] rounded-lg cursor-pointer hover:bg-[#E1F0FF] transition-colors" data-testid="lib-is-global-toggle">
              <input
                type="checkbox"
                className="mt-1 w-4 h-4 accent-[#22438E]"
                checked={form.is_global}
                onChange={(e) => setForm({...form, is_global: e.target.checked})}
              />
              <div className="flex-1">
                <div className="text-sm font-medium text-[#000000]">Course-Wide Resource</div>
                <div className="text-xs text-[#666666] mt-0.5">
                  Applies across all weeks. Automatically included in every AI feedback prompt and shown at the top of the student dashboard.
                </div>
              </div>
            </label>
            {form.material_type === 'video' ? (
              <div className="space-y-3">
                <div>
                  <Label htmlFor="lib-video-url">YouTube / Vimeo / Loom URL</Label>
                  <Input
                    id="lib-video-url"
                    data-testid="lib-video-url-input"
                    placeholder="https://youtube.com/watch?v=..."
                    value={form.video_url}
                    onChange={(e) => setForm({...form, video_url: e.target.value, file: e.target.value ? null : form.file})}
                    className="mt-1"
                    disabled={!!form.file}
                  />
                  <p className="text-xs text-[#666666] mt-1">Paste a video URL (external videos are stored as a link).</p>
                </div>
                <div className="text-xs text-center text-[#666666]">— or —</div>
                <div>
                  <Label>Upload video file (MP4, MOV, WEBM, up to ~100 MB)</Label>
                  <div className="mt-1">
                    <label htmlFor="lib-video-file-upload" className={`flex items-center justify-center gap-2 p-4 border-2 border-dashed border-[#B8D4E8] rounded-lg transition-colors ${form.video_url ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-[#000000]'}`}>
                      <Upload className="w-5 h-5 text-[#666666]" />
                      <span className="text-sm text-[#333333]">
                        {form.file ? form.file.name : 'Click to select video file'}
                      </span>
                    </label>
                    <input
                      id="lib-video-file-upload"
                      data-testid="lib-video-file-input"
                      type="file"
                      accept="video/*,.mp4,.mov,.webm,.m4v,.mp3,.m4a,.wav"
                      className="hidden"
                      disabled={!!form.video_url}
                      onChange={(e) => setForm({...form, file: e.target.files?.[0] || null, video_url: e.target.files?.[0] ? '' : form.video_url})}
                    />
                  </div>
                  <p className="text-xs text-[#666666] mt-1">Uploaded videos are automatically transcribed via Whisper so the AI can reference them.</p>
                </div>
              </div>
            ) : (
              <div>
                <Label>File (PDF or DOCX)</Label>
                <div className="mt-1">
                  <label htmlFor="lib-file-upload" className="flex items-center justify-center gap-2 p-4 border-2 border-dashed border-[#B8D4E8] rounded-lg cursor-pointer hover:border-[#000000] transition-colors">
                    <Upload className="w-5 h-5 text-[#666666]" />
                    <span className="text-sm text-[#333333]">
                      {form.file ? form.file.name : 'Click to select file'}
                    </span>
                  </label>
                  <input id="lib-file-upload" data-testid="lib-file-input" type="file" accept=".pdf,.docx"
                    className="hidden" onChange={(e) => setForm({...form, file: e.target.files?.[0] || null})} />
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUpload(false)}>Cancel</Button>
            <Button onClick={handleUpload} disabled={uploading} className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
              data-testid="lib-upload-submit">
              {uploading ? 'Uploading...' : 'Add to Library'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assign to Cohort Dialog */}
      <AssignCohortDialog
        open={!!showAssign}
        onOpenChange={(open) => { if (!open) setShowAssign(null); }}
        cohorts={cohorts}
        materials={materials}
        selectedMaterialId={showAssign}
        onAssign={handleAssign}
        onUnassign={handleUnassign}
      />

      {/* Inline File Preview Dialog */}
      <LibraryPreviewDialog
        previewMat={previewMat}
        previewText={previewText}
        onClose={() => { setPreviewMat(null); setPreviewText(''); }}
        apiUrl={API_URL}
        downloadFile={downloadFile}
      />

      <EditFeedbackTemplateDialog
        open={!!editingRubricMaterial}
        onOpenChange={(open) => !open && setEditingRubricMaterial(null)}
        material={editingRubricMaterial}
        onSaved={() => { setEditingRubricMaterial(null); fetchData(); }}
      />
    </div>
  );
}

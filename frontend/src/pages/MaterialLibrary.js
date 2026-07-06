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
  ArrowLeft, Upload, BookMarked, ClipboardList, Trash2, Download, 
  Plus, Link2, Unlink, File, CheckCircle, Copy, Eye, RefreshCw, Video, Play, Sparkles
} from 'lucide-react';
import { FeedbackTemplateField, EditFeedbackTemplateDialog } from '../components/rubric/FeedbackTemplateField';
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
    title: '', description: '', week_number: 1, material_type: 'workbook', file: null, is_global: false, video_url: '', feedback_template: ''
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
        feedback_template: form.material_type === 'homework' ? (form.feedback_template || '') : ''
      });
      await axios.post(`${API_URL}/api/library/materials?${params.toString()}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      toast.success(isVideo && !usingUrl ? 'Video uploaded — transcription in progress' : 'Material added to library!');
      setShowUpload(false);
      setForm({ title: '', description: '', week_number: 1, material_type: 'workbook', file: null, is_global: false, video_url: '', feedback_template: '' });
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
              <Card key={mat.material_id} className="bg-white border-[#B8D4E8]" data-testid={`library-material-${mat.material_id}`}>
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
                            onClick={() => handlePreview(mat)}
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
                              onClick={() => downloadFile(`${API_URL}/api/materials/${mat.material_id}/download`, mat.file_name)}
                              title="Download"
                              data-testid={`download-lib-${mat.material_id}`}
                            >
                              <Download className="w-4 h-4 text-[#333333]" />
                            </Button>
                          )}
                          <Button
                            variant="ghost" size="icon"
                            onClick={() => handleDuplicate(mat.material_id)}
                            title="Duplicate / Save as Template"
                            data-testid={`duplicate-lib-${mat.material_id}`}
                          >
                            <Copy className="w-4 h-4 text-[#22438E]" />
                          </Button>
                          {mat.material_type === 'homework' && (
                            <Button
                              variant="ghost" size="icon"
                              onClick={() => handleEditFeedbackTemplate(mat)}
                              title={mat.feedback_template ? 'Edit AI feedback instructions' : 'Add custom AI feedback instructions'}
                              data-testid={`edit-feedback-template-lib-${mat.material_id}`}
                            >
                              <Sparkles className={`w-4 h-4 ${mat.feedback_template ? 'text-[#22438E]' : 'text-[#666666]'}`} />
                            </Button>
                          )}
                          <Button 
                            variant="ghost" size="icon"
                            onClick={() => handleDelete(mat.material_id)}
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
                                onClick={() => handleUnassign(mat.material_id, c.cohort_id)}
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
                          onClick={() => setShowAssign(mat.material_id)}
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
      <Dialog open={!!showAssign} onOpenChange={() => setShowAssign(null)}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Assign to Cohorts</DialogTitle>
            <DialogDescription>Select cohorts to share this material with.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4 max-h-[400px] overflow-y-auto">
            {cohorts.length === 0 ? (
              <p className="text-sm text-[#666666] text-center py-4">No cohorts found.</p>
            ) : (
              cohorts.map((cohort) => {
                const mat = materials.find(m => m.material_id === showAssign);
                const isAssigned = mat?.cohort_ids?.includes(cohort.cohort_id);
                return (
                  <div 
                    key={cohort.cohort_id}
                    className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                      isAssigned ? 'border-[#22438E] bg-[#E1F0FF]' : 'border-[#B8D4E8] hover:bg-[#E1F0FF]'
                    }`}
                    onClick={() => {
                      if (isAssigned) {
                        handleUnassign(showAssign, cohort.cohort_id);
                      } else {
                        handleAssign(showAssign, cohort.cohort_id);
                      }
                    }}
                    data-testid={`assign-cohort-${cohort.cohort_id}`}
                  >
                    <div>
                      <p className="font-medium text-[#000000]">{cohort.name}</p>
                      <p className="text-xs text-[#666666]">{cohort.student_ids?.length || 0} students</p>
                    </div>
                    {isAssigned ? (
                      <span className="text-xs bg-[#22438E] text-white px-2 py-0.5 rounded-full">Assigned</span>
                    ) : (
                      <span className="text-xs text-[#666666]">Click to assign</span>
                    )}
                  </div>
                );
              })
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAssign(null)} className="rounded-lg">Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Inline File Preview Dialog */}
      <Dialog open={!!previewMat} onOpenChange={(open) => { if (!open) { setPreviewMat(null); setPreviewText(''); } }}>
        <DialogContent className="bg-white max-w-5xl w-[95vw] p-0" data-testid="library-preview-dialog">
          <DialogHeader className="px-6 pt-6 pb-3 border-b border-[#B8D4E8]">
            <DialogTitle className="font-normal text-xl flex items-center justify-between gap-4">
              <span className="truncate">{previewMat?.title || 'Preview'}</span>
              {!(previewMat?.material_type === 'video' && previewMat?.video_url) && (
                <button
                  onClick={() => downloadFile(`${API_URL}/api/materials/${previewMat?.material_id}/download`, previewMat?.file_name)}
                  className="inline-flex items-center gap-1.5 text-sm text-[#22438E] hover:bg-[#E1F0FF] px-3 py-1.5 rounded-md font-normal"
                  data-testid="preview-download-btn"
                >
                  <Download className="w-4 h-4" />
                  Download
                </button>
              )}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {previewMat?.material_type === 'video' && previewMat?.video_url
                ? previewMat.video_url
                : `${previewMat?.file_name || ''} · Week ${previewMat?.week_number || ''}`}
            </DialogDescription>
          </DialogHeader>
          <div className="px-6 pb-6 pt-2">
            {previewMat && (() => {
              const ext = (previewMat.file_name || '').toLowerCase().split('.').pop();
              const token = localStorage.getItem('thinkific_session_token');
              // Video preview
              if (previewMat.material_type === 'video') {
                const url = previewMat.video_url || '';
                // YouTube
                const ytMatch = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{6,})/);
                if (ytMatch) {
                  return (
                    <iframe
                      title="Video preview"
                      src={`https://www.youtube.com/embed/${ytMatch[1]}`}
                      className="w-full h-[75vh] rounded-md border border-[#B8D4E8]"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      data-testid="library-preview-youtube"
                    />
                  );
                }
                // Vimeo
                const vmMatch = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
                if (vmMatch) {
                  return (
                    <iframe
                      title="Video preview"
                      src={`https://player.vimeo.com/video/${vmMatch[1]}`}
                      className="w-full h-[75vh] rounded-md border border-[#B8D4E8]"
                      allow="autoplay; fullscreen; picture-in-picture"
                      allowFullScreen
                      data-testid="library-preview-vimeo"
                    />
                  );
                }
                // Other external URL — fallback to plain link
                if (url) {
                  return (
                    <div className="p-8 text-center border border-[#B8D4E8] rounded-md">
                      <a href={url} target="_blank" rel="noreferrer" className="text-[#22438E] underline break-all">
                        {url}
                      </a>
                    </div>
                  );
                }
                // Uploaded video file — HTML5 player streams from the download endpoint (inline)
                const src = `${API_URL}/api/materials/${previewMat.material_id}/download?inline=1&token=${encodeURIComponent(token || '')}`;
                return (
                  <video
                    src={src}
                    controls
                    className="w-full h-[75vh] rounded-md border border-[#B8D4E8] bg-black"
                    data-testid="library-preview-video"
                  />
                );
              }
              if (ext === 'pdf') {
                const src = `${API_URL}/api/materials/${previewMat.material_id}/download?inline=1&token=${encodeURIComponent(token || '')}`;
                return (
                  <iframe
                    title="Material preview"
                    src={src}
                    className="w-full h-[75vh] rounded-md border border-[#B8D4E8]"
                    data-testid="library-preview-pdf"
                  />
                );
              }
              return (
                <pre
                  className="whitespace-pre-wrap text-sm text-[#1A1A1A] font-sans leading-relaxed max-h-[75vh] overflow-auto border border-[#B8D4E8] rounded-md p-4 bg-[#FAFAFA]"
                  data-testid="library-preview-docx"
                >
                  {previewText || 'No extractable text in this file.'}
                </pre>
              );
            })()}
          </div>
        </DialogContent>
      </Dialog>

      <EditFeedbackTemplateDialog
        open={!!editingRubricMaterial}
        onOpenChange={(open) => !open && setEditingRubricMaterial(null)}
        material={editingRubricMaterial}
        onSaved={() => { setEditingRubricMaterial(null); fetchData(); }}
      />
    </div>
  );
}

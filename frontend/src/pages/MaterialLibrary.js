import React, { useState, useEffect } from 'react';
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
  Plus, Link2, Unlink, File, CheckCircle
} from 'lucide-react';
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
    title: '', description: '', week_number: 1, material_type: 'workbook', file: null
  });

  useEffect(() => {
    if (!authLoading && isInstructor) {
      fetchData();
    }
  }, [authLoading, isInstructor]);

  const fetchData = async () => {
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
  };

  const handleUpload = async () => {
    if (!form.title.trim() || !form.file) {
      toast.error('Please provide a title and file');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', form.file);
      // Backend expects non-file fields as query parameters
      const params = new URLSearchParams({
        title: form.title,
        description: form.description || '',
        week_number: form.week_number,
        material_type: form.material_type
      });
      await axios.post(`${API_URL}/api/library/materials?${params.toString()}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      toast.success('Material added to library!');
      setShowUpload(false);
      setForm({ title: '', description: '', week_number: 1, material_type: 'workbook', file: null });
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
    return <File className="w-5 h-5 text-[#22438E]" />;
  };

  const typeBg = (type) => {
    if (type === 'workbook') return 'bg-[#E1F0FF]';
    if (type === 'case_study') return 'bg-[#7CBAE6]';
    return 'bg-[#E1F0FF]';
  };

  const typeLabel = (type) => {
    if (type === 'workbook') return 'Workbook';
    if (type === 'case_study') return 'Case Study';
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
            {materials.map((mat) => (
              <Card key={mat.material_id} className="bg-white border-[#B8D4E8]" data-testid={`library-material-${mat.material_id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start gap-4">
                    <div className={`w-12 h-12 ${typeBg(mat.material_type)} rounded-lg flex items-center justify-center flex-shrink-0`}>
                      {typeIcon(mat.material_type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between mb-1">
                        <div>
                          <h3 className="font-medium text-[#000000]">{mat.title}</h3>
                          <p className="text-xs text-[#666666]">
                            Week {mat.week_number} · {typeLabel(mat.material_type)} · {mat.file_name}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0 ml-4">
                          <Button 
                            variant="ghost" size="icon"
                            onClick={() => downloadFile(`${API_URL}/api/materials/${mat.material_id}/download`, mat.file_name)}
                            data-testid={`download-lib-${mat.material_id}`}
                          >
                            <Download className="w-4 h-4 text-[#333333]" />
                          </Button>
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
                            <span key={c.cohort_id} className="inline-flex items-center gap-1 text-xs bg-[#D1FAE5] text-[#065F46] px-2 py-1 rounded-full">
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
                <Select value={String(form.week_number)} onValueChange={(v) => setForm({...form, week_number: parseInt(v)})}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Array.from({length: 12}, (_, i) => (
                      <SelectItem key={i+1} value={String(i+1)}>Week {i+1}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Type</Label>
                <Select value={form.material_type} onValueChange={(v) => setForm({...form, material_type: v})}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="workbook">Workbook</SelectItem>
                    <SelectItem value="case_study">Case Study</SelectItem>
                    <SelectItem value="homework">Homework</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
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
                      isAssigned ? 'border-[#065F46] bg-[#D1FAE5]' : 'border-[#B8D4E8] hover:bg-[#E1F0FF]'
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
                      <span className="text-xs bg-[#065F46] text-white px-2 py-0.5 rounded-full">Assigned</span>
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
    </div>
  );
}

import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Sparkles, Pencil, Trash2, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from '../components/ui/dialog';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const EMPTY = { name: '', content: '', description: '' };

export default function RubricLibrary() {
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [rubrics, setRubrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null); // null = create, else rubric object
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!authLoading && !isInstructor) navigate('/dashboard');
  }, [authLoading, isInstructor, navigate]);

  const fetchRubrics = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/rubrics`);
      setRubrics(res.data || []);
    } catch (err) {
      toast.error('Failed to load rubric library');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isInstructor) fetchRubrics();
  }, [authLoading, isInstructor, fetchRubrics]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY);
    setDialogOpen(true);
  };

  const openEdit = (r) => {
    setEditing(r);
    setForm({ name: r.name || '', content: r.content || '', description: r.description || '' });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    const name = form.name.trim();
    const content = form.content.trim();
    if (!name) return toast.error('Name is required');
    if (!content) return toast.error('Rubric content is required');
    setSaving(true);
    try {
      if (editing) {
        const res = await axios.put(`${API_URL}/api/rubrics/${editing.rubric_id}`, {
          name, content, description: form.description.trim(),
        });
        setRubrics((prev) => prev.map((r) => (r.rubric_id === editing.rubric_id ? res.data : r)));
        toast.success('Rubric updated');
      } else {
        const res = await axios.post(`${API_URL}/api/rubrics`, {
          name, content, description: form.description.trim(),
        });
        setRubrics((prev) => [res.data, ...prev]);
        toast.success('Rubric created');
      }
      setDialogOpen(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save rubric');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (r) => {
    if (!window.confirm(`Delete rubric "${r.name}"? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API_URL}/api/rubrics/${r.rubric_id}`);
      setRubrics((prev) => prev.filter((x) => x.rubric_id !== r.rubric_id));
      toast.success('Rubric deleted');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to delete rubric');
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="rubric-library-page">
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/dashboard" className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors" data-testid="back-to-dashboard-btn">
              <ArrowLeft className="w-5 h-5 text-[#333333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000000] flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-[#7C3AED]" />
                Rubric Library
              </h1>
              <p className="text-sm text-[#666666]">Reusable AI feedback instructions for homework assignments</p>
            </div>
          </div>
          <Button onClick={openCreate} className="bg-[#22438E] hover:bg-[#1A3A7A] rounded-full" data-testid="new-rubric-btn">
            <Plus className="w-4 h-4 mr-1.5" /> New Rubric
          </Button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {rubrics.length === 0 ? (
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <Sparkles className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[#000000] mb-2">Your Rubric Library is empty</h3>
              <p className="text-[#333333] mb-6 max-w-md mx-auto">
                Save a rubric here to quickly apply the same AI grading rubric to any homework assignment — no more retyping.
              </p>
              <Button onClick={openCreate} className="bg-[#22438E] hover:bg-[#1A3A7A] rounded-full" data-testid="empty-create-rubric-btn">
                <Plus className="w-4 h-4 mr-1.5" /> Create your first rubric
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {rubrics.map((r) => (
              <Card key={r.rubric_id} className="bg-white border-[#B8D4E8]" data-testid={`rubric-card-${r.rubric_id}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <CardTitle className="text-base font-medium truncate">{r.name}</CardTitle>
                      {r.description && (
                        <CardDescription className="text-sm mt-1 line-clamp-2">{r.description}</CardDescription>
                      )}
                    </div>
                    {r.can_edit && (
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <Button
                          variant="ghost" size="icon"
                          onClick={() => openEdit(r)}
                          title="Edit rubric"
                          data-testid={`edit-rubric-${r.rubric_id}`}
                        >
                          <Pencil className="w-4 h-4 text-[#22438E]" />
                        </Button>
                        <Button
                          variant="ghost" size="icon"
                          onClick={() => handleDelete(r)}
                          title="Delete rubric"
                          data-testid={`delete-rubric-${r.rubric_id}`}
                        >
                          <Trash2 className="w-4 h-4 text-red-600" />
                        </Button>
                      </div>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="text-sm text-[#374151] whitespace-pre-wrap line-clamp-5 bg-[#F9FAFB] border border-[#E5E7EB] rounded-lg p-3 mb-3">
                    {r.content}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-[#666666]">
                    <User className="w-3 h-3" />
                    <span>{r.created_by_name || 'Unknown'}</span>
                    {r.created_by === user?.user_id && (
                      <span className="ml-1 px-1.5 py-0.5 bg-[#E1F0FF] text-[#22438E] rounded text-[10px] uppercase tracking-wide">You</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl" data-testid="rubric-form-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Rubric' : 'New Rubric'}</DialogTitle>
            <DialogDescription>
              Rubrics are shared across all instructors. Only you or a super admin can edit or delete rubrics you create.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor="rubric-name">Name</Label>
              <Input
                id="rubric-name"
                data-testid="rubric-name-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., Kawasaki Model Comparison"
                className="mt-1"
                autoFocus
              />
            </div>
            <div>
              <Label htmlFor="rubric-description">Description (optional)</Label>
              <Input
                id="rubric-description"
                data-testid="rubric-description-input"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="When would you use this rubric?"
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="rubric-content">AI Feedback Instructions</Label>
              <Textarea
                id="rubric-content"
                data-testid="rubric-content-input"
                value={form.content}
                onChange={(e) => setForm({ ...form, content: e.target.value })}
                placeholder="Grade specifically on how the submission compares to the Kawasaki Model on slide 4. Give feedback on: (1) accuracy of the comparison, (2) depth of analysis, (3) actionable next steps."
                rows={7}
                className="mt-1 font-mono text-sm"
              />
              <p className="text-xs text-[#666666] mt-1">
                These instructions replace the default 3-well / 3-improve rubric on any homework this rubric is applied to.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} data-testid="rubric-form-cancel-btn">Cancel</Button>
            <Button onClick={handleSave} disabled={saving} data-testid="rubric-form-save-btn">
              {saving ? 'Saving…' : editing ? 'Save Changes' : 'Create Rubric'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

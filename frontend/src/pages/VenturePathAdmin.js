import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Save, RotateCcw, Trophy } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { useAuth } from '../context/AuthContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Super-admin-only editor for the 14 Venture Path module labels. Persists to
 * `platform_settings._id=venture_path_modules.overrides` via the admin API.
 * Any field left blank falls back to the built-in default for that module,
 * so admins only need to change what they want customised.
 */
export default function VenturePathAdmin() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [modules, setModules] = useState([]);
  const [defaults, setDefaults] = useState([]);
  const [allowedIcons, setAllowedIcons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user && user.role !== 'super_admin') navigate('/dashboard');
  }, [user, navigate]);

  const load = useCallback(async () => {
    // Guard: don't hit the admin endpoint for non-super-admins — the role
    // useEffect above redirects them, but this stops the "Super admin only"
    // toast from flashing before the redirect fires.
    if (user && user.role !== 'super_admin') return;
    try {
      const res = await axios.get(`${API_URL}/api/admin/venture-path-modules`);
      setModules(res.data.modules || []);
      setDefaults(res.data.defaults || []);
      setAllowedIcons(res.data.allowed_icons || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not load modules');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const patchModule = (moduleNum, field, value) => {
    setModules((prev) => prev.map((m) => (m.module === moduleNum ? { ...m, [field]: value } : m)));
  };

  const resetToDefault = (moduleNum) => {
    const def = defaults.find((d) => d.module === moduleNum);
    if (!def) return;
    setModules((prev) => prev.map((m) => (m.module === moduleNum ? { ...def } : m)));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Send the whole list; backend keeps only fields that differ from defaults.
      const res = await axios.put(`${API_URL}/api/admin/venture-path-modules`, { modules });
      setModules(res.data.modules || []);
      toast.success(`Saved · ${res.data.saved_count || 0} module${res.data.saved_count === 1 ? '' : 's'} customised`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="max-w-5xl mx-auto px-6 py-8"><p className="text-[#666]">Loading…</p></div>;
  }

  return (
    <div className="max-w-5xl mx-auto px-6 md:px-12 py-8" data-testid="venture-path-admin-page">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/admin" className="text-[#22438E] inline-flex items-center gap-1 text-sm hover:underline" data-testid="vpa-back">
          <ArrowLeft className="w-4 h-4" /> Back to Admin
        </Link>
      </div>

      <div className="mb-6 flex items-start gap-3">
        <div className="w-12 h-12 rounded-full bg-[#E1F0FF] flex items-center justify-center flex-shrink-0">
          <Trophy className="w-6 h-6 text-[#22438E]" />
        </div>
        <div>
          <h1 className="text-3xl font-normal text-[#000] mb-1">Venture Path Modules</h1>
          <p className="text-sm text-[#666] max-w-2xl">
            Rename the 14 badge names, tune the taglines students see, or pick a different icon per module.
            Leave any field blank to keep the built-in default.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {modules.map((m) => {
          const def = defaults.find((d) => d.module === m.module) || {};
          const isCustom = m.name !== def.name || m.tagline !== def.tagline || m.icon !== def.icon;
          return (
            <Card key={m.module} className={`bg-white ${isCustom ? 'border-[#22438E]' : 'border-[#E5E7EB]'}`}>
              <CardContent className="p-4 grid gap-3 md:grid-cols-[80px_1fr_1fr_160px_120px] md:items-end">
                <div className="text-xs uppercase tracking-wide text-[#666]">
                  Module<br /><span className="text-2xl font-medium text-[#22438E]">{m.module}</span>
                </div>
                <div>
                  <Label htmlFor={`vpa-name-${m.module}`} className="text-xs text-[#666]">Name</Label>
                  <Input
                    id={`vpa-name-${m.module}`}
                    data-testid={`vpa-name-${m.module}`}
                    value={m.name || ''}
                    onChange={(e) => patchModule(m.module, 'name', e.target.value)}
                    placeholder={def.name}
                    maxLength={80}
                  />
                </div>
                <div>
                  <Label htmlFor={`vpa-tagline-${m.module}`} className="text-xs text-[#666]">Tagline</Label>
                  <Textarea
                    id={`vpa-tagline-${m.module}`}
                    data-testid={`vpa-tagline-${m.module}`}
                    value={m.tagline || ''}
                    onChange={(e) => patchModule(m.module, 'tagline', e.target.value)}
                    placeholder={def.tagline}
                    rows={2}
                    maxLength={160}
                  />
                </div>
                <div>
                  <Label htmlFor={`vpa-icon-${m.module}`} className="text-xs text-[#666]">Icon</Label>
                  <select
                    id={`vpa-icon-${m.module}`}
                    data-testid={`vpa-icon-${m.module}`}
                    value={m.icon || ''}
                    onChange={(e) => patchModule(m.module, 'icon', e.target.value)}
                    className="w-full h-9 rounded-md border border-[#E5E7EB] px-2 text-sm"
                  >
                    {allowedIcons.map((ic) => (
                      <option key={ic} value={ic}>{ic}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!isCustom}
                    onClick={() => resetToDefault(m.module)}
                    className="text-xs text-[#666] hover:text-[#22438E] w-full"
                    data-testid={`vpa-reset-${m.module}`}
                  >
                    <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="mt-8 flex items-center justify-end gap-2">
        <Button
          onClick={handleSave}
          disabled={saving}
          className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
          data-testid="vpa-save-btn"
        >
          <Save className="w-4 h-4 mr-2" />
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </div>
  );
}

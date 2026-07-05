import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Save, RefreshCw, Palette } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { useAuth } from '../context/AuthContext';
import { useBranding } from '../context/BrandingContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function BrandingSettings() {
  const { user } = useAuth();
  const { branding, refresh } = useBranding();
  const navigate = useNavigate();
  const [form, setForm] = useState(branding);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user && user.role !== 'super_admin') {
      navigate('/dashboard');
    }
  }, [user, navigate]);

  useEffect(() => {
    setForm(branding);
  }, [branding]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API_URL}/api/settings/branding`, form);
      await refresh();
      toast.success('Branding saved — reloading to apply');
      setTimeout(() => window.location.reload(), 800);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save branding');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setForm(branding);
    toast.success('Reverted to saved values');
  };

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="branding-settings">
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 md:px-12 h-16 flex items-center gap-4">
          <Link to="/dashboard" className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors">
            <ArrowLeft className="w-5 h-5 text-[#333333]" />
          </Link>
          <div className="flex items-center gap-3">
            <Palette className="w-5 h-5 text-[#22438E]" />
            <div>
              <h1 className="text-lg font-medium text-[#000000]">Platform Branding</h1>
              <p className="text-xs text-[#666666]">White-label configuration — applies platform-wide</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 md:px-12 py-8 space-y-5">
        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-base font-medium">Identity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="app_name">App Name</Label>
              <Input
                id="app_name"
                data-testid="brand-app-name"
                value={form.app_name || ''}
                onChange={(e) => setForm({ ...form, app_name: e.target.value })}
                placeholder="The Boost Pad"
              />
              <p className="text-xs text-[#666666] mt-1">Shown in the header, browser tab title, and login page.</p>
            </div>
            <div>
              <Label htmlFor="ai_persona_name">AI Persona Name</Label>
              <Input
                id="ai_persona_name"
                data-testid="brand-ai-persona"
                value={form.ai_persona_name || ''}
                onChange={(e) => setForm({ ...form, ai_persona_name: e.target.value })}
                placeholder="Coach Max"
              />
              <p className="text-xs text-[#666666] mt-1">The AI tutor is referred to by this name in chat and emails.</p>
            </div>
            <div>
              <Label htmlFor="tagline">Tagline</Label>
              <Input
                id="tagline"
                data-testid="brand-tagline"
                value={form.tagline || ''}
                onChange={(e) => setForm({ ...form, tagline: e.target.value })}
                placeholder="AI-powered learning coach"
              />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-base font-medium">Visual</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="primary_color">Primary Color</Label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={form.primary_color || '#22438E'}
                  onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
                  className="h-10 w-14 rounded border border-[#B8D4E8]"
                  data-testid="brand-primary-color"
                />
                <Input
                  value={form.primary_color || ''}
                  onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
                  className="max-w-[160px]"
                  placeholder="#22438E"
                />
              </div>
              <p className="text-xs text-[#666666] mt-1">Buttons, links, and accent color. Exposed to CSS as <code>var(--brand-primary)</code>.</p>
            </div>
            <div>
              <Label htmlFor="logo_url">Logo URL</Label>
              <Input
                id="logo_url"
                data-testid="brand-logo-url"
                value={form.logo_url || ''}
                onChange={(e) => setForm({ ...form, logo_url: e.target.value })}
                placeholder="https://cdn.example.com/logo.svg"
              />
            </div>
            <div>
              <Label htmlFor="favicon_url">Favicon URL</Label>
              <Input
                id="favicon_url"
                data-testid="brand-favicon-url"
                value={form.favicon_url || ''}
                onChange={(e) => setForm({ ...form, favicon_url: e.target.value })}
                placeholder="https://cdn.example.com/favicon.ico"
              />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-base font-medium">Email & AI</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="email_sender_name">Email Sender Name</Label>
              <Input
                id="email_sender_name"
                data-testid="brand-email-sender"
                value={form.email_sender_name || ''}
                onChange={(e) => setForm({ ...form, email_sender_name: e.target.value })}
                placeholder="The Boost Pad"
              />
              <p className="text-xs text-[#666666] mt-1">Displayed as the &quot;From&quot; name on outgoing emails.</p>
            </div>
            <div>
              <Label htmlFor="ai_system_prompt">AI System Prompt (optional override)</Label>
              <Textarea
                id="ai_system_prompt"
                data-testid="brand-ai-prompt"
                rows={4}
                value={form.ai_system_prompt || ''}
                onChange={(e) => setForm({ ...form, ai_system_prompt: e.target.value })}
                placeholder="You are {persona}, a friendly AI tutor..."
              />
              <p className="text-xs text-[#666666] mt-1">
                Use <code>{'{persona}'}</code> as a placeholder. Leave blank to use the built-in default.
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-3">
          <Button
            variant="outline"
            onClick={handleReset}
            data-testid="brand-reset-btn"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Reset
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
            data-testid="brand-save-btn"
          >
            <Save className="w-4 h-4 mr-2" />
            {saving ? 'Saving…' : 'Save Branding'}
          </Button>
        </div>
      </main>
    </div>
  );
}

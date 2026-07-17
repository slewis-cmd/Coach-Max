import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Link, Navigate } from 'react-router-dom';
import { ArrowLeft, LifeBuoy, CheckCircle2, Circle, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Textarea } from '../components/ui/textarea';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AdminSupportTicketsPage() {
  const { user, loading: authLoading } = useAuth();
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('open'); // 'open' | 'resolved' | 'all'
  const [expanded, setExpanded] = useState(null); // ticket_id

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    try {
      const qs = filter === 'all' ? '' : `?status=${filter}`;
      const res = await axios.get(`${API_URL}/api/admin/support/tickets${qs}`);
      setTickets(res.data || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load tickets');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);

  // Guard: only super_admin can access this page
  if (!authLoading && user && user.role !== 'super_admin') {
    return <Navigate to="/" replace />;
  }
  if (authLoading || !user) {
    return null;
  }

  const updateTicket = async (ticketId, patch) => {
    try {
      const res = await axios.patch(`${API_URL}/api/admin/support/tickets/${ticketId}`, patch);
      setTickets((prev) => prev.map((t) => (t.ticket_id === ticketId ? res.data : t)));
      toast.success('Updated');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to update');
    }
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      <header className="border-b border-[#E5E7EB] bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link to="/" className="text-[#6B7280] hover:text-[#22438E]"><ArrowLeft className="w-5 h-5" /></Link>
          <LifeBuoy className="w-6 h-6 text-[#22438E]" />
          <h1 className="text-xl font-medium text-[#1F2937]">Support Tickets</h1>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex items-center gap-2 mb-4" data-testid="ticket-filter-tabs">
          {['open', 'resolved', 'all'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 text-sm rounded-full border ${
                filter === s
                  ? 'bg-[#22438E] text-white border-[#22438E]'
                  : 'bg-white text-[#374151] border-[#D1D5DB] hover:bg-[#F3F4F6]'
              }`}
              data-testid={`ticket-filter-${s}`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="text-sm text-[#6B7280]">Loading…</p>
        ) : tickets.length === 0 ? (
          <div className="bg-white border border-[#E5E7EB] rounded-lg p-8 text-center text-[#6B7280]">
            No {filter === 'all' ? '' : filter} tickets yet.
          </div>
        ) : (
          <div className="space-y-3">
            {tickets.map((t) => (
              <div key={t.ticket_id} className="bg-white border border-[#E5E7EB] rounded-lg p-4" data-testid={`ticket-${t.ticket_id}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-xs text-[#6B7280] mb-1">
                      {t.status === 'resolved' ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#10B981]" />
                      ) : (
                        <Circle className="w-3.5 h-3.5 text-[#F59E0B]" />
                      )}
                      <span className="uppercase tracking-wide">{t.status}</span>
                      <span>·</span>
                      <span>{new Date(t.created_at).toLocaleString()}</span>
                    </div>
                    <h3 className="font-medium text-[#1F2937] truncate">{t.subject}</h3>
                    <p className="text-xs text-[#6B7280] mt-1 flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {t.user_name} · {t.user_email} · <span className="uppercase text-[10px]">{t.user_role}</span>
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setExpanded(expanded === t.ticket_id ? null : t.ticket_id)}
                      className="h-7 text-xs"
                      data-testid={`ticket-toggle-${t.ticket_id}`}
                    >
                      {expanded === t.ticket_id ? 'Hide' : 'View'}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => updateTicket(t.ticket_id, { status: t.status === 'open' ? 'resolved' : 'open' })}
                      className={t.status === 'open' ? 'bg-[#10B981] hover:bg-[#059669] text-white h-7 text-xs' : 'bg-[#6B7280] hover:bg-[#4B5563] text-white h-7 text-xs'}
                      data-testid={`ticket-mark-${t.ticket_id}`}
                    >
                      {t.status === 'open' ? 'Resolve' : 'Reopen'}
                    </Button>
                  </div>
                </div>
                {expanded === t.ticket_id && (
                  <div className="mt-4 pt-4 border-t border-[#E5E7EB] space-y-2">
                    {(t.conversation || []).map((c, i) => (
                      <div
                        key={i}
                        className={`text-sm rounded-lg p-3 ${
                          c.role === 'user' ? 'bg-[#EFF6FF] text-[#1E3A8A]' : 'bg-[#F3F4F6] text-[#374151]'
                        }`}
                      >
                        <div className="text-[10px] uppercase font-medium mb-1 opacity-70">
                          {c.role === 'user' ? t.user_name : 'Support bot'}
                        </div>
                        {c.text.split('\n').map((l, j) => <div key={j}>{l || '\u00A0'}</div>)}
                      </div>
                    ))}
                    <div className="pt-2">
                      <label className="text-xs text-[#6B7280] block mb-1">Admin notes</label>
                      <Textarea
                        defaultValue={t.admin_notes || ''}
                        rows={2}
                        onBlur={(e) => {
                          if (e.target.value !== (t.admin_notes || '')) {
                            updateTicket(t.ticket_id, { admin_notes: e.target.value });
                          }
                        }}
                        placeholder="Internal notes (auto-saves on blur)"
                        data-testid={`ticket-notes-${t.ticket_id}`}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

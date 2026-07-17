import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { HelpCircle, Send, X, AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Floating support widget — visible on every authenticated page. Opens a chat panel where
 * users can ask the AI support bot for platform-usage help. Includes an "Escalate to admin"
 * button that creates a persistent ticket + emails the super admin.
 */
export default function SupportWidget() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]); // {role: 'user'|'assistant', text, ts}
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [escalated, setEscalated] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, open]);

  // Only show for authenticated users
  if (!user) return null;

  const greeting = messages.length === 0
    ? `Hi ${(user.name || 'there').split(' ')[0]}! I'm the platform support bot. Ask me how to submit homework, use Coach Max, find your feedback, or anything about navigating The Boost Pad. If I can't help, I can escalate to an administrator.`
    : null;

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    const userTurn = { role: 'user', text, ts: new Date().toISOString() };
    const nextMessages = [...messages, userTurn];
    setMessages(nextMessages);
    setInput('');
    setSending(true);
    try {
      const res = await axios.post(`${API_URL}/api/support/chat`, {
        message: text,
        history: nextMessages.slice(-8).map((m) => ({ role: m.role, text: m.text })),
      });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: res.data?.response || '(empty response)', ts: new Date().toISOString() },
      ]);
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Support bot is temporarily unavailable.';
      setMessages((prev) => [...prev, { role: 'assistant', text: detail, ts: new Date().toISOString() }]);
    } finally {
      setSending(false);
    }
  };

  const handleEscalate = async () => {
    if (escalating || escalated) return;
    if (messages.length === 0) {
      toast.error('Please describe your issue first — even a single message helps the admin understand.');
      return;
    }
    setEscalating(true);
    try {
      const res = await axios.post(`${API_URL}/api/support/escalate`, {
        conversation: messages.map((m) => ({ role: m.role, text: m.text, ts: m.ts })),
      });
      setEscalated(true);
      toast.success(res.data?.message || 'Escalated to administrator.');
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `✓ Ticket #${res.data?.ticket_id} sent to your administrator. They'll follow up by email.`,
          ts: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to escalate. Please try again.');
    } finally {
      setEscalating(false);
    }
  };

  const handleReset = () => {
    setMessages([]);
    setEscalated(false);
    setInput('');
  };

  return (
    <>
      {/* Floating trigger */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-[#22438E] text-white shadow-lg hover:bg-[#1A3A7A] transition-colors flex items-center justify-center"
          data-testid="support-widget-trigger"
          title="Get platform help"
        >
          <HelpCircle className="w-6 h-6" />
        </button>
      )}

      {/* Panel */}
      {open && (
        <div
          className="fixed bottom-6 right-6 z-50 w-[min(400px,calc(100vw-32px))] h-[min(600px,calc(100vh-100px))] rounded-2xl shadow-2xl bg-white border border-[#D1D5DB] flex flex-col overflow-hidden"
          data-testid="support-widget-panel"
        >
          <div className="flex items-center justify-between px-4 py-3 bg-[#22438E] text-white flex-shrink-0">
            <div className="flex items-center gap-2">
              <HelpCircle className="w-5 h-5" />
              <span className="font-medium">Platform Support</span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="hover:opacity-80"
              data-testid="support-widget-close"
              aria-label="Close support"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-4 py-3 space-y-3 bg-[#F9FAFB]"
            data-testid="support-widget-messages"
          >
            {greeting && (
              <div className="text-sm text-[#374151] bg-white border border-[#E5E7EB] rounded-lg p-3">
                {greeting}
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`text-sm rounded-lg p-3 ${
                  m.role === 'user'
                    ? 'bg-[#22438E] text-white ml-8'
                    : 'bg-white border border-[#E5E7EB] text-[#1F2937] mr-8'
                }`}
                data-testid={`support-message-${m.role}-${i}`}
              >
                {m.text.split('\n').map((line, j) => (
                  <div key={j}>{line || '\u00A0'}</div>
                ))}
              </div>
            ))}
            {sending && (
              <div className="text-sm rounded-lg p-3 bg-white border border-[#E5E7EB] mr-8 flex items-center gap-2 text-[#6B7280]">
                <Loader2 className="w-4 h-4 animate-spin" /> Support bot is thinking…
              </div>
            )}
          </div>

          <div className="border-t border-[#E5E7EB] p-3 space-y-2 flex-shrink-0 bg-white">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask about the platform… (Enter to send, Shift+Enter for newline)"
              rows={2}
              className="text-sm resize-none"
              disabled={sending}
              data-testid="support-widget-input"
            />
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleEscalate}
                  disabled={escalating || escalated || messages.length === 0}
                  className="text-xs h-8 border-[#EF4444] text-[#EF4444] hover:bg-[#FEF2F2]"
                  data-testid="support-widget-escalate"
                  title="Send this conversation to an administrator"
                >
                  <AlertCircle className="w-3.5 h-3.5 mr-1" />
                  {escalated ? 'Escalated' : escalating ? 'Sending…' : 'Escalate'}
                </Button>
                {messages.length > 0 && !escalated && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleReset}
                    className="text-xs h-8 text-[#6B7280]"
                    data-testid="support-widget-reset"
                  >
                    Reset
                  </Button>
                )}
              </div>
              <Button
                size="sm"
                onClick={handleSend}
                disabled={sending || !input.trim()}
                className="bg-[#22438E] hover:bg-[#1A3A7A] text-white h-8"
                data-testid="support-widget-send"
              >
                <Send className="w-3.5 h-3.5 mr-1" />
                Send
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

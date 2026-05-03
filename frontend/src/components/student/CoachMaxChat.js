import React, { useState, useEffect, useRef } from 'react';
import { Button } from '../ui/button';
import { MessageCircle, Send, X } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function CoachMaxChat({ submissionId, weekNumber, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/chat/history/${submissionId}`);
        const history = res.data.map(c => ([
          { role: 'student', text: c.message },
          { role: 'coach', text: c.response }
        ])).flat();
        setMessages(history);
      } catch (_e) {
        // First load — no chat history yet
      } finally {
        setLoadingHistory(false);
      }
    };
    loadHistory();
  }, [submissionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'student', text: userMsg }]);
    setSending(true);

    try {
      const res = await axios.post(`${API_URL}/api/chat/ask-tutor`, {
        message: userMsg,
        submission_id: submissionId
      });
      setMessages(prev => [...prev, { role: 'coach', text: res.data.response }]);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Coach Max is unavailable right now');
      setMessages(prev => [...prev, { role: 'coach', text: "Sorry, I'm having trouble right now. Please try again in a moment." }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center" data-testid="coach-max-chat">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white w-full md:w-[480px] md:max-h-[600px] h-[85vh] md:h-auto md:rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-fade-in">
        {/* Header */}
        <div className="bg-[#000000] text-white px-5 py-4 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-[#22438E] rounded-full flex items-center justify-center">
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-medium text-sm">Coach Max</h3>
              <p className="text-xs text-white/60">Week {weekNumber} feedback discussion</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="text-white/70 hover:text-white hover:bg-white/10">
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#FAFAF8]">
          {messages.length === 0 && !loadingHistory && (
            <div className="text-center py-8">
              <div className="w-14 h-14 bg-[#E1F0FF] rounded-full flex items-center justify-center mx-auto mb-3">
                <MessageCircle className="w-7 h-7 text-[#22438E]" />
              </div>
              <h4 className="font-medium text-[#000000] mb-1">Hi! I'm Coach Max</h4>
              <p className="text-sm text-[#333333] max-w-xs mx-auto">
                Ask me anything about your Week {weekNumber} feedback. I'm here to help you grow!
              </p>
            </div>
          )}
          {loadingHistory && (
            <div className="flex justify-center py-8">
              <div className="w-6 h-6 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={`${msg.role}-${i}-${msg.text?.slice(0,20)}`} className={`flex ${msg.role === 'student' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'student'
                  ? 'bg-[#000000] text-white rounded-br-md'
                  : 'bg-white border border-[#B8D4E8] text-[#000000] rounded-bl-md shadow-sm'
              }`}>
                {msg.role === 'coach' && (
                  <p className="text-xs font-medium text-[#22438E] mb-1">Coach Max</p>
                )}
                <div className="whitespace-pre-wrap">{msg.text}</div>
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-white border border-[#B8D4E8] rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                <p className="text-xs font-medium text-[#22438E] mb-1">Coach Max</p>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 bg-[#22438E] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-[#22438E] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-[#22438E] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-[#B8D4E8] p-3 flex items-center gap-2 bg-white flex-shrink-0">
          <input type="text" value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask Coach Max a question..."
            className="flex-1 px-4 py-2.5 bg-[#D0E6F9] rounded-full text-sm outline-none focus:ring-2 focus:ring-[#22438E]/20"
            disabled={sending} data-testid="coach-max-input" />
          <Button size="icon" onClick={handleSend} disabled={sending || !input.trim()}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-full w-10 h-10 flex-shrink-0"
            data-testid="coach-max-send">
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

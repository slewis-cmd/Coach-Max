import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { MessageCircle, ArrowLeft, FileText, Send, Globe, Volume2, Trophy } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { stripProgressScoreLine } from '../lib/progressScore';
import { ProgressScoreBadge } from '../components/submission/ProgressScoreBadge';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function CoachMaxPage() {
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [submission, setSubmission] = useState(null);
  const [loading, setLoading] = useState(true);

  // Chat state
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [chatLang, setChatLang] = useState(user?.language_preference || 'en');
  const [playingAudio, setPlayingAudio] = useState(null); // index of message currently playing
  const messagesEndRef = React.useRef(null);
  const audioPlayerRef = React.useRef(null);

  const handlePlayAudio = async (text, index) => {
    if (playingAudio === index) {
      if (audioPlayerRef.current) audioPlayerRef.current.pause();
      setPlayingAudio(null);
      return;
    }
    setPlayingAudio(index);
    try {
      const res = await axios.post(`${API_URL}/api/chat/audio`, { text });
      const url = `${API_URL}${res.data.audio_url}`;
      if (audioPlayerRef.current) audioPlayerRef.current.pause();
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      audio.onended = () => setPlayingAudio(null);
      audio.play();
    } catch (err) {
      console.warn('TTS audio generation failed:', err?.message || err);
      toast.error('Could not generate audio');
      setPlayingAudio(null);
    }
  };

  const fetchSubmission = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/submissions/${submissionId}`);
      setSubmission(res.data);
    } catch (err) {
      toast.error('Could not load submission');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [submissionId, navigate]);

  const loadChatHistory = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/chat/history/${submissionId}`);
      const history = res.data.flatMap(c => [
        { role: 'student', text: c.message },
        { role: 'coach', text: c.response }
      ]);
      setMessages(history);
    } catch (err) {
      // 404 = no history yet (first load); anything else worth logging
      if (err?.response?.status !== 404) {
        console.warn('Failed to load chat history:', err?.message || err);
      }
    } finally {
      setLoadingHistory(false);
    }
  }, [submissionId]);

  useEffect(() => {
    if (!authLoading && user) {
      fetchSubmission();
      loadChatHistory();
    }
  }, [authLoading, user, fetchSubmission, loadChatHistory]);

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
        submission_id: submissionId,
        language: chatLang
      });
      setMessages(prev => [...prev, { role: 'coach', text: res.data.response }]);
    } catch (error) {
      const status = error?.response?.status;
      const serverDetail = error?.response?.data?.detail;
      // Auth failures get a distinct message so users know to re-login (a common cause
      // of the previously-catch-all "having trouble" message).
      const isAuthError = status === 401 || status === 403;
      const bubbleText = isAuthError
        ? "Your session has expired. Please sign out and sign back in, then try again."
        : (serverDetail || "Sorry, I'm having trouble right now. Please try again.");
      toast.error(isAuthError ? 'Session expired — please sign in again' : (serverDetail || 'Coach Max is unavailable right now'));
      setMessages(prev => [...prev, { role: 'coach', text: bubbleText }]);
    } finally {
      setSending(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!submission) return null;

  const feedback = stripProgressScoreLine(submission.instructor_feedback || submission.ai_feedback || '');
  const readinessScore = submission.readiness_score;
  const weekNum = submission.material?.week_number || '?';
  const materialTitle = submission.material?.title || 'Homework';

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex flex-col" data-testid="coach-max-page">
      {/* Header */}
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 md:px-8 h-14 flex items-center gap-3">
          <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors">
            <ArrowLeft className="w-5 h-5 text-[#333333]" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#22438E] rounded-full flex items-center justify-center">
              <MessageCircle className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-base font-medium text-[#000000] leading-tight">Coach Max</h1>
              <p className="text-xs text-[#666666]">Week {weekNum} — {materialTitle}</p>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Link
              to="/venture-path"
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#E1F0FF] hover:bg-[#B8D4E8] text-[#22438E] text-xs font-medium transition-colors"
              data-testid="coach-max-venture-path-link"
            >
              <Trophy className="w-3.5 h-3.5" />
              Venture Path
            </Link>
            <div className="flex items-center gap-1.5" data-testid="chat-language-toggle">
              <Globe className="w-3.5 h-3.5 text-[#666666]" />
              <button
                onClick={() => setChatLang('en')}
                className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${chatLang === 'en' ? 'bg-[#22438E] text-white' : 'text-[#333] hover:bg-[#D0E6F9]'}`}
                data-testid="chat-lang-en"
              >EN</button>
              <button
                onClick={() => setChatLang('es')}
                className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${chatLang === 'es' ? 'bg-[#22438E] text-white' : 'text-[#333] hover:bg-[#D0E6F9]'}`}
                data-testid="chat-lang-es"
              >ES</button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex flex-col max-w-3xl mx-auto w-full">
        {/* Feedback summary (collapsible) */}
        {feedback && (
          <details className="mx-4 md:mx-8 mt-4" data-testid="feedback-summary">
            <summary className="cursor-pointer flex items-center gap-2 text-sm font-medium text-[#22438E] hover:underline">
              <FileText className="w-4 h-4" />
              {chatLang === 'es' ? 'Ver tu retroalimentacion' : 'View your feedback'}
            </summary>
            <Card className="mt-2 bg-[#F0FDF4] border-[#BBF7D0]">
              <CardContent className="p-4 space-y-3">
                {readinessScore ? <ProgressScoreBadge score={readinessScore} /> : null}
                <p className="text-sm text-[#166534] whitespace-pre-wrap leading-relaxed">{feedback}</p>
              </CardContent>
            </Card>
          </details>
        )}

        {/* Chat area */}
        <div className="flex-1 flex flex-col mx-4 md:mx-8 mt-4 mb-4 bg-white rounded-xl border border-[#B8D4E8] shadow-sm overflow-hidden" style={{ minHeight: '400px' }}>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#FAFAF8]">
            {messages.length === 0 && !loadingHistory && (
              <div className="text-center py-10">
                <div className="w-14 h-14 bg-[#E1F0FF] rounded-full flex items-center justify-center mx-auto mb-3">
                  <MessageCircle className="w-7 h-7 text-[#22438E]" />
                </div>
                <h4 className="font-medium text-[#000000] mb-1">{chatLang === 'es' ? 'Hola! Soy Coach Max' : "Hi! I'm Coach Max"}</h4>
                <p className="text-sm text-[#333333] max-w-xs mx-auto">
                  {chatLang === 'es' 
                    ? `Preguntame lo que quieras sobre tu retroalimentacion de la Semana ${weekNum}. Estoy aqui para ayudarte!`
                    : `Ask me anything about your Week ${weekNum} feedback. I'm here to help you grow!`}
                </p>
              </div>
            )}
            {loadingHistory && (
              <div className="flex justify-center py-8">
                <div className="w-6 h-6 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={`${msg.role}-${i}`} className={`flex ${msg.role === 'student' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === 'student'
                    ? 'bg-[#000000] text-white rounded-br-md'
                    : 'bg-white border border-[#B8D4E8] text-[#000000] rounded-bl-md shadow-sm'
                }`}>
                  {msg.role === 'coach' && (
                    <p className="text-xs font-medium text-[#22438E] mb-1">Coach Max</p>
                  )}
                  <div className="whitespace-pre-wrap">{msg.text}</div>
                  {msg.role === 'coach' && (
                    <button
                      onClick={() => handlePlayAudio(msg.text, i)}
                      className="mt-2 inline-flex items-center gap-1 text-xs text-[#22438E] hover:text-[#1A3A7A] transition-colors"
                      data-testid={`play-audio-${i}`}
                    >
                      <Volume2 className={`w-3.5 h-3.5 ${playingAudio === i ? 'animate-pulse' : ''}`} />
                      {playingAudio === i ? (chatLang === 'es' ? 'Reproduciendo...' : 'Playing...') : (chatLang === 'es' ? 'Escuchar' : 'Listen')}
                    </button>
                  )}
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
          <div className="border-t border-[#B8D4E8] p-3 flex items-center gap-2 bg-white">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder={chatLang === 'es' ? "Hazle una pregunta al Coach Max..." : "Ask Coach Max a question..."}
              className="flex-1 px-4 py-2.5 bg-[#D0E6F9] rounded-full text-sm outline-none focus:ring-2 focus:ring-[#22438E]/20"
              disabled={sending}
              data-testid="coach-max-input"
            />
            <Button
              size="icon"
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-full w-10 h-10 flex-shrink-0"
              data-testid="coach-max-send"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

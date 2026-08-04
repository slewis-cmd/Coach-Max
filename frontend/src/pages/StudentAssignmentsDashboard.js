import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  ChevronDown, ChevronRight, Star, CheckCircle2, Circle, Clock, MessageCircle,
  Mic, Presentation, FileText, ListChecks, ArrowRight, LogOut, User, Trophy
} from 'lucide-react';
import { SUBMISSION_TYPE_BY_ID } from '../config/submissionTypes';
import { useBranding } from '../context/BrandingContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const ICONS = { Mic, Presentation, FileText, ListChecks };

const STATUS_META = {
  not_started:       { label: 'Not started', color: 'bg-[#F3F4F6] text-[#666]', icon: Circle },
  submitted:         { label: 'Submitted — awaiting review', color: 'bg-[#DBEAFE] text-[#1E40AF]', icon: Clock },
  under_review:      { label: 'Instructor reviewing', color: 'bg-[#FEF3C7] text-[#92400E]', icon: Clock },
  feedback_provided: { label: 'Feedback ready', color: 'bg-[#D1FAE5] text-[#065F46]', icon: CheckCircle2 },
};

function statusBadge(status) {
  const meta = STATUS_META[status] || STATUS_META.not_started;
  const I = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full ${meta.color}`}>
      <I className="w-3 h-3" />
      {meta.label}
    </span>
  );
}

export default function StudentAssignmentsDashboard() {
  const { user, logout, loading: authLoading } = useAuth();
  const { branding } = useBranding();
  const [cohorts, setCohorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/student/assignments-dashboard`);
        setCohorts(res.data || []);
      } catch (err) {
        toast.error('Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };
    if (!authLoading && user) fetchData();
  }, [authLoading, user]);

  const toggle = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="student-assignments-dashboard">
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#22438E] flex items-center justify-center text-white text-sm font-medium">
              {(branding?.app_name || 'BP')[0]}
            </div>
            <h1 className="text-lg font-medium text-[#000]">{branding?.app_name || 'The Boost Pad'}</h1>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <Link
              to="/venture-path"
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#E1F0FF] hover:bg-[#B8D4E8] text-[#22438E] text-xs font-medium transition-colors"
              data-testid="venture-path-nav-link"
            >
              <Trophy className="w-3.5 h-3.5" />
              Venture Path
            </Link>
            <span className="text-[#333] hidden sm:inline">{user?.name}</span>
            <div className="w-8 h-8 rounded-full bg-[#E1F0FF] flex items-center justify-center">
              <User className="w-4 h-4 text-[#22438E]" />
            </div>
            <Button variant="ghost" size="sm" onClick={logout} data-testid="student-logout-btn">
              <LogOut className="w-4 h-4 mr-1" /> <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 md:px-12 py-8 space-y-8">
        {cohorts.length === 0 && (
          <Card className="bg-white border-[#B8D4E8] border-dashed">
            <CardContent className="p-12 text-center">
              <p className="text-[#333]">You&apos;re not enrolled in any cohort yet. Ask your instructor for an invite code.</p>
            </CardContent>
          </Card>
        )}

        {cohorts.map((cohort) => (
          <section key={cohort.cohort_id} data-testid={`cohort-section-${cohort.cohort_id}`}>
            <div className="flex items-baseline justify-between mb-4">
              <div>
                <h2 className="text-2xl font-medium text-[#000]" data-testid={`cohort-name-${cohort.cohort_id}`}>{cohort.cohort_name}</h2>
                <p className="text-sm text-[#666]">
                  {cohort.current_week
                    ? `Week ${cohort.current_week} of ${cohort.total_weeks}`
                    : (cohort.this_week?.length === 0 && cohort.assignments?.some(a => a.milestones.length) ? 'All caught up!' : `${cohort.total_weeks} weeks`)
                  }
                </p>
              </div>
            </div>

            {/* This Week Panel */}
            {cohort.this_week?.length > 0 && (
              <Card className="bg-gradient-to-br from-[#22438E] to-[#1A3A7A] border-none shadow-md mb-6" data-testid={`this-week-panel-${cohort.cohort_id}`}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-white flex items-center gap-2">
                    <Star className="w-5 h-5" />
                    This Week &mdash; Week {cohort.current_week}
                  </CardTitle>
                  <CardDescription className="text-[#B8D4E8]">
                    {cohort.this_week.length} milestone{cohort.this_week.length === 1 ? '' : 's'} to submit
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-2 md:grid-cols-2">
                  {cohort.this_week.map((tw) => {
                    const config = SUBMISSION_TYPE_BY_ID[tw.submission_type];
                    const I = ICONS[config?.icon] || FileText;
                    return (
                      <Link
                        key={tw.milestone_id}
                        to={`/submit/a/${tw.assignment_id}/w/${tw.week_number}?cohort=${cohort.cohort_id}`}
                        className="flex items-center gap-3 bg-white/95 hover:bg-white rounded-lg p-3 transition-colors group"
                        data-testid={`this-week-item-${tw.milestone_id}`}
                      >
                        <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center flex-shrink-0">
                          <I className="w-5 h-5 text-[#22438E]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-[#000] truncate">{tw.assignment_title}</div>
                          <div className="text-xs text-[#666] truncate">
                            {tw.milestone_title}
                            {tw.is_final_capstone && <Star className="inline w-3 h-3 ml-1 text-[#7C3AED]" />}
                          </div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-[#22438E] group-hover:translate-x-0.5 transition-transform" />
                      </Link>
                    );
                  })}
                </CardContent>
              </Card>
            )}

            {/* Assignment sections */}
            <div className="space-y-3">
              {cohort.assignments.map((asgn) => {
                const config = SUBMISSION_TYPE_BY_ID[asgn.submission_type];
                const HeaderIcon = ICONS[config?.icon] || FileText;
                const submitted = asgn.milestones.filter(m => m.status !== 'not_started').length;
                const total = asgn.milestones.length;
                const isOpen = expanded[asgn.assignment_id];
                return (
                  <Card key={asgn.assignment_id} className="bg-white border-[#B8D4E8]" data-testid={`assignment-section-${asgn.assignment_id}`}>
                    <CardHeader className="pb-3">
                      <button
                        onClick={() => toggle(asgn.assignment_id)}
                        className="flex items-start gap-3 text-left w-full"
                        data-testid={`assignment-expand-${asgn.assignment_id}`}
                      >
                        {isOpen ? <ChevronDown className="w-5 h-5 text-[#666] mt-0.5 flex-shrink-0" /> : <ChevronRight className="w-5 h-5 text-[#666] mt-0.5 flex-shrink-0" />}
                        <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center flex-shrink-0">
                          <HeaderIcon className="w-5 h-5 text-[#22438E]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-base font-medium">{asgn.title}</CardTitle>
                          <CardDescription className="text-xs text-[#666]">
                            {submitted} / {total} milestones submitted
                          </CardDescription>
                        </div>
                        {/* Progress bar */}
                        <div className="hidden md:block w-24 h-2 bg-[#E5E7EB] rounded-full overflow-hidden mt-3">
                          <div className="h-full bg-[#22438E] transition-all" style={{ width: `${total ? (submitted / total) * 100 : 0}%` }}></div>
                        </div>
                      </button>
                    </CardHeader>
                    {isOpen && (
                      <CardContent className="pt-0">
                        {asgn.description && (
                          <p className="text-sm text-[#333] mb-3">{asgn.description}</p>
                        )}
                        <div className="space-y-1">
                          {asgn.milestones.map((m) => (
                            <Link
                              key={m.milestone_id}
                              to={`/submit/a/${asgn.assignment_id}/w/${m.week_number}?cohort=${cohort.cohort_id}`}
                              className="flex items-center gap-3 border border-[#E5E7EB] rounded-lg p-3 hover:bg-[#F8FBFF] hover:border-[#B8D4E8] transition-colors group"
                              data-testid={`milestone-row-${m.milestone_id}`}
                            >
                              <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0 ${
                                m.is_final_capstone ? 'bg-[#7C3AED] text-white' : (m.status === 'feedback_provided' ? 'bg-[#D1FAE5] text-[#065F46]' : 'bg-[#E1F0FF] text-[#22438E]')
                              }`}>
                                {m.is_final_capstone ? <Star className="w-4 h-4" /> : m.week_number}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-[#000] truncate">
                                  {m.title || `Week ${m.week_number}`}
                                </div>
                                {m.description && (
                                  <div className="text-xs text-[#666] truncate">{m.description}</div>
                                )}
                              </div>
                              {statusBadge(m.status)}
                              {m.status === 'feedback_provided' && (
                                <MessageCircle className="w-4 h-4 text-[#7C3AED]" title="Feedback available" />
                              )}
                              <ArrowRight className="w-4 h-4 text-[#94B8D9] group-hover:text-[#22438E] group-hover:translate-x-0.5 transition-all" />
                            </Link>
                          ))}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          </section>
        ))}
      </main>
    </div>
  );
}

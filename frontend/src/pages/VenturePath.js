import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { ArrowLeft, Rocket, Compass, Map, Layers, MessageCircle, Cog, Sparkles, Info } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Map icon names returned by the backend to lucide-react components. Falls back to Rocket.
const ICONS = {
  compass: Compass, map: Map, layers: Layers,
  message: MessageCircle, gear: Cog, rocket: Rocket,
};

// Visual + copy for each of the three badge tiers. Bronze at 50, Silver at 70,
// Gold at 85. "none" = student hasn't reached the first tier yet.
const TIER_META = {
  gold: {
    label: 'Gold',
    badge: 'Investor-Ready',
    circle: 'bg-gradient-to-br from-[#F5C518] to-[#B8860B] text-white',
    ring: 'border-[#F5C518] shadow-md',
    chip: 'bg-[#FEF3C7] text-[#78350F]',
  },
  silver: {
    label: 'Silver',
    badge: 'Traction Mode',
    circle: 'bg-gradient-to-br from-[#C0C7D1] to-[#7A8494] text-white',
    ring: 'border-[#C0C7D1] shadow-sm',
    chip: 'bg-[#F1F5F9] text-[#334155]',
  },
  bronze: {
    label: 'Bronze',
    badge: 'Building Momentum',
    circle: 'bg-gradient-to-br from-[#D97706] to-[#78350F] text-white',
    ring: 'border-[#D97706] shadow-sm',
    chip: 'bg-[#FFEDD5] text-[#7C2D12]',
  },
  none: {
    label: 'Locked',
    badge: 'Not started',
    circle: 'bg-[#E5E7EB] text-[#94A3B8]',
    ring: 'border-[#E5E7EB] opacity-80',
    chip: 'bg-[#F3F4F6] text-[#6B7280]',
  },
};

export default function VenturePath() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { studentId } = useParams();
  const isInstructorView = Boolean(studentId);

  const fetchPath = useCallback(async () => {
    try {
      const url = isInstructorView
        ? `${API_URL}/api/instructor/students/${studentId}/venture-path`
        : `${API_URL}/api/student/venture-path`;
      const res = await axios.get(url);
      setData(res.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not load Venture Path');
    } finally {
      setLoading(false);
    }
  }, [isInstructorView, studentId]);

  useEffect(() => { fetchPath(); }, [fetchPath]);

  if (loading) {
    return <div className="max-w-6xl mx-auto p-8"><p className="text-[#666]">Loading your Venture Path…</p></div>;
  }
  if (!data) return null;

  const {
    modules, trend, unlocked_count, total_modules, overall_best_score,
    gold_count = 0, silver_count = 0, bronze_count = 0, student = null,
  } = data;
  const chartData = trend.map((t, i) => ({
    name: t.title || `Wk ${t.week}`,
    week: t.week,
    score: t.score,
    idx: i + 1,
  }));

  const headline = isInstructorView && student
    ? `${student.name}'s Venture Path`
    : 'Your Venture Path';
  const subhead = isInstructorView && student
    ? `${student.email} — showing best score per module.`
    : null;

  return (
    <div className="max-w-6xl mx-auto px-6 md:px-12 py-8" data-testid="venture-path-page">
      <div className="flex items-center gap-3 mb-6">
        <Button
          variant="ghost" size="sm" onClick={() => navigate(-1)}
          className="text-[#22438E]" data-testid="venture-path-back-btn"
        >
          <ArrowLeft className="w-4 h-4 mr-1" /> Back
        </Button>
      </div>

      <div className="mb-6">
        <h1 className="text-3xl md:text-4xl font-normal text-[#000] mb-2" data-testid="venture-path-headline">{headline}</h1>
        {subhead ? (
          <p className="text-sm text-[#666] mb-2" data-testid="venture-path-subhead">{subhead}</p>
        ) : null}
        <p className="text-[#333] max-w-3xl">
          {isInstructorView
            ? 'Coach Max scores every submission from 1–100. Tiers unlock at Bronze 50, Silver 70, and Gold 85 per module.'
            : (
              <>Every submission earns a <strong>Founder Progress Score</strong> from Coach Max.
              Each module unlocks three tiers as you grow: <span className="text-[#7C2D12] font-medium">Bronze</span> at 50,
              {' '}<span className="text-[#334155] font-medium">Silver</span> at 70, and
              {' '}<span className="text-[#78350F] font-medium">Gold</span> at 85.</>
            )
          }
        </p>
      </div>

      {/* Best-of-many-attempts reassurance (student view only) */}
      {!isInstructorView && (
        <div
          className="flex items-start gap-2 bg-[#EFF6FF] border border-[#B8D4E8] rounded-lg p-3 mb-6 text-sm text-[#22438E]"
          data-testid="venture-path-best-attempt-note"
        >
          <Sparkles className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>
            Only your <strong>best attempt</strong> counts toward each badge. Resubmit any milestone as many times as you like — your highest score is the one we celebrate.
          </span>
        </div>
      )}

      {/* Progress summary */}
      <Card className="bg-white border-[#B8D4E8] mb-6" data-testid="venture-path-summary">
        <CardContent className="p-6 flex items-center gap-6 flex-wrap">
          <div>
            <p className="text-xs text-[#666] uppercase tracking-wide">Badges Earned</p>
            <p className="text-3xl font-medium text-[#22438E]">{unlocked_count} / {total_modules}</p>
            <div className="flex items-center gap-2 mt-1 text-xs">
              <span className="inline-flex items-center gap-1 text-[#78350F]" data-testid="venture-path-gold-count">
                <span className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-[#F5C518] to-[#B8860B]" />
                {gold_count} Gold
              </span>
              <span className="inline-flex items-center gap-1 text-[#334155]" data-testid="venture-path-silver-count">
                <span className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-[#C0C7D1] to-[#7A8494]" />
                {silver_count} Silver
              </span>
              <span className="inline-flex items-center gap-1 text-[#7C2D12]" data-testid="venture-path-bronze-count">
                <span className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-[#D97706] to-[#78350F]" />
                {bronze_count} Bronze
              </span>
            </div>
          </div>
          <div>
            <p className="text-xs text-[#666] uppercase tracking-wide">Best Progress Score</p>
            <p className="text-3xl font-medium text-[#22438E]">{overall_best_score || '—'}</p>
          </div>
          <div className="flex-1 min-w-[200px]">
            <div className="h-3 w-full bg-[#E1F0FF] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#22438E] transition-all"
                style={{ width: `${(unlocked_count / total_modules) * 100}%` }}
                data-testid="venture-path-progress-bar"
              />
            </div>
            <p className="text-xs text-[#666] mt-1">
              {Math.round((unlocked_count / total_modules) * 100)}% of the path started
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Score trend chart */}
      {chartData.length > 0 && (
        <Card className="bg-white border-[#B8D4E8] mb-8" data-testid="venture-path-trend-chart">
          <CardContent className="p-6">
            <h2 className="text-lg font-medium text-[#000] mb-3">Score Trend</h2>
            <div className="w-full h-64">
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#666' }} interval={0} angle={-15} textAnchor="end" height={55} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#666' }} />
                  <ReferenceLine y={50} stroke="#D97706" strokeDasharray="4 4" label={{ value: 'Bronze', fill: '#D97706', fontSize: 10, position: 'insideTopRight' }} />
                  <ReferenceLine y={70} stroke="#7A8494" strokeDasharray="4 4" label={{ value: 'Silver', fill: '#7A8494', fontSize: 10, position: 'insideTopRight' }} />
                  <ReferenceLine y={85} stroke="#B8860B" strokeDasharray="4 4" label={{ value: 'Gold', fill: '#B8860B', fontSize: 10, position: 'insideTopRight' }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="score" stroke="#22438E" strokeWidth={2} dot={{ fill: '#22438E', r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Badges grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {modules.map((m) => {
          const Icon = ICONS[m.icon] || Rocket;
          const tier = m.tier || (m.unlocked ? 'gold' : 'none');
          const meta = TIER_META[tier] || TIER_META.none;
          const hasBadge = tier !== 'none';
          return (
            <Card
              key={m.module}
              className={`border transition-all bg-white ${meta.ring}`}
              data-testid={`venture-path-module-${m.module}`}
            >
              <CardContent className="p-5">
                <div className="flex items-start gap-3 mb-3">
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${meta.circle}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-xs text-[#666] uppercase tracking-wide">Module {m.module}</p>
                      <span
                        className={`text-[10px] font-medium px-2 py-0.5 rounded-full uppercase tracking-wide ${meta.chip}`}
                        data-testid={`venture-path-tier-${m.module}`}
                      >
                        {meta.label}
                      </span>
                    </div>
                    <h3 className={`text-base font-medium ${hasBadge ? 'text-[#000]' : 'text-[#666]'}`}>
                      {m.name}
                    </h3>
                    <p className={`text-xs italic mt-0.5 ${hasBadge ? 'text-[#22438E]' : 'text-[#94A3B8]'}`}>
                      {meta.badge}
                    </p>
                  </div>
                </div>
                <p className={`text-sm mb-3 ${hasBadge ? 'text-[#333]' : 'text-[#666]'}`}>
                  {hasBadge
                    ? m.tagline
                    : m.attempted
                      ? `Great start at ${m.best_score}/100 — every resubmission gets you closer.`
                      : `Submit a Module ${m.module} assignment to start earning your first badge.`}
                </p>
                {(m.attempted || hasBadge) && (
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#666]">Best score</span>
                      <span className={`text-sm font-medium ${hasBadge ? 'text-[#22438E]' : 'text-[#666]'}`}>
                        {m.best_score}/100
                      </span>
                    </div>
                    {m.next_tier && m.points_to_next !== null && m.points_to_next > 0 && (
                      <span
                        className="text-[11px] text-[#22438E] bg-[#E1F0FF] px-2 py-0.5 rounded-full"
                        data-testid={`venture-path-points-to-next-${m.module}`}
                      >
                        {m.points_to_next} pts to {m.next_tier[0].toUpperCase() + m.next_tier.slice(1)}
                      </span>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Score band legend (encouraging tone) */}
      <div
        className="mt-8 flex items-start gap-2 text-xs text-[#666] bg-[#F9FAFB] border border-[#E5E7EB] rounded-lg p-4"
        data-testid="venture-path-legend"
      >
        <Info className="w-4 h-4 mt-0.5 text-[#22438E] flex-shrink-0" />
        <div className="leading-relaxed">
          <strong className="text-[#333]">How Coach Max scores you:</strong>{' '}
          <span className="text-[#7C2D12]">50-69 Building Momentum</span>{' · '}
          <span className="text-[#334155]">70-84 Traction Mode</span>{' · '}
          <span className="text-[#78350F]">85-100 Investor-Ready</span>.
          Most first-time founders land in the 50-75 range on their first attempt — that&apos;s exactly where you should be.
        </div>
      </div>
    </div>
  );
}

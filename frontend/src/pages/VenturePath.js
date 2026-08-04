import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { ArrowLeft, Rocket, Lock, Compass, Map, Layers, MessageCircle, Cog } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Map icon names returned by the backend to lucide-react components. Falls back to Rocket.
const ICONS = {
  compass: Compass, map: Map, layers: Layers,
  message: MessageCircle, gear: Cog, rocket: Rocket,
};

export default function VenturePath() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchPath = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/student/venture-path`);
      setData(res.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not load Venture Path');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPath(); }, [fetchPath]);

  if (loading) {
    return <div className="max-w-6xl mx-auto p-8"><p className="text-[#666]">Loading your Venture Path…</p></div>;
  }
  if (!data) return null;

  const { modules, trend, unlocked_count, total_modules, overall_best_score } = data;
  const chartData = trend.map((t, i) => ({
    name: t.title || `Wk ${t.week}`,
    week: t.week,
    score: t.score,
    idx: i + 1,
  }));

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

      <div className="mb-8">
        <h1 className="text-3xl md:text-4xl font-normal text-[#000] mb-2">Your Venture Path</h1>
        <p className="text-[#333]">
          Each module unlocks a badge when you score <strong>80 or higher</strong>. Coach Max
          scores every submission on an Investor Ready scale of 1–100.
        </p>
      </div>

      {/* Progress summary */}
      <Card className="bg-white border-[#B8D4E8] mb-6" data-testid="venture-path-summary">
        <CardContent className="p-6 flex items-center gap-6 flex-wrap">
          <div>
            <p className="text-xs text-[#666] uppercase tracking-wide">Badges Unlocked</p>
            <p className="text-3xl font-medium text-[#22438E]">{unlocked_count} / {total_modules}</p>
          </div>
          <div>
            <p className="text-xs text-[#666] uppercase tracking-wide">Best Investor Ready Score</p>
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
              {Math.round((unlocked_count / total_modules) * 100)}% of the path complete
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
                  <ReferenceLine y={80} stroke="#22438E" strokeDasharray="4 4" label={{ value: 'Badge threshold', fill: '#22438E', fontSize: 10 }} />
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
          const isUnlocked = m.unlocked;
          return (
            <Card
              key={m.module}
              className={`border transition-all ${
                isUnlocked
                  ? 'bg-white border-[#22438E] shadow-md'
                  : 'bg-[#F9FAFB] border-[#E5E7EB] opacity-70'
              }`}
              data-testid={`venture-path-module-${m.module}`}
            >
              <CardContent className="p-5">
                <div className="flex items-start gap-3 mb-3">
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${
                    isUnlocked ? 'bg-[#22438E] text-white' : 'bg-[#E5E7EB] text-[#94A3B8]'
                  }`}>
                    {isUnlocked ? <Icon className="w-6 h-6" /> : <Lock className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[#666] uppercase tracking-wide">Module {m.module}</p>
                    <h3 className={`text-base font-medium ${isUnlocked ? 'text-[#000]' : 'text-[#666]'}`}>
                      {m.name}
                    </h3>
                  </div>
                </div>
                <p className={`text-sm mb-3 ${isUnlocked ? 'text-[#333]' : 'text-[#94A3B8]'}`}>
                  {isUnlocked
                    ? m.tagline
                    : m.attempted
                      ? `Currently at ${m.best_score}/100 — reach 80 to unlock.`
                      : 'Submit a Module ' + m.module + ' assignment to start unlocking.'}
                </p>
                {(m.attempted || isUnlocked) && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#666]">Best score</span>
                    <span className={`text-sm font-medium ${isUnlocked ? 'text-[#22438E]' : 'text-[#666]'}`}>
                      {m.best_score}/100
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

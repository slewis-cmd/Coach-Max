import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { toast } from 'sonner';
import { 
  MessageCircle, ChevronDown, ChevronUp, Sparkles, Users, HelpCircle, 
  Lightbulb, BarChart3 
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function CoachMaxInsightsTab({ cohortId }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [insights, setInsights] = useState({});
  const [generatingWeek, setGeneratingWeek] = useState(null);
  const [expandedWeeks, setExpandedWeeks] = useState({});

  const fetchReport = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/cohorts/${cohortId}/coach-max-report`);
      setReport(res.data);
    } catch (_e) {
      toast.error('Failed to load Coach Max report');
    } finally {
      setLoading(false);
    }
  }, [cohortId]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const generateInsights = async (weekNumber) => {
    setGeneratingWeek(weekNumber);
    try {
      const res = await axios.post(`${API_URL}/api/cohorts/${cohortId}/coach-max-report/generate`, {
        week_number: weekNumber
      });
      setInsights(prev => ({ ...prev, [weekNumber]: res.data }));
      toast.success(`Insights generated for Week ${weekNumber}`);
    } catch (_e) {
      toast.error('Failed to generate insights');
    } finally {
      setGeneratingWeek(null);
    }
  };

  const toggleWeek = (wk) => setExpandedWeeks(prev => ({ ...prev, [wk]: !prev[wk] }));

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-6 h-6 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!report || report.total_questions === 0) {
    return (
      <Card className="bg-white border-[#D0E6F9]">
        <CardContent className="p-12 text-center">
          <MessageCircle className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
          <h3 className="text-lg font-medium text-[#333333] mb-2">No Coach Max Conversations Yet</h3>
          <p className="text-sm text-[#666666]">
            Students haven't started chatting with Coach Max. Conversations will appear here once feedback is delivered and students ask follow-up questions.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="coach-max-insights-tab">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="bg-white border-[#D0E6F9]">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
              <HelpCircle className="w-5 h-5 text-[#22438E]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-[#000000]">{report.total_questions}</p>
              <p className="text-xs text-[#666666]">Total Questions</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border-[#D0E6F9]">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 bg-[#E1F0FF] rounded-lg flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-[#22438E]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-[#000000]">{report.weeks.length}</p>
              <p className="text-xs text-[#666666]">Active Weeks</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Per-Week Breakdown */}
      {report.weeks.map((week) => (
        <Card key={week.week_number} className="bg-white border-[#D0E6F9]" data-testid={`insights-week-${week.week_number}`}>
          <CardContent className="p-0">
            {/* Week Header */}
            <div className="p-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-[#22438E] rounded-full flex items-center justify-center text-white text-sm font-bold">
                  {week.week_number}
                </div>
                <div>
                  <h3 className="font-medium text-[#000000]">{week.material_title}</h3>
                  <p className="text-xs text-[#666666]">
                    {week.question_count} questions from {week.unique_students} student{week.unique_students !== 1 ? 's' : ''}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => generateInsights(week.week_number)}
                  disabled={generatingWeek === week.week_number}
                  className="bg-[#22438E] text-white hover:bg-[#1A3A7A] text-xs"
                  data-testid={`generate-insights-week-${week.week_number}`}
                >
                  {generatingWeek === week.week_number ? (
                    <>
                      <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin mr-1.5" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3 h-3 mr-1.5" />
                      {insights[week.week_number] ? 'Refresh' : 'Generate'} Insights
                    </>
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleWeek(week.week_number)}
                  className="text-[#22438E]"
                  data-testid={`toggle-week-${week.week_number}`}
                >
                  {expandedWeeks[week.week_number] ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </Button>
              </div>
            </div>

            {/* AI Insights */}
            {insights[week.week_number] && (
              <div className="px-5 pb-4 space-y-4">
                {/* Summary */}
                <div className="bg-[#F0F9FF] rounded-lg p-4 border border-[#BAE6FD]">
                  <p className="text-sm font-medium text-[#22438E] mb-1 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" /> AI Summary
                  </p>
                  <p className="text-sm text-[#333333] leading-relaxed">{insights[week.week_number].summary}</p>
                </div>

                {/* Themes */}
                {insights[week.week_number].themes?.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-[#666666] uppercase tracking-wide">Themes</p>
                    {insights[week.week_number].themes.map((theme, i) => (
                      <div key={i} className="bg-white border border-[#E5E5E5] rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-[#000000]">{theme.theme}</span>
                          <span className="text-xs bg-[#E1F0FF] text-[#22438E] px-2 py-0.5 rounded-full font-medium flex items-center gap-1">
                            <Users className="w-3 h-3" /> {theme.count} question{theme.count !== 1 ? 's' : ''}
                          </span>
                        </div>
                        {theme.examples?.length > 0 && (
                          <ul className="text-xs text-[#666666] mt-1.5 space-y-0.5">
                            {theme.examples.map((ex, j) => (
                              <li key={j} className="pl-3 border-l-2 border-[#D0E6F9]">"{ex}"</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Recommendations */}
                {insights[week.week_number].recommendations?.length > 0 && (
                  <div className="bg-[#F0FDF4] rounded-lg p-4 border border-[#BBF7D0]">
                    <p className="text-xs font-semibold text-[#166534] uppercase tracking-wide mb-2 flex items-center gap-1.5">
                      <Lightbulb className="w-3.5 h-3.5" /> Recommendations
                    </p>
                    <ul className="space-y-1.5">
                      {insights[week.week_number].recommendations.map((rec, i) => (
                        <li key={i} className="text-sm text-[#166534] pl-4 relative before:content-[''] before:absolute before:left-0 before:top-2 before:w-1.5 before:h-1.5 before:bg-[#22C55E] before:rounded-full">
                          {rec}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Expandable Raw Questions */}
            {expandedWeeks[week.week_number] && (
              <div className="border-t border-[#E5E5E5] px-5 py-4">
                <p className="text-xs font-semibold text-[#666666] uppercase tracking-wide mb-3">All Questions</p>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {week.questions.map((q, i) => (
                    <div key={i} className="bg-[#F9F8F6] rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-1.5">
                        <div className="w-5 h-5 bg-[#22438E] rounded-full flex items-center justify-center">
                          <Users className="w-2.5 h-2.5 text-white" />
                        </div>
                        <span className="text-xs font-medium text-[#333333]">{q.student_name}</span>
                        <span className="text-xs text-[#999999]">{new Date(q.created_at).toLocaleDateString()}</span>
                      </div>
                      <p className="text-sm text-[#000000] font-medium mb-1">"{q.question}"</p>
                      <p className="text-xs text-[#666666] line-clamp-2">{q.response}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

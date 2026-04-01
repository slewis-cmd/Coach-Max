import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../components/ui/select';
import {
  ArrowLeft, RefreshCw, Users, BookOpen, CheckCircle, Link2, 
  Unlink, TrendingUp, Loader2
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function ThinkificSync() {
  const { user, isInstructor, loading: authLoading } = useAuth();
  const [courses, setCourses] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [progress, setProgress] = useState({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(null);
  const [refreshing, setRefreshing] = useState(null);
  const [selectedCourse, setSelectedCourse] = useState({});

  useEffect(() => {
    if (!authLoading && isInstructor) fetchData();
  }, [authLoading, isInstructor]);

  const fetchData = async () => {
    try {
      const [coursesRes, cohortsRes] = await Promise.all([
        axios.get(`${API_URL}/api/thinkific/courses`),
        axios.get(`${API_URL}/api/cohorts`)
      ]);
      setCourses(coursesRes.data);
      setCohorts(cohortsRes.data);

      // Fetch progress for linked cohorts
      const linked = cohortsRes.data.filter(c => c.thinkific_course_id);
      const progressMap = {};
      for (const c of linked) {
        try {
          const res = await axios.get(`${API_URL}/api/thinkific/progress/${c.cohort_id}`);
          progressMap[c.cohort_id] = res.data;
        } catch { /* skip */ }
      }
      setProgress(progressMap);
    } catch (error) {
      toast.error('Failed to load Thinkific data');
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async (cohortId) => {
    const courseId = selectedCourse[cohortId];
    if (!courseId) {
      toast.error('Select a Thinkific course first');
      return;
    }
    setSyncing(cohortId);
    try {
      const res = await axios.post(`${API_URL}/api/thinkific/sync-students/${cohortId}`, {
        course_id: parseInt(courseId)
      });
      toast.success(res.data.message);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Sync failed');
    } finally {
      setSyncing(null);
    }
  };

  const handleRefresh = async (cohortId) => {
    setRefreshing(cohortId);
    try {
      const res = await axios.post(`${API_URL}/api/thinkific/refresh-progress/${cohortId}`);
      toast.success(res.data.message);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Refresh failed');
    } finally {
      setRefreshing(null);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="thinkific-sync">
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/dashboard" className="p-2 hover:bg-[#E1F0FF] rounded-lg transition-colors">
              <ArrowLeft className="w-5 h-5 text-[#333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000]">Thinkific Integration</h1>
              <p className="text-sm text-[#666]">Sync students and track course progress</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 md:px-12 py-8 space-y-6">
        {/* Thinkific Courses */}
        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-[#1A75BA]" />
              Thinkific Courses ({courses.length})
            </CardTitle>
            <CardDescription>Courses available on your Thinkific site</CardDescription>
          </CardHeader>
          <CardContent>
            {courses.length === 0 ? (
              <p className="text-[#666] text-center py-4">No courses found on Thinkific</p>
            ) : (
              <div className="grid gap-3">
                {courses.map(course => (
                  <div key={course.id} className="flex items-center gap-4 p-3 border border-[#B8D4E8] rounded-lg" data-testid={`thinkific-course-${course.id}`}>
                    {course.image_url ? (
                      <img src={course.image_url} alt={course.name} className="w-16 h-12 object-cover rounded" />
                    ) : (
                      <div className="w-16 h-12 bg-[#E1F0FF] rounded flex items-center justify-center">
                        <BookOpen className="w-6 h-6 text-[#1A75BA]" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#000] truncate">{course.name}</p>
                      <p className="text-xs text-[#666]">{course.chapter_ids?.length || 0} chapters · ID: {course.id}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Cohort Linking & Sync */}
        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <Link2 className="w-5 h-5 text-[#22438E]" />
              Cohort Sync
            </CardTitle>
            <CardDescription>Link Thinkific courses to Coach Max cohorts and sync students</CardDescription>
          </CardHeader>
          <CardContent>
            {cohorts.length === 0 ? (
              <p className="text-[#666] text-center py-4">No cohorts found. Create a cohort first.</p>
            ) : (
              <div className="space-y-4">
                {cohorts.map(cohort => {
                  const isLinked = !!cohort.thinkific_course_id;
                  const linkedCourse = courses.find(c => c.id === cohort.thinkific_course_id);
                  const cohortProgress = progress[cohort.cohort_id] || [];
                  const avgProgress = cohortProgress.length > 0
                    ? Math.round(cohortProgress.reduce((sum, p) => sum + (p.percentage_completed || 0), 0) / cohortProgress.length)
                    : 0;

                  return (
                    <div key={cohort.cohort_id} className="border border-[#B8D4E8] rounded-lg p-4" data-testid={`sync-cohort-${cohort.cohort_id}`}>
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <h3 className="font-medium text-[#000]">{cohort.name}</h3>
                          <p className="text-xs text-[#666]">
                            {cohort.student_ids?.length || 0} students
                            {isLinked && linkedCourse && ` · Linked to: ${linkedCourse.name}`}
                          </p>
                        </div>
                        {isLinked && (
                          <div className="flex items-center gap-2">
                            <div className="text-right mr-2">
                              <p className="text-sm font-medium text-[#22438E]">{avgProgress}%</p>
                              <p className="text-xs text-[#666]">Avg Progress</p>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleRefresh(cohort.cohort_id)}
                              disabled={refreshing === cohort.cohort_id}
                              className="border-[#1A75BA] text-[#1A75BA]"
                              data-testid={`refresh-${cohort.cohort_id}`}
                            >
                              {refreshing === cohort.cohort_id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <RefreshCw className="w-4 h-4" />
                              )}
                            </Button>
                          </div>
                        )}
                      </div>

                      {!isLinked && (
                        <div className="flex items-center gap-3">
                          <Select
                            value={selectedCourse[cohort.cohort_id] || ''}
                            onValueChange={(v) => setSelectedCourse({ ...selectedCourse, [cohort.cohort_id]: v })}
                          >
                            <SelectTrigger className="flex-1">
                              <SelectValue placeholder="Select Thinkific course..." />
                            </SelectTrigger>
                            <SelectContent>
                              {courses.map(c => (
                                <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            onClick={() => handleSync(cohort.cohort_id)}
                            disabled={syncing === cohort.cohort_id || !selectedCourse[cohort.cohort_id]}
                            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
                            data-testid={`sync-btn-${cohort.cohort_id}`}
                          >
                            {syncing === cohort.cohort_id ? (
                              <Loader2 className="w-4 h-4 animate-spin mr-2" />
                            ) : (
                              <Users className="w-4 h-4 mr-2" />
                            )}
                            Sync Students
                          </Button>
                        </div>
                      )}

                      {/* Progress Table for linked cohorts */}
                      {isLinked && cohortProgress.length > 0 && (
                        <div className="mt-3 border-t border-[#B8D4E8] pt-3">
                          <p className="text-xs font-medium text-[#666] mb-2">Thinkific Progress</p>
                          <div className="space-y-1.5 max-h-48 overflow-y-auto">
                            {cohortProgress.map((p, i) => (
                              <div key={p.user_id || i} className="flex items-center gap-3 text-sm">
                                <span className="flex-1 truncate text-[#000]">{p.student_name}</span>
                                <div className="w-32 bg-[#E1F0FF] rounded-full h-2">
                                  <div
                                    className="h-2 rounded-full transition-all"
                                    style={{
                                      width: `${p.percentage_completed || 0}%`,
                                      backgroundColor: p.completed ? '#22438E' : '#7CBAE6'
                                    }}
                                  />
                                </div>
                                <span className="text-xs text-[#666] w-10 text-right">{p.percentage_completed || 0}%</span>
                                {p.completed && <CheckCircle className="w-4 h-4 text-[#22438E] flex-shrink-0" />}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Webhook Setup Instructions */}
        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#1A75BA]" />
              Real-Time Sync (Webhooks)
            </CardTitle>
            <CardDescription>Set up webhooks in Thinkific for automatic progress updates</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="bg-[#E1F0FF] rounded-lg p-4 space-y-3">
              <p className="text-sm text-[#000]">To enable real-time sync, set up webhooks in your Thinkific admin:</p>
              <ol className="text-sm text-[#333] space-y-2 list-decimal list-inside">
                <li>Go to <strong>Settings &rarr; Code & Analytics &rarr; Webhooks</strong> in Thinkific</li>
                <li>Click <strong>New Webhook</strong></li>
                <li>Set the Target URL to:</li>
              </ol>
              <div className="bg-white border border-[#B8D4E8] rounded-lg p-3 font-mono text-sm break-all select-all">
                {API_URL}/api/webhooks/thinkific
              </div>
              <ol start="4" className="text-sm text-[#333] space-y-2 list-decimal list-inside">
                <li>Create two webhooks with topics: <strong>enrollment.progress</strong> and <strong>lesson.completed</strong></li>
                <li>Save each webhook</li>
              </ol>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

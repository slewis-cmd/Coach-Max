import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogHeader, 
  DialogTitle,
  DialogFooter
} from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { 
  BookOpen, 
  Users, 
  FileText, 
  Plus, 
  LogOut,
  ChevronRight,
  Upload,
  ClipboardList
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function InstructorDashboard() {
  const { user, logout, loading, isAuthenticated, isInstructor } = useAuth();
  const navigate = useNavigate();
  const [cohorts, setCohorts] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [showCreateCohort, setShowCreateCohort] = useState(false);
  const [newCohort, setNewCohort] = useState({ name: '', description: '' });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/');
    } else if (!loading && !isInstructor) {
      navigate('/role-selection');
    }
  }, [loading, isAuthenticated, isInstructor, navigate]);

  useEffect(() => {
    if (isInstructor) {
      fetchData();
    }
  }, [isInstructor]);

  const fetchData = async () => {
    try {
      const [cohortsRes, submissionsRes] = await Promise.all([
        axios.get(`${API_URL}/api/cohorts`, { withCredentials: true }),
        axios.get(`${API_URL}/api/submissions`, { withCredentials: true })
      ]);
      setCohorts(cohortsRes.data);
      setSubmissions(submissionsRes.data);
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to load data');
    } finally {
      setLoadingData(false);
    }
  };

  const handleCreateCohort = async () => {
    if (!newCohort.name.trim()) {
      toast.error('Please enter a cohort name');
      return;
    }

    setCreating(true);
    try {
      await axios.post(`${API_URL}/api/cohorts`, newCohort, { withCredentials: true });
      toast.success('Cohort created successfully!');
      setShowCreateCohort(false);
      setNewCohort({ name: '', description: '' });
      fetchData();
    } catch (error) {
      toast.error('Failed to create cohort');
    } finally {
      setCreating(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const pendingSubmissions = submissions.filter(s => s.status === 'pending');

  if (loading || loadingData) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="instructor-dashboard">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 bottom-0 w-64 bg-[#F2F0ED] border-r border-[#E5E5E5] p-6 hidden md:block">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-8 h-8 bg-[#1A1A1A] rounded-lg flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-[#1A1A1A]">ThinkificAI</span>
        </div>

        <nav className="space-y-2">
          <Link 
            to="/dashboard"
            className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white text-[#1A1A1A] font-medium"
          >
            <FileText className="w-5 h-5" />
            Dashboard
          </Link>
          <Link 
            to="/submissions"
            className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#5A5A5A] hover:bg-white hover:text-[#1A1A1A] transition-colors"
          >
            <ClipboardList className="w-5 h-5" />
            Submissions
            {pendingSubmissions.length > 0 && (
              <span className="ml-auto bg-[#FDE047] text-[#1A1A1A] text-xs px-2 py-0.5 rounded-full">
                {pendingSubmissions.length}
              </span>
            )}
          </Link>
        </nav>

        <div className="absolute bottom-6 left-6 right-6">
          <div className="flex items-center gap-3 mb-4">
            {user?.picture && (
              <img src={user.picture} alt={user.name} className="w-10 h-10 rounded-full" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[#1A1A1A] truncate">{user?.name}</p>
              <p className="text-xs text-[#888] truncate">{user?.email}</p>
            </div>
          </div>
          <Button 
            variant="ghost" 
            className="w-full justify-start text-[#5A5A5A] hover:text-[#1A1A1A]"
            onClick={handleLogout}
            data-testid="logout-btn"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Sign Out
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="md:ml-64 p-6 md:p-8">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#1A1A1A] rounded-lg flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold">ThinkificAI</span>
          </div>
          <Button variant="ghost" size="icon" onClick={handleLogout}>
            <LogOut className="w-5 h-5" />
          </Button>
        </div>

        {/* Header */}
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl md:text-4xl font-light tracking-tight text-[#1A1A1A] mb-2">
            Welcome back, {user?.name?.split(' ')[0]}
          </h1>
          <p className="text-[#5A5A5A]">
            Manage your cohorts and review student submissions
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 stagger-children">
          <Card className="bg-white border-[#E5E5E5]">
            <CardContent className="p-4">
              <p className="text-sm text-[#888] mb-1">Cohorts</p>
              <p className="text-2xl font-light text-[#1A1A1A]">{cohorts.length}</p>
            </CardContent>
          </Card>
          <Card className="bg-white border-[#E5E5E5]">
            <CardContent className="p-4">
              <p className="text-sm text-[#888] mb-1">Total Students</p>
              <p className="text-2xl font-light text-[#1A1A1A]">
                {cohorts.reduce((acc, c) => acc + (c.student_ids?.length || 0), 0)}
              </p>
            </CardContent>
          </Card>
          <Card className="bg-white border-[#E5E5E5]">
            <CardContent className="p-4">
              <p className="text-sm text-[#888] mb-1">Pending Reviews</p>
              <p className="text-2xl font-light text-[#FDE047]">{pendingSubmissions.length}</p>
            </CardContent>
          </Card>
          <Card className="bg-white border-[#E5E5E5]">
            <CardContent className="p-4">
              <p className="text-sm text-[#888] mb-1">Reviewed</p>
              <p className="text-2xl font-light text-[#065F46]">
                {submissions.filter(s => s.status === 'reviewed').length}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Cohorts Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-light text-[#1A1A1A]">Your Cohorts</h2>
            <Button 
              data-testid="create-cohort-btn"
              onClick={() => setShowCreateCohort(true)}
              className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
            >
              <Plus className="w-4 h-4 mr-2" />
              New Cohort
            </Button>
          </div>

          {cohorts.length === 0 ? (
            <Card className="bg-white border-[#E5E5E5] border-dashed">
              <CardContent className="p-12 text-center">
                <Users className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No cohorts yet</h3>
                <p className="text-[#5A5A5A] mb-4">Create your first cohort to get started</p>
                <Button 
                  onClick={() => setShowCreateCohort(true)}
                  className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                >
                  Create Cohort
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {cohorts.map((cohort, index) => (
                <Card 
                  key={cohort.cohort_id}
                  className="bg-white border-[#E5E5E5] hover:shadow-md transition-shadow cursor-pointer group"
                  onClick={() => navigate(`/cohort/${cohort.cohort_id}`)}
                  style={{ animationDelay: `${index * 0.1}s` }}
                  data-testid={`cohort-card-${cohort.cohort_id}`}
                >
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg font-normal flex items-center justify-between">
                      {cohort.name}
                      <ChevronRight className="w-5 h-5 text-[#C4C4C4] group-hover:text-[#1A1A1A] transition-colors" />
                    </CardTitle>
                    <CardDescription>{cohort.description || 'No description'}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-4 text-sm text-[#5A5A5A]">
                      <span className="flex items-center gap-1">
                        <Users className="w-4 h-4" />
                        {cohort.student_ids?.length || 0} students
                      </span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Recent Submissions */}
        {pendingSubmissions.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-light text-[#1A1A1A]">Pending Reviews</h2>
              <Link 
                to="/submissions"
                className="text-sm text-[#5A5A5A] hover:text-[#1A1A1A] flex items-center gap-1"
              >
                View all <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="space-y-3">
              {pendingSubmissions.slice(0, 5).map((sub) => (
                <Card 
                  key={sub.submission_id}
                  className="bg-white border-[#E5E5E5] hover:shadow-sm transition-shadow cursor-pointer"
                  onClick={() => navigate(`/submission/${sub.submission_id}`)}
                  data-testid={`submission-${sub.submission_id}`}
                >
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-[#FDE047] rounded-lg flex items-center justify-center">
                        <Upload className="w-5 h-5 text-[#1A1A1A]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#1A1A1A]">{sub.student?.name || 'Unknown'}</p>
                        <p className="text-sm text-[#888]">
                          {sub.material?.title || 'Homework'} • Week {sub.material?.week_number || '?'}
                        </p>
                      </div>
                    </div>
                    <Button size="sm" className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg">
                      Review
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Create Cohort Dialog */}
      <Dialog open={showCreateCohort} onOpenChange={setShowCreateCohort}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Create New Cohort</DialogTitle>
            <DialogDescription>
              Create a cohort to organize your students and course materials.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="cohort-name">Cohort Name</Label>
              <Input
                id="cohort-name"
                data-testid="cohort-name-input"
                placeholder="e.g., Fall 2024 Leadership Course"
                value={newCohort.name}
                onChange={(e) => setNewCohort({ ...newCohort, name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="cohort-desc">Description (optional)</Label>
              <Textarea
                id="cohort-desc"
                data-testid="cohort-desc-input"
                placeholder="Brief description of the cohort..."
                value={newCohort.description}
                onChange={(e) => setNewCohort({ ...newCohort, description: e.target.value })}
                className="mt-1"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateCohort(false)}>
              Cancel
            </Button>
            <Button 
              data-testid="create-cohort-submit"
              onClick={handleCreateCohort}
              disabled={creating}
              className="bg-[#1A1A1A] text-white hover:bg-[#333]"
            >
              {creating ? 'Creating...' : 'Create Cohort'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { 
  ArrowLeft, Users, UserPlus, Shield, GraduationCap, BookOpen,
  User, UserMinus, Trash2
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { ClearSubmissionsDialog, InviteInstructorDialog } from '../components/admin/AdminDialogs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AdminManagement() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [users, setUsers] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  useEffect(() => {
    if (!authLoading && user?.role !== 'super_admin') {
      navigate('/dashboard');
    }
  }, [authLoading, user, navigate]);

  useEffect(() => {
    if (user?.role === 'super_admin') {
      fetchData();
    }
  }, [user]);

  const fetchData = async () => {
    try {
      const [usersRes, statsRes, cohortsRes] = await Promise.all([
        axios.get(`${API_URL}/api/admin/users`),
        axios.get(`${API_URL}/api/admin/stats`),
        axios.get(`${API_URL}/api/cohorts`)
      ]);
      setUsers(usersRes.data);
      setStats(statsRes.data);
      setCohorts(cohortsRes.data);
    } catch (error) {
      toast.error('Failed to load admin data');
    } finally {
      setLoading(false);
    }
  };

  const handleInviteInstructor = async () => {
    if (!inviteEmail.trim()) {
      toast.error('Please enter an email address');
      return;
    }

    setInviting(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/admin/invite-instructor`,
        { email: inviteEmail },
      );
      toast.success(res.data.message);
      setShowInvite(false);
      setInviteEmail('');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to invite instructor');
    } finally {
      setInviting(false);
    }
  };

  const handleRevokeInstructor = async (userId, name) => {
    if (!window.confirm(`Revoke instructor access for ${name}? They will become a student.`)) {
      return;
    }

    try {
      await axios.post(
        `${API_URL}/api/admin/revoke-instructor`,
        { user_id: userId },
      );
      toast.success(`${name} is now a student`);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to revoke access');
    }
  };

  const handleClearSubmissions = async () => {
    setClearing(true);
    try {
      const res = await axios.delete(`${API_URL}/api/admin/clear-submissions`);
      toast.success(res.data.message);
      setShowClearConfirm(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to clear submissions');
    } finally {
      setClearing(false);
    }
  };

  const handleDeleteCohort = async (cohortId, cohortName) => {
    if (!window.confirm(`Delete "${cohortName}"? This will permanently remove the cohort, its materials, and all student submissions. This cannot be undone.`)) return;
    try {
      await axios.delete(`${API_URL}/api/cohorts/${cohortId}`);
      toast.success(`"${cohortName}" deleted`);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete cohort');
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const instructors = users.filter(u => u.role === 'instructor');
  const students = users.filter(u => u.role === 'student');
  const superAdmins = users.filter(u => u.role === 'super_admin');

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="admin-management">
      {/* Header */}
      <header className="bg-white border-b border-[#B8D4E8] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/dashboard"
              className="p-2 hover:bg-[#D0E6F9] rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-[#333333]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#000000]">Admin Management</h1>
              <p className="text-sm text-[#666666]">Manage instructors and platform users</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Link
              to="/admin/branding"
              className="inline-flex items-center gap-1.5 px-3 py-2 border border-[#22438E] text-[#22438E] hover:bg-[#E1F0FF] rounded-lg text-sm"
              data-testid="branding-nav-btn"
            >
              Branding
            </Link>
            <Button 
              onClick={() => setShowInvite(true)}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
              data-testid="invite-instructor-btn"
            >
              <UserPlus className="w-4 h-4 mr-2" />
              Invite Instructor
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {/* Stats */}
        {stats && (
          <div className="grid md:grid-cols-4 gap-4 mb-8">
            <Card className="bg-white border-[#B8D4E8]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Users className="w-4 h-4 text-[#666666]" />
                  <p className="text-sm text-[#666666]">Total Users</p>
                </div>
                <p className="text-3xl font-light text-[#000000]">{stats.users.total}</p>
              </CardContent>
            </Card>
            <Card className="bg-[#FEF3C7] border-[#7CBAE6]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-4 h-4 text-[#1A75BA]" />
                  <p className="text-sm text-[#1A75BA]">Super Admins</p>
                </div>
                <p className="text-3xl font-light text-[#1A75BA]">{stats.users.super_admins}</p>
              </CardContent>
            </Card>
            <Card className="bg-[#E1F0FF] border-[#BAE6FD]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <GraduationCap className="w-4 h-4 text-[#22438E]" />
                  <p className="text-sm text-[#22438E]">Instructors</p>
                </div>
                <p className="text-3xl font-light text-[#22438E]">{stats.users.instructors}</p>
              </CardContent>
            </Card>
            <Card className="bg-[#E1F0FF] border-[#B8D4E8]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen className="w-4 h-4 text-[#22438E]" />
                  <p className="text-sm text-[#22438E]">Students</p>
                </div>
                <p className="text-3xl font-light text-[#22438E]">{stats.users.students}</p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Super Admins */}
        <Card className="bg-white border-[#B8D4E8] mb-6">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <Shield className="w-5 h-5 text-[#1A75BA]" />
              Super Admins
            </CardTitle>
            <CardDescription>Platform administrators with full access</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {superAdmins.map((u) => (
                <div key={u.user_id} className="flex items-center gap-4 p-3 bg-[#FEF3C7] rounded-lg">
                  {u.picture ? (
                    <img src={u.picture} alt={u.name} className="w-10 h-10 rounded-full" />
                  ) : (
                    <div className="w-10 h-10 bg-[#7CBAE6] rounded-full flex items-center justify-center">
                      <Shield className="w-5 h-5 text-[#1A75BA]" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-[#000000] truncate">{u.name}</p>
                    <p className="text-sm text-[#666666] truncate">{u.email}</p>
                  </div>
                  <span className="text-xs bg-[#7CBAE6] text-[#1A75BA] px-2 py-1 rounded">
                    Super Admin
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Instructors */}
        <Card className="bg-white border-[#B8D4E8] mb-6">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <GraduationCap className="w-5 h-5 text-[#22438E]" />
              Instructors ({instructors.length})
            </CardTitle>
            <CardDescription>Users who can create cohorts and review submissions</CardDescription>
          </CardHeader>
          <CardContent>
            {instructors.length === 0 ? (
              <div className="text-center py-8">
                <GraduationCap className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                <p className="text-[#666666]">No instructors yet</p>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="mt-2"
                  onClick={() => setShowInvite(true)}
                >
                  Invite First Instructor
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {instructors.map((u) => (
                  <div key={u.user_id} className="flex items-center gap-4 p-3 hover:bg-[#E1F0FF] rounded-lg transition-colors">
                    {u.picture ? (
                      <img src={u.picture} alt={u.name} className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 bg-[#E1F0FF] rounded-full flex items-center justify-center">
                        <GraduationCap className="w-5 h-5 text-[#22438E]" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#000000] truncate">{u.name}</p>
                      <p className="text-sm text-[#666666] truncate">{u.email}</p>
                    </div>
                    <Button 
                      variant="ghost" 
                      size="sm"
                      onClick={() => handleRevokeInstructor(u.user_id, u.name)}
                      className="text-red-500 hover:text-red-600 hover:bg-red-50"
                    >
                      <UserMinus className="w-4 h-4 mr-1" />
                      Revoke
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Students */}
        <Card className="bg-white border-[#B8D4E8]">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-[#22438E]" />
              Students ({students.length})
            </CardTitle>
            <CardDescription>Users who can enroll in cohorts and submit homework</CardDescription>
          </CardHeader>
          <CardContent>
            {students.length === 0 ? (
              <div className="text-center py-8">
                <BookOpen className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                <p className="text-[#666666]">No students yet</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {students.map((u) => (
                  <div key={u.user_id} className="flex items-center gap-4 p-3 hover:bg-[#E1F0FF] rounded-lg transition-colors">
                    {u.picture ? (
                      <img src={u.picture} alt={u.name} className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 bg-[#E1F0FF] rounded-full flex items-center justify-center">
                        <User className="w-5 h-5 text-[#22438E]" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#000000] truncate">{u.name}</p>
                      <p className="text-sm text-[#666666] truncate">{u.email}</p>
                    </div>
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={() => {
                        setInviteEmail(u.email);
                        setShowInvite(true);
                      }}
                      className="border-[#B8D4E8]"
                    >
                      <GraduationCap className="w-4 h-4 mr-1" />
                      Promote
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Cohorts */}
        <Card className="bg-white border-[#B8D4E8] mt-6">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-[#22438E]" />
              Cohorts ({cohorts.length})
            </CardTitle>
            <CardDescription>All cohorts on the platform</CardDescription>
          </CardHeader>
          <CardContent>
            {cohorts.length === 0 ? (
              <div className="text-center py-8">
                <BookOpen className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                <p className="text-[#666666]">No cohorts yet</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {cohorts.map((c) => (
                  <div key={c.cohort_id} className="flex items-center gap-4 p-3 hover:bg-[#E1F0FF] rounded-lg transition-colors" data-testid={`cohort-row-${c.cohort_id}`}>
                    <div className="w-10 h-10 bg-[#E1F0FF] rounded-full flex items-center justify-center flex-shrink-0">
                      <BookOpen className="w-5 h-5 text-[#22438E]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#000000] truncate">{c.name}</p>
                      <p className="text-xs text-[#666666]">{c.student_ids?.length || 0} students · {c.description || 'No description'}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteCohort(c.cohort_id, c.name)}
                      className="text-red-500 hover:text-red-600 hover:bg-red-50 flex-shrink-0"
                      data-testid={`delete-cohort-${c.cohort_id}`}
                    >
                      <Trash2 className="w-4 h-4 mr-1" />
                      Delete
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Danger Zone */}
        <Card className="bg-white border-red-200 mt-6">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2 text-red-700">
              <Trash2 className="w-5 h-5" />
              Data Management
            </CardTitle>
            <CardDescription>Destructive actions — use with caution</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between p-4 bg-red-50 rounded-lg">
              <div>
                <p className="font-medium text-[#000000]">Clear All Submissions</p>
                <p className="text-sm text-[#666666] mt-0.5">Deletes all student homework submissions, uploaded files, and AI chat history. Materials and cohorts are not affected.</p>
              </div>
              <Button
                variant="outline"
                onClick={() => setShowClearConfirm(true)}
                className="border-red-300 text-red-700 hover:bg-red-100 flex-shrink-0 ml-4"
                data-testid="clear-submissions-btn"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Clear All
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>

      <ClearSubmissionsDialog open={showClearConfirm} onOpenChange={setShowClearConfirm}
        clearing={clearing} onConfirm={handleClearSubmissions} />

      <InviteInstructorDialog open={showInvite} onOpenChange={setShowInvite}
        inviteEmail={inviteEmail} setInviteEmail={setInviteEmail}
        inviting={inviting} onSubmit={handleInviteInstructor} />
    </div>
  );
}

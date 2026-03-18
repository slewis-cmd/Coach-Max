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
import { 
  ArrowLeft,
  Users,
  UserPlus,
  Shield,
  GraduationCap,
  BookOpen,
  User,
  Mail,
  UserMinus,
  BarChart3
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AdminManagement() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);

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
      const [usersRes, statsRes] = await Promise.all([
        axios.get(`${API_URL}/api/admin/users`, { withCredentials: true }),
        axios.get(`${API_URL}/api/admin/stats`, { withCredentials: true })
      ]);
      setUsers(usersRes.data);
      setStats(statsRes.data);
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
        { withCredentials: true }
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
        { withCredentials: true }
      );
      toast.success(`${name} is now a student`);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to revoke access');
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const instructors = users.filter(u => u.role === 'instructor');
  const students = users.filter(u => u.role === 'student');
  const superAdmins = users.filter(u => u.role === 'super_admin');

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="admin-management">
      {/* Header */}
      <header className="bg-white border-b border-[#E5E5E5] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/dashboard"
              className="p-2 hover:bg-[#F2F0ED] rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-[#5A5A5A]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#1A1A1A]">Admin Management</h1>
              <p className="text-sm text-[#888]">Manage instructors and platform users</p>
            </div>
          </div>
          
          <Button 
            onClick={() => setShowInvite(true)}
            className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
            data-testid="invite-instructor-btn"
          >
            <UserPlus className="w-4 h-4 mr-2" />
            Invite Instructor
          </Button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {/* Stats */}
        {stats && (
          <div className="grid md:grid-cols-4 gap-4 mb-8">
            <Card className="bg-white border-[#E5E5E5]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Users className="w-4 h-4 text-[#888]" />
                  <p className="text-sm text-[#888]">Total Users</p>
                </div>
                <p className="text-3xl font-light text-[#1A1A1A]">{stats.users.total}</p>
              </CardContent>
            </Card>
            <Card className="bg-[#FEF3C7] border-[#FDE047]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-4 h-4 text-[#854D0E]" />
                  <p className="text-sm text-[#854D0E]">Super Admins</p>
                </div>
                <p className="text-3xl font-light text-[#854D0E]">{stats.users.super_admins}</p>
              </CardContent>
            </Card>
            <Card className="bg-[#E0F2FE] border-[#BAE6FD]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <GraduationCap className="w-4 h-4 text-[#075985]" />
                  <p className="text-sm text-[#075985]">Instructors</p>
                </div>
                <p className="text-3xl font-light text-[#075985]">{stats.users.instructors}</p>
              </CardContent>
            </Card>
            <Card className="bg-[#D1FAE5] border-[#BBF7D0]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen className="w-4 h-4 text-[#065F46]" />
                  <p className="text-sm text-[#065F46]">Students</p>
                </div>
                <p className="text-3xl font-light text-[#065F46]">{stats.users.students}</p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Super Admins */}
        <Card className="bg-white border-[#E5E5E5] mb-6">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <Shield className="w-5 h-5 text-[#854D0E]" />
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
                    <div className="w-10 h-10 bg-[#FDE047] rounded-full flex items-center justify-center">
                      <Shield className="w-5 h-5 text-[#854D0E]" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-[#1A1A1A] truncate">{u.name}</p>
                    <p className="text-sm text-[#888] truncate">{u.email}</p>
                  </div>
                  <span className="text-xs bg-[#FDE047] text-[#854D0E] px-2 py-1 rounded">
                    Super Admin
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Instructors */}
        <Card className="bg-white border-[#E5E5E5] mb-6">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <GraduationCap className="w-5 h-5 text-[#075985]" />
              Instructors ({instructors.length})
            </CardTitle>
            <CardDescription>Users who can create cohorts and review submissions</CardDescription>
          </CardHeader>
          <CardContent>
            {instructors.length === 0 ? (
              <div className="text-center py-8">
                <GraduationCap className="w-8 h-8 text-[#C4C4C4] mx-auto mb-2" />
                <p className="text-[#888]">No instructors yet</p>
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
                  <div key={u.user_id} className="flex items-center gap-4 p-3 hover:bg-[#F9F8F6] rounded-lg transition-colors">
                    {u.picture ? (
                      <img src={u.picture} alt={u.name} className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 bg-[#E0F2FE] rounded-full flex items-center justify-center">
                        <GraduationCap className="w-5 h-5 text-[#075985]" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#1A1A1A] truncate">{u.name}</p>
                      <p className="text-sm text-[#888] truncate">{u.email}</p>
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
        <Card className="bg-white border-[#E5E5E5]">
          <CardHeader>
            <CardTitle className="text-lg font-normal flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-[#065F46]" />
              Students ({students.length})
            </CardTitle>
            <CardDescription>Users who can enroll in cohorts and submit homework</CardDescription>
          </CardHeader>
          <CardContent>
            {students.length === 0 ? (
              <div className="text-center py-8">
                <BookOpen className="w-8 h-8 text-[#C4C4C4] mx-auto mb-2" />
                <p className="text-[#888]">No students yet</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {students.map((u) => (
                  <div key={u.user_id} className="flex items-center gap-4 p-3 hover:bg-[#F9F8F6] rounded-lg transition-colors">
                    {u.picture ? (
                      <img src={u.picture} alt={u.name} className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 bg-[#D1FAE5] rounded-full flex items-center justify-center">
                        <User className="w-5 h-5 text-[#065F46]" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#1A1A1A] truncate">{u.name}</p>
                      <p className="text-sm text-[#888] truncate">{u.email}</p>
                    </div>
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={() => {
                        setInviteEmail(u.email);
                        setShowInvite(true);
                      }}
                      className="border-[#E5E5E5]"
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
      </main>

      {/* Invite Instructor Dialog */}
      <Dialog open={showInvite} onOpenChange={setShowInvite}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Invite Instructor</DialogTitle>
            <DialogDescription>
              Enter the email of a user to promote them to instructor. They must have already signed up.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="invite-email">User Email</Label>
            <Input
              id="invite-email"
              data-testid="invite-email-input"
              type="email"
              placeholder="instructor@example.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="mt-1"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInvite(false)}>
              Cancel
            </Button>
            <Button 
              data-testid="invite-submit-btn"
              onClick={handleInviteInstructor}
              disabled={inviting}
              className="bg-[#1A1A1A] text-white hover:bg-[#333]"
            >
              {inviting ? 'Promoting...' : 'Promote to Instructor'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

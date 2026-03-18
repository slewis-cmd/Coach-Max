import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { GraduationCap, BookOpen } from 'lucide-react';

export default function RoleSelection() {
  const { user, setRole, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const [selecting, setSelecting] = useState(false);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/');
    }
    if (!loading && user?.role && user.role !== 'student') {
      navigate('/dashboard');
    }
  }, [loading, isAuthenticated, user, navigate]);

  const handleSelectRole = async (role) => {
    setSelecting(true);
    const success = await setRole(role);
    if (success) {
      navigate('/dashboard');
    }
    setSelecting(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center p-6">
      <div className="max-w-2xl w-full">
        <div className="text-center mb-12 animate-fade-in">
          <h1 className="text-4xl md:text-5xl font-light tracking-tight text-[#1A1A1A] mb-4">
            Welcome, {user?.name?.split(' ')[0]}!
          </h1>
          <p className="text-lg text-[#5A5A5A]">
            How would you like to use ThinkificAI?
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6 stagger-children">
          <Card 
            data-testid="role-instructor"
            className="cursor-pointer hover:-translate-y-1 transition-transform duration-300 border-2 border-transparent hover:border-[#1A1A1A]"
            onClick={() => handleSelectRole('instructor')}
          >
            <CardHeader className="text-center pb-2">
              <div className="w-16 h-16 bg-[#E0F2FE] rounded-2xl flex items-center justify-center mx-auto mb-4">
                <GraduationCap className="w-8 h-8 text-[#075985]" />
              </div>
              <CardTitle className="text-2xl font-normal">I'm an Instructor</CardTitle>
              <CardDescription className="text-base">
                Create cohorts, upload materials, and review student submissions
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              <Button 
                className="w-full bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                disabled={selecting}
              >
                Continue as Instructor
              </Button>
            </CardContent>
          </Card>

          <Card 
            data-testid="role-student"
            className="cursor-pointer hover:-translate-y-1 transition-transform duration-300 border-2 border-transparent hover:border-[#1A1A1A]"
            onClick={() => handleSelectRole('student')}
          >
            <CardHeader className="text-center pb-2">
              <div className="w-16 h-16 bg-[#D1FAE5] rounded-2xl flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8 text-[#065F46]" />
              </div>
              <CardTitle className="text-2xl font-normal">I'm a Student</CardTitle>
              <CardDescription className="text-base">
                Access course materials, submit homework, and receive AI feedback
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              <Button 
                className="w-full bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                disabled={selecting}
              >
                Continue as Student
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

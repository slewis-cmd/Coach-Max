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
    // If user already has a role, redirect to dashboard
    if (!loading && user?.role) {
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
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center p-6">
      <div className="max-w-2xl w-full">
        <div className="text-center mb-12 animate-fade-in">
          <h1 className="text-4xl md:text-5xl font-light tracking-tight text-[#000000] mb-4">
            Welcome, {user?.name?.split(' ')[0]}!
          </h1>
          <p className="text-lg text-[#333333]">
            How would you like to use ThinkificAI?
          </p>
        </div>

        <div className="grid md:grid-cols-1 gap-6 max-w-md mx-auto stagger-children">
          <Card 
            data-testid="role-student"
            className="cursor-pointer hover:-translate-y-1 transition-transform duration-300 border-2 border-transparent hover:border-[#000000]"
            onClick={() => handleSelectRole('student')}
          >
            <CardHeader className="text-center pb-2">
              <div className="w-16 h-16 bg-[#E1F0FF] rounded-2xl flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8 text-[#22438E]" />
              </div>
              <CardTitle className="text-2xl font-normal">I'm a Student</CardTitle>
              <CardDescription className="text-base">
                Access course materials, submit homework, and receive AI feedback
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              <Button 
                className="w-full bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg"
                disabled={selecting}
              >
                Continue as Student
              </Button>
            </CardContent>
          </Card>
          <p className="text-center text-sm text-[#666666]">
            Need instructor access? Ask your admin to promote your account.
          </p>
        </div>
      </div>
    </div>
  );
}

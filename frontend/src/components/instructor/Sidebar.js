import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../ui/button';
import { 
  BookOpen, FileText, ClipboardList, BarChart3, Shield, LogOut, Library, Link2
} from 'lucide-react';

export function InstructorSidebar({ user, isSuperAdmin, totalActionRequired, onLogout }) {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 bg-[#D0E6F9] border-r border-[#B8D4E8] p-6 hidden md:block">
      <div className="flex items-center gap-2 mb-8">
        <div className="w-8 h-8 bg-[#22438E] rounded-lg flex items-center justify-center">
          <BookOpen className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold text-[#000000]">The Boost Pad</span>
      </div>

      <nav className="space-y-2">
        <Link to="/dashboard"
          className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white text-[#000000] font-medium">
          <FileText className="w-5 h-5" />Dashboard
        </Link>
        <Link to="/submissions"
          className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#333333] hover:bg-white hover:text-[#000000] transition-colors">
          <ClipboardList className="w-5 h-5" />Submissions
          {totalActionRequired > 0 && (
            <span className="ml-auto bg-[#22438E] text-white text-xs px-2 py-0.5 rounded-full">{totalActionRequired}</span>
          )}
        </Link>
        <Link to="/progress"
          className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#333333] hover:bg-white hover:text-[#000000] transition-colors">
          <BarChart3 className="w-5 h-5" />Progress
        </Link>
        <Link to="/library"
          className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#333333] hover:bg-white hover:text-[#000000] transition-colors"
          data-testid="library-link">
          <Library className="w-5 h-5" />Library
        </Link>
        <Link to="/thinkific"
          className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#333333] hover:bg-white hover:text-[#000000] transition-colors"
          data-testid="thinkific-link">
          <Link2 className="w-5 h-5" />Thinkific
        </Link>
        {isSuperAdmin && (
          <Link to="/admin"
            className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#333333] hover:bg-white hover:text-[#000000] transition-colors"
            data-testid="admin-link">
            <Shield className="w-5 h-5" />Admin
          </Link>
        )}
      </nav>

      <div className="absolute bottom-6 left-6 right-6">
        <div className="flex items-center gap-3 mb-4">
          {user?.picture && (
            <img src={user.picture} alt={user.name} className="w-10 h-10 rounded-full" />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[#000000] truncate">{user?.name}</p>
            <p className="text-xs text-[#666666] truncate">{user?.email}</p>
          </div>
        </div>
        <Button variant="ghost" className="w-full justify-start text-[#333333] hover:text-[#000000]"
          onClick={onLogout} data-testid="logout-btn">
          <LogOut className="w-4 h-4 mr-2" />Sign Out
        </Button>
      </div>
    </aside>
  );
}

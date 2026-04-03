import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Users, X, Mail } from 'lucide-react';

export function StudentsTab({ cohort, invitingAll, onInviteAll, onAddStudent, onRemoveStudent }) {
  return (
    <>
      {cohort?.students?.length > 0 && (
        <div className="flex justify-end mb-4">
          <Button variant="outline" size="sm"
            onClick={onInviteAll} disabled={invitingAll}
            className="border-[#000000] text-[#000000] hover:bg-[#D0E6F9] rounded-lg"
            data-testid="invite-all-btn">
            <Mail className="w-4 h-4 mr-1.5" />
            {invitingAll ? 'Sending...' : 'Send Invitations to All'}
          </Button>
        </div>
      )}
      {cohort?.students?.length === 0 ? (
        <Card className="bg-white border-[#B8D4E8] border-dashed">
          <CardContent className="p-12 text-center">
            <Users className="w-12 h-12 text-[#94B8D9] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[#000000] mb-2">No students yet</h3>
            <p className="text-[#333333] mb-4">Add students by their email address</p>
            <Button onClick={onAddStudent} className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg">
              Add Student
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {cohort?.students?.map((student) => (
            <Card key={student.user_id} className="bg-white border-[#B8D4E8]">
              <CardContent className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  {student.picture ? (
                    <img src={student.picture} alt={student.name} className="w-10 h-10 rounded-full" />
                  ) : (
                    <div className="w-10 h-10 bg-[#D0E6F9] rounded-full flex items-center justify-center">
                      <Users className="w-5 h-5 text-[#666666]" />
                    </div>
                  )}
                  <div>
                    <p className="font-medium text-[#000000]">{student.name}</p>
                    <p className="text-sm text-[#666666]">{student.email}</p>
                  </div>
                </div>
                <Button variant="ghost" size="icon"
                  onClick={() => onRemoveStudent(student.user_id, student.name)}
                  className="text-red-500 hover:text-red-600 hover:bg-red-50">
                  <X className="w-4 h-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

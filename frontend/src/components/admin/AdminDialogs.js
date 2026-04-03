import React from 'react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Trash2 } from 'lucide-react';

export function ClearSubmissionsDialog({ open, onOpenChange, clearing, onConfirm }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl text-red-700">Clear All Submissions?</DialogTitle>
          <DialogDescription>
            This will permanently delete all student homework submissions, uploaded files, and AI tutor chat history. Course materials and cohorts will not be affected. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onConfirm} disabled={clearing}
            className="bg-red-600 text-white hover:bg-red-700" data-testid="confirm-clear-btn">
            {clearing ? 'Clearing...' : 'Yes, Clear All Submissions'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function InviteInstructorDialog({ open, onOpenChange, inviteEmail, setInviteEmail, inviting, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Invite Instructor</DialogTitle>
          <DialogDescription>
            Enter the email of a user to promote them to instructor. They must have already signed up.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Label htmlFor="invite-email">User Email</Label>
          <Input id="invite-email" data-testid="invite-email-input" type="email" placeholder="instructor@example.com"
            value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="mt-1" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="invite-submit-btn" onClick={onSubmit} disabled={inviting}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
            {inviting ? 'Promoting...' : 'Promote to Instructor'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

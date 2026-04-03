import React from 'react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';

export function CreateCohortDialog({ open, onOpenChange, newCohort, setNewCohort, creating, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Create New Cohort</DialogTitle>
          <DialogDescription>Create a cohort to organize your students and course materials.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label htmlFor="cohort-name">Cohort Name</Label>
            <Input id="cohort-name" data-testid="cohort-name-input" placeholder="e.g., Fall 2024 Leadership Course"
              value={newCohort.name} onChange={(e) => setNewCohort({ ...newCohort, name: e.target.value })} className="mt-1" />
          </div>
          <div>
            <Label htmlFor="cohort-desc">Description (optional)</Label>
            <Textarea id="cohort-desc" data-testid="cohort-desc-input" placeholder="Brief description of the cohort..."
              value={newCohort.description} onChange={(e) => setNewCohort({ ...newCohort, description: e.target.value })}
              className="mt-1" rows={3} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="create-cohort-submit" onClick={onSubmit} disabled={creating}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
            {creating ? 'Creating...' : 'Create Cohort'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

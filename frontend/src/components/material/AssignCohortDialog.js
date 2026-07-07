import React from 'react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';

export function AssignCohortDialog({
  open,
  onOpenChange,
  cohorts,
  materials,
  selectedMaterialId,
  onAssign,
  onUnassign,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Assign to Cohorts</DialogTitle>
          <DialogDescription>Select cohorts to share this material with.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-4 max-h-[400px] overflow-y-auto">
          {cohorts.length === 0 ? (
            <p className="text-sm text-[#666666] text-center py-4">No cohorts found.</p>
          ) : (
            cohorts.map((cohort) => {
              const mat = materials.find(m => m.material_id === selectedMaterialId);
              const isAssigned = mat?.cohort_ids?.includes(cohort.cohort_id);
              return (
                <div
                  key={cohort.cohort_id}
                  className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                    isAssigned ? 'border-[#22438E] bg-[#E1F0FF]' : 'border-[#B8D4E8] hover:bg-[#E1F0FF]'
                  }`}
                  onClick={() => {
                    if (isAssigned) {
                      onUnassign(selectedMaterialId, cohort.cohort_id);
                    } else {
                      onAssign(selectedMaterialId, cohort.cohort_id);
                    }
                  }}
                  data-testid={`assign-cohort-${cohort.cohort_id}`}
                >
                  <div>
                    <p className="font-medium text-[#000000]">{cohort.name}</p>
                    <p className="text-xs text-[#666666]">{cohort.student_ids?.length || 0} students</p>
                  </div>
                  {isAssigned ? (
                    <span className="text-xs bg-[#22438E] text-white px-2 py-0.5 rounded-full">Assigned</span>
                  ) : (
                    <span className="text-xs text-[#666666]">Click to assign</span>
                  )}
                </div>
              );
            })
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

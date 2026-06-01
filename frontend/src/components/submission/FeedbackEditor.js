import React from 'react';
import { Card, CardContent } from '../ui/card';
import { Textarea } from '../ui/textarea';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { FileDown } from 'lucide-react';

export function FeedbackEditor({
  editedFeedback,
  setEditedFeedback,
  saving,
  exporting,
  onCancel,
  onSave,
  onSaveAndSend,
}) {
  return (
    <Card className="bg-white border-[#B8D4E8]">
      <CardContent className="p-6">
        <Label className="text-sm text-[#333333] mb-2 block">
          Review and edit the AI-generated feedback before sending to the student
        </Label>
        <Textarea
          value={editedFeedback}
          onChange={(e) => setEditedFeedback(e.target.value)}
          className="min-h-[300px] mb-4 font-normal"
          placeholder="Enter feedback for the student..."
          data-testid="feedback-editor"
        />
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            onClick={onSave}
            disabled={saving}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
            data-testid="save-feedback-btn"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </Button>
          <Button
            onClick={onSaveAndSend}
            disabled={saving || exporting}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]"
          >
            <FileDown className="w-4 h-4 mr-2" />
            Save & Send
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

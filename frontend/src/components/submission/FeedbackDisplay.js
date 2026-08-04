import React from 'react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Volume2, Download } from 'lucide-react';
import { ProgressScoreBadge } from './ProgressScoreBadge';
import { stripProgressScoreLine } from '../../lib/progressScore';

export function FeedbackDisplay({
  isSent,
  currentFeedback,
  readinessScore,
  audioUrl,
  audioRef,
  generatingAudio,
  onGenerateAudio,
}) {
  const cleanFeedback = stripProgressScoreLine(currentFeedback);
  return (
    <Card className={isSent ? 'bg-[#F0FDF4] border-[#B8D4E8]' : 'bg-[#F0F9FF] border-[#BAE6FD]'}>
      <CardContent className="p-8">
        {readinessScore ? (
          <div className="mb-6">
            <ProgressScoreBadge score={readinessScore} />
          </div>
        ) : null}

        <div className="feedback-letter text-[#166534] whitespace-pre-wrap leading-relaxed">
          {cleanFeedback}
        </div>

        {/* Audio Player */}
        <div className="mt-6 pt-4 border-t border-[#B8D4E8]">
          {audioUrl ? (
            <div className="flex items-center gap-3" data-testid="audio-player">
              <audio ref={audioRef} src={audioUrl} controls className="flex-1 h-10" />
              <a
                href={audioUrl}
                download
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-[#22438E] text-white rounded-lg hover:bg-[#1A3A7A] transition-colors"
                data-testid="download-audio-btn"
              >
                <Download className="w-3.5 h-3.5" />
                MP3
              </a>
            </div>
          ) : (
            <Button
              onClick={onGenerateAudio}
              disabled={generatingAudio}
              variant="outline"
              className="border-[#22438E] text-[#22438E] hover:bg-[#E1F0FF]"
              data-testid="generate-audio-btn"
            >
              {generatingAudio ? (
                <>
                  <div className="w-4 h-4 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin mr-2"></div>
                  Generating Audio...
                </>
              ) : (
                <>
                  <Volume2 className="w-4 h-4 mr-2" />
                  Listen to Feedback
                </>
              )}
            </Button>
          )}
        </div>

        <div className="mt-4 text-right">
          <p className="text-sm text-[#22438E] italic">
            {isSent ? '— Feedback sent to student' : '— Draft (Not yet sent to student)'}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

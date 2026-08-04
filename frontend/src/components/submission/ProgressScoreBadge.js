import React from 'react';
import { Link } from 'react-router-dom';
import { Trophy, ArrowRight } from 'lucide-react';
import { tierFromScore } from '../../lib/progressScore';

/**
 * Founder Progress Score badge — shown at the top of AI feedback so students
 * see the tone-appropriate label (Bronze/Silver/Gold + tagline) instead of a
 * raw "Progress Score: 72/100" line at the bottom.
 *
 * Only renders when `score` is a positive integer. If null/undefined (e.g.,
 * the AI review is still running or failed) the component returns null and
 * the parent shows the feedback text alone.
 */
export function ProgressScoreBadge({ score, linkToVenturePath = true }) {
  if (!score || score <= 0) return null;
  const meta = tierFromScore(score);

  const body = (
    <div
      className={`flex items-center gap-4 p-4 rounded-xl border ${meta.chip}`}
      data-testid="founder-progress-score-badge"
    >
      <div className={`w-14 h-14 rounded-full flex items-center justify-center flex-shrink-0 ${meta.pill}`}>
        <Trophy className="w-6 h-6" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs uppercase tracking-wide opacity-80">Founder Progress Score</p>
        <div className="flex items-baseline gap-2 flex-wrap">
          <span
            className="text-2xl font-medium"
            data-testid="founder-progress-score-value"
          >
            {score}<span className="text-sm opacity-70">/100</span>
          </span>
          <span
            className="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-current opacity-90"
            data-testid="founder-progress-score-tier"
          >
            {meta.label} · {meta.badgeName}
          </span>
        </div>
      </div>
      {linkToVenturePath && (
        <Link
          to="/venture-path"
          className="hidden sm:inline-flex items-center gap-1 text-xs font-medium hover:underline flex-shrink-0"
          data-testid="founder-progress-score-link"
        >
          View Venture Path
          <ArrowRight className="w-3 h-3" />
        </Link>
      )}
    </div>
  );

  return body;
}

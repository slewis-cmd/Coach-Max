/**
 * Helpers for the Founder Progress Score badge shown on each submission.
 * Keeps the score-line stripping + tier mapping in one place so any view
 * that renders AI feedback can benefit consistently.
 */

// Matches the trailing "Progress Score: 72/100" or legacy "Readiness Score: 72/100"
// line the backend appends to AI feedback via INVESTOR_SCORE_INSTRUCTION.
const SCORE_LINE_RE = /\s*(?:Progress|Readiness)\s*Score\s*:\s*\d{1,3}\s*(?:\/\s*100)?\s*$/im;

/** Remove the trailing machine-readable score line so it doesn't leak into UI. */
export function stripProgressScoreLine(text) {
  if (!text) return text;
  return text.replace(SCORE_LINE_RE, '').trimEnd();
}

/** Map a 0..100 score to its Bronze/Silver/Gold tier + display metadata. */
export function tierFromScore(score) {
  const s = Number(score) || 0;
  if (s >= 85) {
    return {
      tier: 'gold',
      label: 'Gold',
      badgeName: 'Investor-Ready',
      chip: 'bg-[#FEF3C7] text-[#78350F] border-[#F5C518]',
      pill: 'bg-gradient-to-br from-[#F5C518] to-[#B8860B] text-white',
    };
  }
  if (s >= 70) {
    return {
      tier: 'silver',
      label: 'Silver',
      badgeName: 'Traction Mode',
      chip: 'bg-[#F1F5F9] text-[#334155] border-[#C0C7D1]',
      pill: 'bg-gradient-to-br from-[#C0C7D1] to-[#7A8494] text-white',
    };
  }
  if (s >= 50) {
    return {
      tier: 'bronze',
      label: 'Bronze',
      badgeName: 'Building Momentum',
      chip: 'bg-[#FFEDD5] text-[#7C2D12] border-[#D97706]',
      pill: 'bg-gradient-to-br from-[#D97706] to-[#78350F] text-white',
    };
  }
  return {
    tier: 'none',
    label: 'Strong Start',
    badgeName: 'Strong Start',
    chip: 'bg-[#EFF6FF] text-[#22438E] border-[#B8D4E8]',
    pill: 'bg-[#22438E] text-white',
  };
}

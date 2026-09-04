/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Surface layers ── deep forest green
        base:   '#152018',
        panel:  '#1C2A1F',
        raised: '#233026',
        // ── Borders ── warm green-tinted
        line:   '#2E4232',
        line2:  '#3B5340',
        // ── Typography ── warm ivory
        ink:    '#F0EAD6',
        muted:  '#A89F89',
        dim:    '#6B6456',
        // ── Semantic states ──
        cleared: '#52B86A',   // emerald — trust, settlement
        blocked: '#C94030',   // vermillion — contradiction, block
        context: '#D4870A',   // amber — human judgment
        wire:    '#C9A84C',   // antique gold — money, value, active
      },
      fontFamily: {
        sans:   ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono:   ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
        serif:  ['Playfair Display', 'Georgia', 'Cambria', 'ui-serif', 'serif'],
      },
      keyframes: {
        'fade-in':    { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        'slide-up':   { '0%': { opacity: '0', transform: 'translateY(8px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'pulse-dot':  { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
      },
      animation: {
        'fade-in':   'fade-in 0.35s ease-out forwards',
        'slide-up':  'slide-up 0.35s ease-out forwards',
        'pulse-dot': 'pulse-dot 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

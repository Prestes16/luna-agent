/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg:      '#080b14',
          bg2:     '#0d1117',
          surface: '#0f1624',
          border:  '#1a2332',
          cyan:    '#00d4ff',
          purple:  '#7c3aed',
          pink:    '#e040fb',
          green:   '#10b981',
          yellow:  '#f59e0b',
          red:     '#ef4444',
          text:    '#e2e8f0',
          muted:   '#64748b',
          dim:     '#334155',
        },
      },
      boxShadow: {
        'cyan':    '0 0 20px rgba(0,212,255,0.25), 0 0 60px rgba(0,212,255,0.08)',
        'cyan-sm': '0 0 8px rgba(0,212,255,0.4)',
        'purple':  '0 0 20px rgba(124,58,237,0.35)',
        'glass':   '0 4px 24px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.05)',
      },
      fontFamily: {
        mono: ['Consolas', '"Cascadia Code"', 'monospace'],
        sans: ['"Segoe UI"', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-cyan': 'pulse-cyan 2s ease-in-out infinite',
        'slide-in':   'slide-in 0.25s ease-out',
        'fade-up':    'fade-up 0.3s ease-out',
        'blink':      'blink 1s step-end infinite',
        'spin-slow':  'spin 3s linear infinite',
        'shimmer':    'shimmer 2s linear infinite',
      },
      keyframes: {
        'pulse-cyan': {
          '0%, 100%': { boxShadow: '0 0 8px rgba(0,212,255,0.4)' },
          '50%':      { boxShadow: '0 0 24px rgba(0,212,255,0.8), 0 0 48px rgba(0,212,255,0.3)' },
        },
        'slide-in': {
          '0%':   { transform: 'translateX(-10px)', opacity: '0' },
          '100%': { transform: 'translateX(0)',     opacity: '1' },
        },
        'fade-up': {
          '0%':   { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',    opacity: '1' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
}

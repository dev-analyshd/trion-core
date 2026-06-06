import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: '#030711',
        sidebar: '#060e1e',
        card: '#0a1628',
        card2: '#0d1e38',
        border: '#122040',
        border2: '#1a3356',
        t1: '#e2eaf4',
        t2: '#7f9bb8',
        t3: '#4a6b8a',
        cyan: '#00c2ff',
        cyan2: '#00a3d9',
        violet: '#7c3aed',
        violet2: '#9f67f5',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        blink: 'blink 2s infinite',
        'pulse-slow': 'pulse 3s infinite',
        'flash-in': 'flashIn 0.6s ease-out',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        flashIn: {
          '0%': { backgroundColor: 'rgba(0, 194, 255, 0.12)', opacity: '0.7' },
          '100%': { backgroundColor: 'transparent', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};

export default config;

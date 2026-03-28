/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: '#0a0f1e',
          surface: '#0d1426',
          border: '#1e2d4a',
          primary: '#00d4ff',
          success: '#00ff88',
          warning: '#ffaa00',
          danger: '#ff4466',
        },
      },
      animation: {
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}

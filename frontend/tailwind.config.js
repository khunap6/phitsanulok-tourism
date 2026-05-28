/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          bg: '#0f172a',
          card: '#1e293b',
          border: '#334155',
          primary: '#3b82f6',
          text: '#e2e8f0',
          subtext: '#94a3b8',
        },
        severity: {
          high: '#ef4444',
          medium: '#f97316',
          low: '#eab308',
        },
      },
    },
  },
  plugins: [],
}

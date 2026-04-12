/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      keyframes: {
        'bounce-in': {
          '0%': { transform: 'translate(-50%, -20px)', opacity: '0' },
          '60%': { transform: 'translate(-50%, 10px)' },
          '100%': { transform: 'translate(-50%, 0)', opacity: '1' },
        },
        'scale-in': {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        }
      },
      animation: {
        'bounce-in': 'bounce-in 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28)',
        'scale-in': 'scale-in 0.2s ease-out',
      }
    },
  },
  plugins: [],
}

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Credit Portal UI talks to the Credit Portal API (FastAPI, port 8100) through /api.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8100',
    },
  },
})

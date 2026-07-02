import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Single source of truth: read the repo-root .env (two levels up) for VITE_*
  // vars. Path is relative to this config's folder (the Vite project root).
  // Only VITE_* vars reach the bundle; backend secrets in that .env are never
  // shipped to the client. On Render, VITE_* come from the service env instead,
  // so a missing root .env there is fine.
  envDir: '../../',
  server: {
    port: 5173,
  },
})

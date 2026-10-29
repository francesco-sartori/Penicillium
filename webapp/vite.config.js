import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run build` writes into the Python package, which serves it (penicillium dcs).
// `npm run dev` serves the console on :5173 and forwards the WebSocket to a running `penicillium dcs` on :8050.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/penicillium/dcs/static',
    emptyOutDir: true,
  },
  server: {
    proxy: { '/ws': { target: 'ws://127.0.0.1:8050', ws: true } },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, '../src/lumberjack/web/static'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/lumber': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(rootDir, '../src/lumberjack/web/static'),
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

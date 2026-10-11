import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Запросы /api/* в режиме разработки уходят на бэкенд FastAPI
    proxy: { '/api': 'http://localhost:8000' },
  },
})

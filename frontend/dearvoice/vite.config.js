import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/skyvoice': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
    port: 5173,
    hmr: {
      protocol: 'ws',
      host: 'localhost',
    },
    historyApiFallback: true,
  },
  // Vitest 설정 (npm test)
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'cobertura', 'html'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.{js,jsx,tsx}'],
      exclude: ['src/test/**', 'src/**/*.test.{js,jsx}', 'src/main.jsx'],
    },
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8082'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': apiProxyTarget,
      '/healthz': apiProxyTarget,
      '/readyz': apiProxyTarget,
    },
  },
  build: {
    chunkSizeWarningLimit: 2000,
  },
})

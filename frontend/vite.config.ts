import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': decodeURIComponent(new URL('./src', import.meta.url).pathname),
    },
  },
  build: {
    outDir: '../frontend_dist',
    emptyOutDir: false,
    assetsDir: 'ui-assets',
  },
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8770',
      '/artifacts': 'http://127.0.0.1:8770',
      '/bundled': 'http://127.0.0.1:8770',
      '/demo': 'http://127.0.0.1:8770',
      '/assets': 'http://127.0.0.1:8770'
    }
  }
})

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
      '/auth':     { target: 'http://localhost:8000', changeOrigin: true },
      '/segments': { target: 'http://localhost:8000', changeOrigin: true },
      '/signals':  { target: 'http://localhost:8000', changeOrigin: true },
      '/mpi':      { target: 'http://localhost:8000', changeOrigin: true },
      '/health':   { target: 'http://localhost:8000', changeOrigin: true },
      '/performance': { target: 'http://localhost:8000', changeOrigin: true },
      '/playbooks':   { target: 'http://localhost:8000', changeOrigin: true },
      '/alerts':      { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});

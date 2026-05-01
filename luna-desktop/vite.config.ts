import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@':            path.resolve(__dirname, './src'),
      '@components':  path.resolve(__dirname, './src/components'),
      '@pages':       path.resolve(__dirname, './src/pages'),
      '@services':    path.resolve(__dirname, './src/services'),
      '@utils':       path.resolve(__dirname, './src/utils'),
      '@types':       path.resolve(__dirname, './src/types'),
      '@hooks':       path.resolve(__dirname, './src/hooks'),
      '@store':       path.resolve(__dirname, './src/store'),
      '@i18n':        path.resolve(__dirname, './src/i18n'),
    }
  },

  // Pre-bundle all commonly used deps upfront so Vite doesn't need
  // to restart the server when it discovers new dependencies at runtime.
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react-router-dom',
      'zustand',
      'zustand/middleware',
      'framer-motion',
      'lucide-react',
      'axios',
      'recharts',
      'react-markdown',
      'remark-gfm',
      'react-syntax-highlighter',
      'react-syntax-highlighter/dist/esm/styles/prism',
      'crypto-js',
      'tweetnacl',
      'js-sha256',
    ],
    // Heavy blockchain libs: only load when Blockchain page is opened
    exclude: ['web3', '@solana/web3.js', '@solana/wallet-adapter-react'],
  },

  server: {
    port: 5173,
    strictPort: false,
    // Reduce HMR overlay noise
    hmr: { overlay: true },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      }
    }
  },

  build: {
    outDir: 'dist',
    sourcemap: false,          // disable sourcemaps in prod for smaller bundle
    minify: 'esbuild',         // esbuild is much faster than terser
    target: 'esnext',
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor':      ['react', 'react-dom', 'react-router-dom'],
          'ui-vendor':         ['framer-motion', 'lucide-react', 'recharts'],
          'markdown-vendor':   ['react-markdown', 'remark-gfm', 'react-syntax-highlighter'],
          'crypto-vendor':     ['crypto-js', 'tweetnacl', 'js-sha256'],
          'blockchain-vendor': ['web3', '@solana/web3.js'],
        }
      }
    }
  }
})

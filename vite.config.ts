import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const custom = process.env.THESMIO_CUSTOM_DOMAIN === 'true';
export default defineConfig({plugins:[react()],base:custom?'/':'/thesmio/',build:{outDir:'dist'}});

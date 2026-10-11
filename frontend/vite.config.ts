import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // ไฟล์นิยามที่ใช้ร่วมกับฝั่ง Python — อ่านไฟล์เดียวกันทั้งสองฝั่ง
      // ไม่ทำสำเนา เพราะสำเนาจะเพี้ยนจากกันเมื่อแก้ที่เดียว
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // ต้องอนุญาตให้ dev server อ่านไฟล์นอกโฟลเดอร์ frontend ได้
    fs: { allow: ['..'] },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

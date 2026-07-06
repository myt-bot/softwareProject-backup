import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          // iconify-icon 是通过 CDN 引入的 Web Component，不是 Vue 组件
          isCustomElement: tag => tag === "iconify-icon",
        },
      },
    }),
  ],
  server: {
    port: 5173,
  },
});

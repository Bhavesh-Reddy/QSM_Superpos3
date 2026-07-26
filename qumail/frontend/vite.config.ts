import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" so the built assets resolve correctly when loaded via
// file:// from Electron's packaged app (see electron/main.js).
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
  },
});

import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function appLink() {
  return {
    name: "app-link",
    configureServer(server) {
      server.printUrls = () => {
        const url = server.resolvedUrls?.local?.[0];
        if (!url) return;
        const bold = "\x1b[1m";
        const cyan = "\x1b[36m";
        const dim = "\x1b[2m";
        const reset = "\x1b[0m";
        console.log("");
        console.log(`  ${bold}Healthcare call extraction${reset}`);
        console.log(`  ${dim}Open this link in your browser:${reset}`);
        console.log(`  ${cyan}${url}${reset}`);
        console.log("");
      };
    },
  };
}

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    fs: { allow: [repoRoot] },
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
    warmup: {
      clientFiles: ["./src/main.tsx"],
    },
  },
  plugins: [react(), appLink()],
});

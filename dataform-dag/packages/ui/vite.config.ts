import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Standalone dev harness: mounts the UI against a MockBridge so packages/ui runs on its own,
// with no VS Code and no real project — spec step 2. The two hosts consume the same src later.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
  },
});

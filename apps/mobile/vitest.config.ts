import { defineConfig } from "vitest/config";

// Only the platform-independent core is unit-tested here; it imports no React Native code.
export default defineConfig({
  test: { include: ["src/core/**/*.test.ts"], environment: "node" },
});

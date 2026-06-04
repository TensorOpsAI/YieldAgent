// eslint-config-next 16 ships a native ESLint 9 flat config (typescript-eslint +
// react + react-hooks + jsx-a11y + @next/next), so we spread it directly.
import next from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  ...next,
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
];

export default eslintConfig;

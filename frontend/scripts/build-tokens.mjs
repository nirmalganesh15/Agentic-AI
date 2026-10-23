// Generates src/tokens.css (CSS custom properties, light + dark) and public/design-tokens.json
// from design-tokens.json. Runs automatically before `npm start` and `npm run build`.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const tokens = JSON.parse(readFileSync(resolve(root, 'design-tokens.json'), 'utf8'));

// color.bg -> --bg ; radius.default -> --radius ; space.4 -> --space-4
const varName = (group, name) => {
  if (group === 'color') return `--${name}`;
  return name === 'default' ? `--${group}` : `--${group}-${name}`;
};

const light = [];
const dark = [];
for (const [group, entries] of Object.entries(tokens)) {
  if (group.startsWith('$')) continue;
  for (const [name, token] of Object.entries(entries)) {
    const variable = varName(group, name);
    if ('value' in token) {
      light.push(`  ${variable}: ${token.value};`);
    } else {
      light.push(`  ${variable}: ${token.light};`);
      if (token.dark !== token.light) dark.push(`  ${variable}: ${token.dark};`);
    }
  }
}

const css = `/* GENERATED from design-tokens.json by scripts/build-tokens.mjs. Do not edit by hand. */
:root {
  color-scheme: light;
${light.join('\n')}
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
${dark.map(l => '  ' + l).join('\n')}
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
${dark.join('\n')}
}
`;

writeFileSync(resolve(root, 'src/tokens.css'), css);
mkdirSync(resolve(root, 'public'), { recursive: true });
// Published so AI design and code generation tools can read the same tokens and usage rules
writeFileSync(resolve(root, 'public/design-tokens.json'), JSON.stringify(tokens, null, 2) + '\n');
console.log(`tokens: ${light.length} variables (${dark.length} with dark overrides) -> src/tokens.css`);

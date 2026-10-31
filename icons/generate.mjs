// Renders each app's SVG into the Home Screen icons in its public/ folder.
// Run after changing an SVG: npm install && npm run generate
import { readFileSync, writeFileSync } from 'node:fs'
import { Resvg } from '@resvg/resvg-js'

const APPS = {
  'pocket-money': 'frontend',
  deductions: 'deductions-frontend',
  'family-photos': 'family-photos-frontend',
  investments: 'investments-frontend',
  utilities: 'utilities-frontend',
}

const png = (svg, size) =>
  new Resvg(svg, { fitTo: { mode: 'width', value: size } }).render().asPng()

// An .ico is a small directory followed by the images, which may be PNGs.
function ico(svg, sizes) {
  const images = sizes.map((size) => png(svg, size))
  const header = Buffer.alloc(6 + 16 * sizes.length)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(sizes.length, 4)
  let offset = header.length
  images.forEach((image, i) => {
    const entry = 6 + 16 * i
    header[entry] = sizes[i]
    header[entry + 1] = sizes[i]
    header.writeUInt16LE(1, entry + 4)
    header.writeUInt16LE(32, entry + 6)
    header.writeUInt32LE(image.length, entry + 8)
    header.writeUInt32LE(offset, entry + 12)
    offset += image.length
  })
  return Buffer.concat([header, ...images])
}

for (const [name, frontend] of Object.entries(APPS)) {
  const svg = readFileSync(new URL(`${name}.svg`, import.meta.url))
  const out = (file) => new URL(`../${frontend}/public/${file}`, import.meta.url)
  writeFileSync(out('apple-touch-icon.png'), png(svg, 180))
  writeFileSync(out('icon-192.png'), png(svg, 192))
  writeFileSync(out('icon-512.png'), png(svg, 512))
  writeFileSync(out('favicon.ico'), ico(svg, [16, 32, 48]))
}

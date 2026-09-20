import { rm } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const distribution = fileURLToPath(new URL('../../frontend_dist/', import.meta.url))
const generated = fileURLToPath(new URL('../../frontend_dist/ui-assets/', import.meta.url))

if (!generated.startsWith(distribution) || !generated.endsWith('/ui-assets/')) {
  throw new Error('Refusing to clean an unexpected output directory')
}

await rm(generated, { recursive:true, force:true })

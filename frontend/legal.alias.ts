/**
 * 법률 문서 별칭.
 *
 * `vite.config.ts` 와 `vitest.config.ts` 가 따로 있어서, 별칭을 두 곳에 적으면
 * 한쪽만 고쳐진다. 여기 한 번만 적고 양쪽이 가져다 쓴다.
 *
 * 문서를 `frontend/` 안으로 복사하지 않는 이유는 그러면 같은 문서가 두 벌이
 * 되기 때문이다. `legal/` 이 단일 원본이다.
 */

import { fileURLToPath, URL } from 'node:url'

export const legalAlias = {
  '@legal': fileURLToPath(new URL('../legal', import.meta.url)),
}

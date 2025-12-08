# Dependency: hello-wasm

## How we use it

hello-web consumes the compiled WASM binary from hello-wasm and transpiles it into JavaScript modules that can be imported in the browser. The dependency is integrated at build time:

**Build-time integration (flake.nix:30):**
```nix
cp ${hello-wasm.packages.${system}.default}/lib/hello_wasm.wasm ./
```

**Transpilation (flake.nix:41-46):**
```bash
npx jco transpile hello_wasm.wasm \
  -o dist/bindings \
  --tla-compat \
  --no-nodejs-compat \
  --base64-cutoff=0 \
  --valid-lifting-optimization
```

**Runtime usage in browser (src/index.html:85-103):**
```javascript
import { greeter, $init } from './dist/bindings/hello_wasm.js';
await $init;
const greeting = greeter.hello(name);
```

## What we need from them

- **WASM Component Binary**: A WebAssembly component file named `hello_wasm.wasm` located at `${hello-wasm.packages.${system}.default}/lib/hello_wasm.wasm`
- **Exported Interface**: A `greeter` interface/namespace that exports a `hello(name: string): string` function
- **Component Model Compatibility**: The WASM must be a WIT-based component (not core module) that can be transpiled by jco with the specified flags (tla-compat, no-nodejs-compat, base64-cutoff=0)
- **No Node.js Dependencies**: The WASM component must work with browser-only shims (using @bytecodealliance/preview2-shim for browser environment)
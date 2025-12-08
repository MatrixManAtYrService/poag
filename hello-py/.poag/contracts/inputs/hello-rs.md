# Dependency: hello-rs

## How we use it

hello-py wraps the hello-rs Rust library to expose it to Python. The integration happens at multiple levels:

1. **Rust FFI binding** (src/lib.rs:4,9):
```rust
use hello_rs;

fn hello(name: &str) -> String {
    hello_rs::hello(name)
}
```

2. **Cargo dependency** (Cargo.toml:15):
```toml
hello-rs = { path = "../hello-rs" }
```

3. **Nix build integration** (flake.nix:8-11,44,58-62):
```nix
hello-rs = {
  url = "git+file:///Users/matt/src/hello-subflakes/subflake-git/hello-rs?ref=main";
  flake = false;
};
# Later copied into build directory and path rewritten
cp -r ${helloRsSrc} $out/hello-rs
sed -i 's|path = "../hello-rs"|path = "./hello-rs"|' $out/Cargo.toml
```

## What we need from them

- **A `hello(name: &str) -> String` function** in the hello-rs crate that takes a string slice and returns a formatted greeting
- **Rust library API stability**: The function signature must remain compatible as it's directly called from the PyO3 wrapper
- **Source code access**: The entire hello-rs source is copied during the Nix build process (not just compiled artifacts) since maturin builds it as part of the wheel creation
- **Cargo.lock compatibility**: Must be buildable with the Cargo.lock in hello-py's root directory
# Dependency: hello-rs
## How we use it
hello-py depends on hello-rs as its core implementation. The Rust FFI wrapper (`src/lib.rs:4,9`) imports and delegates to `hello_rs::hello()`:

```rust
use hello_rs;

#[pyfunction]
fn hello(name: &str) -> String {
    hello_rs::hello(name)
}
```

The build process (`Cargo.toml:15`) references hello-rs as a path dependency: `hello-rs = { path = "../hello-rs" }`. During Nix builds (`flake.nix:47-73`), the hello-rs source is copied into the build directory and paths are rewritten from `../hello-rs` to `./hello-rs`.

## What we need from them
- **Stable API**: The `hello(name: &str) -> String` function signature in hello-rs must remain stable
- **Source availability**: hello-rs source code must be available at build time (currently via git submodule reference in flake.nix:8-11)
- **Cargo compatibility**: hello-rs must be a valid Rust library that can be included as a Cargo path dependency
- **String handling**: hello-rs must accept any valid UTF-8 string input and return formatted output (expected format: "hello {name}")
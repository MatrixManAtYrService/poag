# Provider Contract: What hello-rs provides to hello-wasm

## Current Implementation

hello-rs provides a minimal, stable Rust library that satisfies all hello-wasm requirements:

**Public API** (src/lib.rs:9-11):
```rust
pub fn hello(name: &str) -> String {
    format!("hello {}", name)
}
```
- Signature: `hello(&str) -> String` - exactly as required
- Returns lowercase, space-separated greeting format (e.g., "hello world")
- This format is intentionally designed for downstream capitalization

**Library Configuration** (Cargo.toml:8-11):
```toml
[lib]
name = "hello_rs"
crate-type = ["rlib"]
path = "src/lib.rs"
```
- Built as `rlib` - a Rust library crate suitable for static linking
- Compatible with wasm32-wasip2 target compilation
- No external dependencies that would block WASM compilation

**Source Availability**: The entire crate is source-only (no build artifacts), making it compatible with hello-wasm's Nix flake pattern of copying source and building in-tree.

## API Stability

**Stable (WILL NOT CHANGE)**:
- Function signature: `pub fn hello(name: &str) -> String`
- Return format: lowercase "hello {name}" pattern with space separation
- Library name: `hello_rs`
- No external dependencies

**Subject to Change** (with proper notice):
- Internal implementation details (currently uses `format!` macro)
- Additional functions may be added to the public API

## Breaking Change Protocol

1. **Semantic Versioning**: Breaking changes require a major version bump (0.1.x → 0.2.0)
2. **Deprecation Period**: Where possible, deprecated APIs will remain for one minor version with deprecation warnings
3. **Communication**: Breaking changes will be documented in:
   - `CHANGELOG.md` (to be created if needed)
   - Git commit messages with `BREAKING:` prefix
   - Cargo.toml version bump
4. **Coordination**: Will notify hello-wasm maintainers before merging breaking changes to main branch

## Testing

**Contract Validation Tests** (src/lib.rs:14-22):
```rust
#[test]
fn test_hello() {
    assert_eq!(hello("claude"), "hello claude");
    assert_eq!(hello("world"), "hello world");
}
```

**Coverage**:
- ✅ Verifies function returns correctly formatted string
- ✅ Validates lowercase output
- ✅ Confirms space separation between words
- ✅ Includes doctest example that verifies public API

**Additional Guarantees**:
- All tests must pass before merging to main branch
- The test suite validates the exact format hello-wasm depends on ("hello world" not "Hello World!")
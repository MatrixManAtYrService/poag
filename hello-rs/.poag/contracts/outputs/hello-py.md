# Provider Contract: What hello-rs provides to hello-py

## Current Implementation

hello-rs provides a single public function that meets hello-py's requirements:

**Core API** (src/lib.rs:9-11):
```rust
pub fn hello(name: &str) -> String {
    format!("hello {}", name)
}
```

**Library Configuration** (Cargo.toml:8-11):
```toml
[lib]
name = "hello_rs"
crate-type = ["rlib"]
path = "src/lib.rs"
```

This configuration exports the library as `hello_rs`, which hello-py imports and wraps. The function signature `hello(name: &str) -> String` exactly matches what hello-py's FFI binding expects.

**Dependency Metadata**:
- Version: 0.1.0
- Edition: Rust 2021
- No external dependencies (Cargo.lock contains only hello-rs itself)
- Source access: Full source tree available for Nix build copying

## API Stability

**Stable (Semver Guaranteed)**:
- `pub fn hello(name: &str) -> String` - Function signature and behavior
- Library name: `hello_rs`
- Crate type: `rlib` compilation target
- No external dependencies policy (for now)

**Subject to Change** (with appropriate versioning):
- Internal implementation details (currently uses `format!` macro)
- Additional public functions may be added (non-breaking)
- Test coverage and examples

## Breaking Change Protocol

1. **Semver Compliance**: Any change to `hello(name: &str) -> String` constitutes a major version bump (0.1.0 → 0.2.0)

2. **Pre-Release Communication**:
   - Document breaking changes in a CHANGELOG.md
   - Tag releases in git with version numbers
   - hello-py should pin to specific git refs in their flake.nix

3. **Breaking Changes Include**:
   - Modifying function signature (parameter types, return type)
   - Changing library name or crate type
   - Adding external dependencies (may affect hello-py's build)
   - Changing minimum Rust edition requirements

4. **Non-Breaking Changes**:
   - Internal implementation improvements
   - Adding new public functions
   - Documentation updates
   - Test additions

## Testing

**Current Test Coverage** (src/lib.rs:13-22):
```rust
#[test]
fn test_hello() {
    assert_eq!(hello("claude"), "hello claude");
    assert_eq!(hello("world"), "hello world");
}
```

**Contract Validation**:
- Tests verify the exact string format: `"hello {name}"`
- Tests run on `cargo test` and prevent accidental behavior changes
- Any change that breaks these tests signals a potential breaking change to hello-py

**Recommended CI Checks**:
- Run `cargo test` on all commits
- Verify no new dependencies are added without version bump
- Run `cargo build --release` to ensure compilation succeeds
- Consider adding integration test that mirrors hello-py's usage pattern

## Dependencies on hello-py

None. hello-rs is a standalone library with no knowledge of its consumers. It maintains a unidirectional dependency relationship.
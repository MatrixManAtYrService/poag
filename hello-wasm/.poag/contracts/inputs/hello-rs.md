# Dependency: hello-rs

## How we use it

hello-wasm imports hello-rs as a Rust dependency and calls its core function:

**Cargo.toml:8**
```toml
hello-rs = { path = "../hello-rs" }
```

**src/lib.rs:25**
```rust
fn hello(name: String) -> String {
    // Get the base greeting from hello-rs
    let greeting = hello_rs::hello(&name);
    
    // Format the greeting: capitalize each word and add "!"
    let formatted = greeting
        .split_whitespace()
        .map(|word| { /* capitalize each word */ })
        .collect::<Vec<_>>()
        .join(" ");
    
    format!("{}!", formatted)
}
```

The flake.nix uses hello-rs as a source-only input (flake=false) and copies it into the build environment:

**flake.nix:13-14, 40-43**
```nix
hello-rs.url = "git+file:///Users/matt/src/hello-subflakes/subflake-git/hello-rs?ref=main";
hello-rs.flake = false;

# Copies hello-rs source into build
mkdir -p $out/hello-rs
cp -r ${hello-rs}/* $out/hello-rs/
sed -i 's|path = "../hello-rs"|path = "./hello-rs"|' $out/Cargo.toml
```

## What we need from them

1. **Public API**: Must export a `hello(&str) -> String` function (or similar signature) that takes a name and returns a greeting string
2. **Rust library crate**: Must be buildable as a Rust library that can be linked into wasm32-wasip2 target
3. **Format expectation**: Should return space-separated words that can be capitalized (e.g., "hello world" not "Hello World!")
4. **Source availability**: Must be available as source code (not just built artifacts) for the Nix build to copy and compile
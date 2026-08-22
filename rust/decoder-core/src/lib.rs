//! decoder-core — single source of truth for Confluence Decoder math.
//!
//! Replaces the 22 scattered Python BS/GEX implementations with one typed,
//! vectorized, lock-free core. Exposed to FastAPI via PyO3.

pub mod chain;
pub mod bindings;
pub mod gex;
pub mod greeks;
pub mod term;

#[cfg(test)]
mod tests;

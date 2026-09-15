//! TRION Protocol SDK — Rust
//!
//! Behavioral truth oracle client for Rust. Provides signal retrieval,
//! signal verification, and provenance chain inspection.
//!
//! Whitepaper Part 15.4: "cargo add trion-sdk"
//!
//! # Example
//! ```no_run
//! use trion_sdk::TrionClient;
//!
//! #[tokio::main]
//! async fn main() {
//!     let client = TrionClient::new("http://localhost:5000");
//!     let signal = client.get_signal("0x1234...").await.unwrap();
//!     println!("coherence: {}", signal.coherence);
//! }
//! ```

mod types;
mod client;
mod verify;

pub use types::*;
pub use client::TrionClient;
pub use verify::{verify_signal, VerifyResult};

/*!
 * Exponential back-off retry wrapper.
 *
 * Retries an async fallible closure up to `max_attempts` times with
 * a base delay of `base_ms` ms, doubled on each failure (capped at 60 s).
 */

use anyhow::{anyhow, Result};
use std::future::Future;
use std::time::Duration;
use tokio::time::sleep;
use tracing::warn;

pub async fn with_retry<F, Fut, T>(
    label: &str,
    max_attempts: u32,
    base_ms: u64,
    mut f: F,
) -> Result<T>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T>>,
{
    let mut delay_ms = base_ms;
    for attempt in 1..=max_attempts {
        match f().await {
            Ok(v) => return Ok(v),
            Err(e) => {
                if attempt == max_attempts {
                    return Err(anyhow!("[{}] failed after {} attempts: {}", label, max_attempts, e));
                }
                warn!("[{}] attempt {}/{} failed: {} — retrying in {}ms", label, attempt, max_attempts, e, delay_ms);
                sleep(Duration::from_millis(delay_ms)).await;
                delay_ms = (delay_ms * 2).min(60_000);
            }
        }
    }
    Err(anyhow!("[{}] unreachable", label))
}

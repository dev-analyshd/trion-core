use crate::types::{TRIONSignal, AssetType, WeightProfile};
use serde::{Deserialize, Serialize};

/// TRION SDK client for connecting to the Oracle API.
pub struct TrionClient {
    base_url: String,
    api_key: Option<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum TrionError {
    #[error("HTTP error: {0}")]
    Http(String),
    #[error("Parse error: {0}")]
    Parse(String),
    #[error("Signal not found")]
    NotFound,
}

#[derive(Serialize)]
struct GetSignalParams<'a> {
    #[serde(skip_serializing_if = "Option::is_none")]
    profile: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    asset_type: Option<&'a str>,
}

impl TrionClient {
    /// Create a new TRION client.
    /// `base_url` is the Oracle API URL (e.g., "http://localhost:5000").
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            api_key: None,
        }
    }

    /// Set the API key for authenticated requests.
    pub fn with_api_key(mut self, key: impl Into<String>) -> Self {
        self.api_key = Some(key.into());
        self
    }

    /// Get the current signal for an entity (whitepaper Part 15.4).
    pub async fn get_signal(
        &self,
        entity_id: &str,
        profile: Option<WeightProfile>,
        asset_type: Option<AssetType>,
    ) -> Result<TRIONSignal, TrionError> {
        let params = GetSignalParams {
            profile: profile.map(|p| p.as_str()),
            asset_type: asset_type.map(|a| a.as_str()),
        };
        let qs = serde_urlencoded::to_string(&params).unwrap_or_default();
        let url = format!("{}/api/v1/signal/{}?{}", self.base_url, entity_id, qs);

        let resp = self.http_get(&url).await?;
        let signal: TRIONSignal = serde_json::from_str(&resp)
            .map_err(|e| TrionError::Parse(e.to_string()))?;
        Ok(signal)
    }

    /// Get signal history for an entity.
    pub async fn get_history(
        &self,
        entity_id: &str,
        limit: u32,
    ) -> Result<Vec<TRIONSignal>, TrionError> {
        let url = format!(
            "{}/api/v1/signal_history/{}?limit={}",
            self.base_url, entity_id, limit
        );
        let resp = self.http_get(&url).await?;
        let data: serde_json::Value = serde_json::from_str(&resp)
            .map_err(|e| TrionError::Parse(e.to_string()))?;
        let signals = data.get("signals")
            .and_then(|s| serde_json::from_value(s.clone()).ok())
            .unwrap_or_default();
        Ok(signals)
    }

    /// Get Oracle health status.
    pub async fn health(&self) -> Result<serde_json::Value, TrionError> {
        let url = format!("{}/api/v1/health", self.base_url);
        let resp = self.http_get(&url).await?;
        let val: serde_json::Value = serde_json::from_str(&resp)
            .map_err(|e| TrionError::Parse(e.to_string()))?;
        Ok(val)
    }

    async fn http_get(&self, url: &str) -> Result<String, TrionError> {
        let client = reqwest::Client::new();
        let mut req = client.get(url);
        if let Some(ref key) = self.api_key {
            req = req.header("X-API-Key", key);
        }
        let resp = req.send().await
            .map_err(|e| TrionError::Http(e.to_string()))?;
        if resp.status() == 404 {
            return Err(TrionError::NotFound);
        }
        if !resp.status().is_success() {
            return Err(TrionError::Http(format!("HTTP {}", resp.status())));
        }
        let text = resp.text().await
            .map_err(|e| TrionError::Http(e.to_string()))?;
        Ok(text)
    }
}

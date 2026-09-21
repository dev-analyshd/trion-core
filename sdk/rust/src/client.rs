use reqwest::Client;
use std::time::Duration;
use tokio::sync::mpsc;

pub struct TrionClient {
    base_url: String,
    http: Client,
}

impl TrionClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            http: Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .unwrap_or_default(),
        }
    }

    pub async fn get_health(&self) -> Result<serde_json::Value, reqwest::Error> {
        let url = format!("{}/api/v1/health", self.base_url);
        self.http.get(&url).send().await?.json().await
    }

    pub async fn get_feed(&self, n: u32) -> Result<serde_json::Value, reqwest::Error> {
        let url = format!("{}/api/v1/feed?n={}", self.base_url, n);
        self.http.get(&url).send().await?.json().await
    }

    pub async fn poll_feed_once(&self) -> Result<serde_json::Value, reqwest::Error> {
        self.get_feed(50).await
    }

    pub async fn subscribe<F>(&self, mut callback: F)
    where
        F: FnMut(serde_json::Value) + Send + 'static,
    {
        let mut interval = tokio::time::interval(Duration::from_secs(10));
        loop {
            interval.tick().await;
            match self.poll_feed_once().await {
                Ok(feed) => callback(feed),
                Err(e) => eprintln!("[trion-sdk] poll error: {}", e),
            }
        }
    }

    pub fn subscribe_channel(&self, buffer: usize) -> (JoinHandle<()>, mpsc::Receiver<serde_json::Value>) {
        let (tx, rx) = mpsc::channel(buffer);
        let base_url = self.base_url.clone();
        let http = self.http.clone();
        let handle = tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(10));
            loop {
                interval.tick().await;
                let url = format!("{}/api/v1/feed?n=50", base_url);
                match http.get(&url).send().await {
                    Ok(resp) => {
                        if let Ok(json) = resp.json::<serde_json::Value>().await {
                            let _ = tx.send(json).await;
                        }
                    }
                    Err(e) => eprintln!("[trion-sdk] poll error: {}", e),
                }
            }
        });
        (handle, rx)
    }
}

use tokio::task::JoinHandle;

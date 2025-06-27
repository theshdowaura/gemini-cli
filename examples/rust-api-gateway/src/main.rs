use axum::{routing::{post, get}, Router, Json, extract::State, response::{IntoResponse, Response}};
use serde::{Deserialize, Serialize};
use std::{sync::Arc, fs};
use tokio::sync::Mutex;
use reqwest::Client;
use thiserror::Error;

#[derive(Clone)]
struct AppState {
    http: Client,
    token: Arc<Mutex<TokenStore>>, // stores access and refresh tokens
}

#[derive(Clone, Serialize, Deserialize)]
struct TokenStore {
    access_token: String,
    refresh_token: String,
    client_id: String,
    client_secret: String,
}

#[derive(Deserialize)]
struct OAuthFile {
    access_token: String,
    refresh_token: String,
    client_id: String,
    client_secret: String,
}

#[derive(Error, Debug)]
enum ApiError {
    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (axum::http::StatusCode::INTERNAL_SERVER_ERROR, self.to_string()).into_response()
    }
}

#[derive(Deserialize)]
struct PromptReq {
    prompt: String,
}

#[derive(Serialize)]
struct GeminiRequest {
    contents: Vec<Content>,
}

#[derive(Serialize)]
struct Content {
    role: String,
    parts: Vec<Part>,
}

#[derive(Serialize)]
struct Part {
    text: String,
}

async fn userinfo(State(app): State<Arc<AppState>>) -> Result<Response, ApiError> {
    let access_token = refresh_access_token(&app).await?;
    let resp = app
        .http
        .get("https://openidconnect.googleapis.com/v1/userinfo")
        .bearer_auth(access_token)
        .send()
        .await?;
    let status = axum::http::StatusCode::from_u16(resp.status().as_u16())
        .unwrap_or(axum::http::StatusCode::INTERNAL_SERVER_ERROR);
    let body = resp.json::<serde_json::Value>().await?;
    Ok((status, Json(body)).into_response())
}

async fn refresh_access_token(state: &AppState) -> Result<String, ApiError> {
    let mut token = state.token.lock().await;
    let params = [
        ("client_id", token.client_id.clone()),
        ("client_secret", token.client_secret.clone()),
        ("refresh_token", token.refresh_token.clone()),
        ("grant_type", "refresh_token".to_string()),
    ];
    let resp = state
        .http
        .post("https://oauth2.googleapis.com/token")
        .form(&params)
        .send()
        .await?;
    let json: serde_json::Value = resp.json().await?;
    if let Some(access) = json.get("access_token").and_then(|v| v.as_str()) {
        token.access_token = access.to_string();
    }
    Ok(token.access_token.clone())
}

async fn generate(
    State(app): State<Arc<AppState>>,
    Json(req): Json<PromptReq>,
) -> Result<Response, ApiError> {
    let access_token = refresh_access_token(&app).await?;

    let payload = GeminiRequest {
        contents: vec![Content {
            role: "user".into(),
            parts: vec![Part { text: req.prompt }],
        }],
    };

    let resp = app
        .http
        .post("https://generativelanguage.googleapis.com/v1/models/gemini-2.5-pro:generateContent")
        .bearer_auth(access_token)
        .json(&payload)
        .send()
        .await?;
    let status = axum::http::StatusCode::from_u16(resp.status().as_u16())
        .unwrap_or(axum::http::StatusCode::INTERNAL_SERVER_ERROR);
    let body = resp.json::<serde_json::Value>().await?;
    Ok((status, Json(body)).into_response())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let file = fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/oauth.json"))?;
    let creds: OAuthFile = serde_json::from_str(&file)?;
    let token_store = TokenStore {
        access_token: creds.access_token,
        refresh_token: creds.refresh_token,
        client_id: creds.client_id,
        client_secret: creds.client_secret,
    };
    let state = Arc::new(AppState {
        http: Client::new(),
        token: Arc::new(Mutex::new(token_store)),
    });

    let app = Router::new()
        .route("/generate", post(generate))
        .route("/userinfo", get(userinfo))
        .with_state(state);

    println!("Server running on http://localhost:3000");
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await?;
    axum::serve(listener, app).await?;
    Ok(())
}

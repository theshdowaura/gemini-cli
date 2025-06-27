# Rust API Gateway Demo

This example demonstrates how to perform Google OAuth refresh and send a request to the Gemini `gemini-2.5-pro` model using Rust. It exposes a simple HTTP endpoint that proxies user prompts to the Gemini API. The server is implemented with asynchronous Tokio tasks so each request can refresh the token and forward prompts without blocking.

## Building

```
cargo build --release
```

## Running

Copy `oauth.example.json` to `oauth.json` and fill in your Google OAuth credentials (access token, refresh token, client id and secret). Then start the gateway:

```
cargo run --release
```

Send a request using `curl`:

```
cURL request to the Gemini API (may fail if the token lacks proper scopes):
curl -X POST http://localhost:3000/generate -H 'Content-Type: application/json' -d '{"prompt":"Hello"}'

Successful connectivity test using the userinfo endpoint:
curl http://localhost:3000/userinfo
```

The server refreshes the access token before each request. The `/userinfo` route should return user information with a 200 status if the credentials are valid.

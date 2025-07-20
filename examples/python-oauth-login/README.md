# Python OAuth Login Demo

This example demonstrates how to perform Google OAuth authentication for the
Gemini API using Python. It mimics the login logic in the TypeScript
implementation and stores credentials in `~/.gemini/oauth_creds.json`.

## Running

Install the dependencies and run the script:

```bash
pip install google-auth google-auth-oauthlib requests
python oauth_login.py
```

Your browser will open to complete the authentication. Subsequent runs reuse the
cached credentials.

# Acme Auth Service

JWT-based authentication service with OAuth2 social login for the Acme web
app. This document is the architecture reference for the auth team.

## Token model

The service issues short-lived JWTs signed with rotating keys. Validation
happens in middleware on every request; expired tokens trigger a silent
refresh when the session is still alive.

## Social login

Google and GitHub OAuth are the two supported providers. The OAuth callback
exchanges the provider code for a profile, then issues a first-party JWT.

## Sessions

Sessions are tracked server-side with a sliding expiration window. Logging
out revokes the session and blacklists the active token until expiry.

## Password reset

Reset flows use single-use, time-boxed links sent by email. A succesful reset
revokes all active sesions for the user acount.

## FAQ

**Will this service support 2FA?** No. Two-factor authentication is explicitly out of scope for this service; it is owned by the platform security team.

# FAQ

Answers to the questions the support team sees most often.

## Accounts

### How do I reset my password?

Use the reset link on the sign-in page. Tokens are valid for thirty minutes.

### Can I share one account across a team?

No. Each person needs an account so audit trails stay attributable.

## Billing

### When is my invoice issued?

Invoices are issued on the first business day of each month.

### What happens when I exceed my quota?

Overage is billed per gibibyte at the rates on the pricing page; nothing is
throttled without a warning email first.

## Data

### Where is my data stored?

Primary storage lives in the region you chose at signup; encrypted backups
are replicated to a second zone in the same region.

### How do I export everything?

The export endpoint streams a signed archive per workspace.

### How long do deletions take?

Deleted objects leave the primary path immediately and the backup path
within seventy-two hours.

## Integrations

### Is there a webhook system?

Yes. Webhooks sign payloads with HMAC-SHA256 and retry with exponential
backoff for up to one day.

## Security

### Do you support SSO?

SAML and OIDC are available on the team plan and above.

# API Reference

Public endpoints for the ingestion service. All routes accept JSON and return
JSON unless noted otherwise.

## Authentication

Requests authenticate with a bearer token issued by the identity service.

### Token Acquisition

Exchange a refresh token for a short-lived access token:

```text
POST /v1/tokens
{"refresh_token": "rt_..."}
```

### Token Rotation

Access tokens expire after fifteen minutes. Rotate before expiry to avoid a
401 in the middle of a batch upload.

## Resources

### Documents

Upload, inspect, and delete source documents.

#### Upload

`POST /v1/documents` accepts multipart form data and returns a document id.

#### Inspect

`GET /v1/documents/{id}` returns parse status and extracted metadata.

#### Delete

`DELETE /v1/documents/{id}` removes the document and its derived chunks.

### Chunks

`GET /v1/documents/{id}/chunks` streams finalized chunks in document order.

## Rate Limits

| Plan | Requests per minute | Upload size |
| --- | ---: | ---: |
| free | 60 | 5 MiB |
| team | 600 | 50 MiB |
| enterprise | 6000 | 500 MiB |

## Errors

Errors return a JSON envelope with `code`, `message`, and `request_id`.

## Versioning

The API is versioned in the path. Breaking changes ship under a new version
prefix with a twelve-month deprecation window.

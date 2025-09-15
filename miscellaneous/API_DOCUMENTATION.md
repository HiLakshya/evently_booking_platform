# API Documentation

The Evently Booking Platform exposes a RESTful API built with FastAPI, supporting user and admin operations.

Live Swagger UI (production): [https://evently-booking-platform-latest.onrender.com/docs](https://evently-booking-platform-latest.onrender.com/docs)

Base URL (development):

```

[http://localhost:3000](http://localhost:3000)

```

Current version:

```

/api/v1

```

---

## Authentication

Evently uses **JWT (JSON Web Tokens)** for authentication.

### Flow

1. Register → Get access token.
2. Login → Get access token.
3. Use token in all requests:

```

Authorization: Bearer \<access_token>

```

Tokens expire in **1 hour**.

---

## User Authentication Endpoints

### Register

`POST /api/v1/auth/register`

Request:

```json
{
  "email": "john@example.com",
  "password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe"
}
```

Response (201):

```json
{
  "access_token": "<jwt_token>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "email": "john@example.com",
    "is_admin": false,
    "is_active": true
  }
}
```

---

### Login

`POST /api/v1/auth/login`

Request:

```json
{
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

Response:

```json
{
  "access_token": "<jwt_token>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## Events

### List Events

`GET /api/v1/events`

Query Parameters:

- `page` (int, default: 1)
- `size` (int, default: 20, max: 100)
- `search` (string) – Search by name/venue
- `date_from`, `date_to` (ISO 8601 date strings)
- `min_price`, `max_price` (float)
- `available_only` (bool, default: true)
- `active_only` (bool, default: true)

---

### Create Event (admin)

`POST /api/v1/events`

Request:

```json
{
  "name": "Music Festival 2025",
  "description": "Outdoor concert event",
  "venue": "Central Park",
  "event_date": "2025-07-15T19:00:00Z",
  "total_capacity": 5000,
  "price": 89.99,
  "has_seat_selection": true
}
```

---

### Event Details

`GET /api/v1/events/{event_id}`

### Update Event (admin)

`PUT /api/v1/events/{event_id}`

### Delete Event (admin)

`DELETE /api/v1/events/{event_id}`

---

## Bookings

### Create Booking

`POST /api/v1/bookings`

Request:

```json
{
  "event_id": "uuid",
  "quantity": 2,
  "seat_ids": ["seat-uuid1", "seat-uuid2"]
}
```

_(`seat_ids` optional if event doesn’t use seat selection.)_

---

### Get User Bookings

`GET /api/v1/bookings`

### Booking Details

`GET /api/v1/bookings/{booking_id}`

### Cancel Booking

`DELETE /api/v1/bookings/{booking_id}`

---

## Seats

### Get Seat Map

`GET /api/v1/seats/{event_id}`

### Bulk Create Seats (admin)

`POST /api/v1/seats/{event_id}/bulk-create`

### Hold Seats

`POST /api/v1/seats/hold`

### Release Seats

`POST /api/v1/seats/release`

---

## Waitlist

### Join Waitlist

`POST /api/v1/waitlist`

Request:

```json
{
  "event_id": "uuid",
  "requested_quantity": 2
}
```

### Get My Waitlist

`GET /api/v1/waitlist`

### Leave Waitlist

`DELETE /api/v1/waitlist/{waitlist_id}`

---

## Analytics (admin)

### Dashboard

`GET /api/v1/admin/analytics/dashboard`

### Booking Metrics

`GET /api/v1/admin/analytics/bookings`

### Event Performance

`GET /api/v1/admin/analytics/events`

### Revenue Reports

`GET /api/v1/admin/analytics/revenue`

---

## Advanced Features (admin)

- **Trends** → `GET /api/v1/advanced/analytics/trends`
- **User Behavior** → `GET /api/v1/advanced/analytics/user-behavior`
- **Predictions** → `GET /api/v1/advanced/analytics/predictions`
- **Event Recommendations** → `POST /api/v1/advanced/events/recommendations`
- **Seat Recommendations** → `POST /api/v1/advanced/seats/recommendations`
- **Dynamic Pricing Update** →

  - `POST /api/v1/advanced/pricing/update/{event_id}`
  - `POST /api/v1/advanced/pricing/update-all`

---

## Health and Monitoring

- `GET /` → Basic API info
- `GET /health` → Basic health check
- `GET /health/detailed` → DB + Redis status
- `GET /metrics` → App metrics

---

## Error Handling

Standard error response format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {},
    "suggestions": []
  }
}
```

### Common Codes

| Code                        | Status | Meaning                   |
| --------------------------- | ------ | ------------------------- |
| `VALIDATION_ERROR`          | 400    | Invalid input             |
| `BOOKING_CAPACITY_EXCEEDED` | 400    | Event is sold out         |
| `AUTHENTICATION_REQUIRED`   | 401    | Missing token             |
| `INVALID_TOKEN`             | 401    | Expired or invalid token  |
| `INSUFFICIENT_PERMISSIONS`  | 403    | Admin privileges required |
| `EVENT_NOT_FOUND`           | 404    | Event not found           |
| `SEAT_ALREADY_TAKEN`        | 409    | Seat unavailable          |
| `RATE_LIMIT_EXCEEDED`       | 429    | Too many requests         |
| `INTERNAL_SERVER_ERROR`     | 500    | Unexpected server error   |

---

## 📌 Postman Collection

A Postman collection is provided:

- [`postman_collection.json`](./postman_collection.json) → Ready to import
- Includes all endpoints with sample data
- Handles token extraction automatically

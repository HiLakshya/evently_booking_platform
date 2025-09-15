# Admin Authentication Guide

This document explains how to authenticate as an admin user and how admin authorization works in the Evently Booking Platform.

The platform provides role-based access control (RBAC):

Live Swagger UI (production): [https://evently-booking-platform-latest.onrender.com/docs](https://evently-booking-platform-latest.onrender.com/docs)

- Regular users: browse events, create and manage bookings
- Admin users: all user privileges plus event management, analytics, and admin-only APIs

Admin status is controlled by the `is_admin` field on the `User` model.

---

## Methods to Create Admin Users

### 1. Using the provided script (recommended)

Run the admin creation script:

```bash
cd miscellaneous/evently-booking-platform
python create_admin_user.py
```

Follow the prompts to set up email, name, and password.

To **list existing admin users**:

```bash
python create_admin_user.py list
```

---

### 2. Via API and database update

1. Register a user:

```bash
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "AdminPassword123!",
    "first_name": "Admin",
    "last_name": "User"
  }'
```

2. Update user to admin via the api route

---

### 3. Direct database insert

Insert directly into the database (replace password hash):

```sql
INSERT INTO users (id, email, password_hash, first_name, last_name, is_admin, is_active, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'admin@example.com',
    '$2b$12$<bcrypt_hash_here>', -- hashed password
    'Admin',
    'User',
    true,
    true,
    NOW(),
    NOW()
);
```

---

## Authenticating as Admin

1. **Login to get a token**:

```bash
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "AdminPassword123!"
  }'
```

Response:

```json
{
  "access_token": "<jwt_token_here>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "email": "admin@example.com",
    "is_admin": true
  }
}
```

2. **Use the token for admin requests**:

```bash
curl -X POST http://localhost:3000/api/v1/events \
  -H "Authorization: Bearer <jwt_token_here>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sample Concert",
    "venue": "Test Venue",
    "event_date": "2025-12-31T20:00:00Z",
    "total_capacity": 100,
    "price": 50.00,
    "has_seat_selection": false
  }'
```

---

## Admin-only Endpoints

- **Event Management**

  - `POST /api/v1/events` – Create event
  - `PUT /api/v1/events/{id}` – Update event
  - `DELETE /api/v1/events/{id}` – Delete event

- **Seat Management**

  - `POST /api/v1/seats/{event_id}/bulk-create` – Bulk seat creation

- **Analytics**

  - `GET /api/v1/admin/analytics/dashboard` – Dashboard
  - `GET /api/v1/admin/analytics/bookings` – Booking metrics
  - `GET /api/v1/admin/analytics/capacity` – Capacity utilization
  - `GET /api/v1/admin/analytics/revenue` – Revenue reports

- **Advanced Features**

  - `GET /api/v1/advanced/analytics/*` – Advanced analytics
  - `POST /api/v1/advanced/pricing/update/{event_id}` – Dynamic pricing

---

## Testing Admin Access

### Using Postman

1. Import the Postman collection ([`postman_collection.json`](./postman_collection.json)).
2. Use the "Login" request to get a token.
3. Run any admin request — the token will be automatically injected.

### Using cURL

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"AdminPassword123!"}' | jq -r '.access_token')

curl -X GET http://localhost:3000/api/v1/admin/analytics/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

### Using Python

```python
import requests

login = requests.post("http://localhost:3000/api/v1/auth/login", json={
    "email": "admin@example.com",
    "password": "AdminPassword123!"
})
token = login.json()["access_token"]

resp = requests.get("http://localhost:3000/api/v1/admin/analytics/dashboard",
    headers={"Authorization": f"Bearer {token}"})
print(resp.json())
```

---

## Troubleshooting

- **403 Forbidden** → Ensure `is_admin = true` in DB and token is valid.
- **401 Unauthorized** → Token expired; login again.
- **User Not Found** → Check email in DB and `is_active = true`.

---

## Security Best Practices

- Use **strong passwords** and rotate regularly.
- Enable **HTTPS** in production.
- Tokens expire in **1 hour** by default.

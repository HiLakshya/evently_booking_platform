"""
API documentation examples for OpenAPI/Swagger.
"""

from typing import Dict, Any

# Authentication Examples
AUTHENTICATION_EXAMPLES: Dict[str, Any] = {
    "user_registration": {
        "summary": "User Registration Example",
        "description": "Register a new user account",
        "value": {
            "email": "john.doe@example.com",
            "password": "SecurePassword123!",
            "first_name": "John",
            "last_name": "Doe"
        }
    },
    "user_login": {
        "summary": "User Login Example",
        "description": "Login with existing credentials",
        "value": {
            "email": "john.doe@example.com",
            "password": "SecurePassword123!"
        }
    },
    "admin_login": {
        "summary": "Admin Login Example",
        "description": "Login with admin credentials",
        "value": {
            "email": "admin@evently.com",
            "password": "AdminPassword123!"
        }
    }
}

# Event Examples
EVENT_EXAMPLES: Dict[str, Any] = {
    "create_event": {
        "summary": "Create Concert Event",
        "description": "Create a new concert event with seat selection",
        "value": {
            "name": "Summer Music Festival 2024",
            "description": "Join us for an unforgettable night of music featuring top artists from around the world. Experience live performances in a stunning outdoor venue.",
            "venue": "Central Park Amphitheater",
            "event_date": "2024-07-15T19:00:00Z",
            "total_capacity": 5000,
            "price": 89.99,
            "has_seat_selection": True
        }
    },
    "create_conference": {
        "summary": "Create Conference Event",
        "description": "Create a business conference without seat selection",
        "value": {
            "name": "Tech Innovation Summit 2024",
            "description": "Discover the latest trends in technology and innovation. Network with industry leaders and learn from expert speakers.",
            "venue": "Convention Center Hall A",
            "event_date": "2024-09-20T09:00:00Z",
            "total_capacity": 500,
            "price": 299.00,
            "has_seat_selection": False
        }
    },
    "update_event": {
        "summary": "Update Event Details",
        "description": "Update event information",
        "value": {
            "name": "Summer Music Festival 2024 - Updated",
            "description": "Updated description with new artist lineup",
            "price": 99.99
        }
    }
}

# Booking Examples
BOOKING_EXAMPLES: Dict[str, Any] = {
    "create_booking": {
        "summary": "Book Event Tickets",
        "description": "Book tickets for an event",
        "value": {
            "event_id": "123e4567-e89b-12d3-a456-426614174000",
            "quantity": 2,
            "seat_ids": [
                "seat-123e4567-e89b-12d3-a456-426614174001",
                "seat-123e4567-e89b-12d3-a456-426614174002"
            ]
        }
    },
    "create_general_booking": {
        "summary": "Book General Admission",
        "description": "Book general admission tickets without seat selection",
        "value": {
            "event_id": "123e4567-e89b-12d3-a456-426614174000",
            "quantity": 3
        }
    }
}

# Waitlist Examples
WAITLIST_EXAMPLES: Dict[str, Any] = {
    "join_waitlist": {
        "summary": "Join Event Waitlist",
        "description": "Join waitlist for a sold-out event",
        "value": {
            "event_id": "123e4567-e89b-12d3-a456-426614174000",
            "requested_quantity": 2
        }
    }
}

# Seat Examples
SEAT_EXAMPLES: Dict[str, Any] = {
    "create_seats": {
        "summary": "Create Venue Seats",
        "description": "Create seats for an event venue",
        "value": {
            "event_id": "123e4567-e89b-12d3-a456-426614174000",
            "seats": [
                {
                    "section": "VIP",
                    "row": "A",
                    "number": "1",
                    "price": 150.00
                },
                {
                    "section": "VIP",
                    "row": "A",
                    "number": "2",
                    "price": 150.00
                },
                {
                    "section": "General",
                    "row": "B",
                    "number": "1",
                    "price": 89.99
                }
            ]
        }
    }
}

# User Profile Examples
USER_EXAMPLES: Dict[str, Any] = {
    "update_profile": {
        "summary": "Update User Profile",
        "description": "Update user profile information",
        "value": {
            "first_name": "John",
            "last_name": "Smith"
        }
    },
    "change_password": {
        "summary": "Change Password",
        "description": "Change user password",
        "value": {
            "current_password": "OldPassword123!",
            "new_password": "NewSecurePassword456!"
        }
    }
}

# Combine all examples
API_EXAMPLES: Dict[str, Dict[str, Any]] = {
    "authentication": AUTHENTICATION_EXAMPLES,
    "events": EVENT_EXAMPLES,
    "bookings": BOOKING_EXAMPLES,
    "waitlist": WAITLIST_EXAMPLES,
    "seats": SEAT_EXAMPLES,
    "users": USER_EXAMPLES
}
"""Main entry point for the Evently Booking Platform."""

from evently_booking_platform.main import app

def main():
    """Main function for CLI entry point."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)

if __name__ == "__main__":
    main()

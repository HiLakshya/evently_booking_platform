#!/usr/bin/env python3
"""
Script to create an admin user for the Evently Booking Platform.
"""

import asyncio
import sys
import os
from getpass import getpass

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from evently_booking_platform.database import init_database, get_db
from evently_booking_platform.models.user import User
from evently_booking_platform.utils.auth import get_password_hash


async def create_admin_user():
    """Create an admin user interactively."""
    print("🔧 Evently Booking Platform - Admin User Creation")
    print("=" * 50)
    
    # Get user input
    email = input("Enter admin email: ").strip()
    if not email:
        print("❌ Email is required!")
        return
    
    first_name = input("Enter first name: ").strip()
    if not first_name:
        print("❌ First name is required!")
        return
    
    last_name = input("Enter last name: ").strip()
    if not last_name:
        print("❌ Last name is required!")
        return
    
    password = getpass("Enter password: ").strip()
    if not password:
        print("❌ Password is required!")
        return
    
    confirm_password = getpass("Confirm password: ").strip()
    if password != confirm_password:
        print("❌ Passwords do not match!")
        return
    
    try:
        # Initialize database
        print("\n🔄 Initializing database connection...")
        await init_database()
        
        # Create admin user
        print("🔄 Creating admin user...")
        
        async for db in get_db():
            # Check if user already exists
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.email == email))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                print(f"❌ User with email {email} already exists!")
                
                # Ask if they want to make existing user admin
                make_admin = input("Make existing user an admin? (y/N): ").strip().lower()
                if make_admin == 'y':
                    existing_user.is_admin = True
                    await db.commit()
                    print(f"✅ User {email} is now an admin!")
                return
            
            # Create new admin user
            admin_user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password_hash=get_password_hash(password),
                is_admin=True,
                is_active=True
            )
            
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)
            
            print(f"✅ Admin user created successfully!")
            print(f"   Email: {admin_user.email}")
            print(f"   Name: {admin_user.full_name}")
            print(f"   Admin: {admin_user.is_admin}")
            print(f"   Active: {admin_user.is_active}")
            print(f"   ID: {admin_user.id}")
            
            break
            
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        return


async def list_admin_users():
    """List all admin users."""
    print("👥 Current Admin Users")
    print("=" * 30)
    
    try:
        await init_database()
        
        async for db in get_db():
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(User.is_admin == True)
            )
            admin_users = result.scalars().all()
            
            if not admin_users:
                print("No admin users found.")
            else:
                for user in admin_users:
                    status = "Active" if user.is_active else "Inactive"
                    print(f"📧 {user.email}")
                    print(f"   Name: {user.full_name}")
                    print(f"   Status: {status}")
                    print(f"   ID: {user.id}")
                    print()
            
            break
            
    except Exception as e:
        print(f"❌ Error listing admin users: {e}")


async def main():
    """Main function."""
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        await list_admin_users()
    else:
        await create_admin_user()


if __name__ == "__main__":
    print("Usage:")
    print("  python create_admin_user.py        # Create new admin user")
    print("  python create_admin_user.py list   # List existing admin users")
    print()
    
    asyncio.run(main())
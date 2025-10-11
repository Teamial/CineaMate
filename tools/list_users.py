#!/usr/bin/env python3
"""List all users in the database"""

from backend.database import SessionLocal
from backend.models import User, Rating

db = SessionLocal()

print("\n📋 Users in Database:")
print("=" * 50)

users = db.query(User).all()

if not users:
    print("⚠️  No users found!")
    print("\nCreate a user first:")
    print("  python3 -c \"from backend.models import User; from backend.database import SessionLocal; from backend.auth import get_password_hash; db = SessionLocal(); user = User(username='testuser', email='test@example.com', hashed_password=get_password_hash('password123')); db.add(user); db.commit(); print('User created!')\"")
else:
    for user in users:
        rating_count = db.query(Rating).filter(Rating.user_id == user.id).count()
        print(f"\n👤 {user.username}")
        print(f"   ID: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Ratings: {rating_count}")
        print(f"   Created: {user.created_at}")

print("\n" + "=" * 50)
print(f"Total users: {len(users)}")
print()

db.close()

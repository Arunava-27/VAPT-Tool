"""
Database initialization script

Creates tables and seeds initial data (tenants, roles, superuser)
"""

import sys
import os
from sqlalchemy.orm import Session
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine, SessionLocal, Base
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role, SYSTEM_ROLES
from app.core.security import hash_password
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize database with tables and seed data"""
    
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Tables created")
    
    db: Session = SessionLocal()
    
    try:
        # Check if default tenant exists
        default_tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        
        if not default_tenant:
            logger.info("Creating default tenant...")
            default_tenant = Tenant(
                name="Default Organization",
                slug="default",
                contact_email="admin@vapt-platform.local",
                schema_name="default",
                is_active=True
            )
            db.add(default_tenant)
            db.commit()
            db.refresh(default_tenant)
            logger.info(f"✓ Default tenant created: {default_tenant.id}")
        else:
            logger.info(f"Default tenant already exists: {default_tenant.id}")
        
        # Create system roles
        logger.info("Creating system roles...")
        roles_created = 0
        
        for role_slug, role_data in SYSTEM_ROLES.items():
            existing_role = db.query(Role).filter(Role.slug == role_slug).first()
            
            if not existing_role:
                role = Role(
                    name=role_data["name"],
                    slug=role_data["slug"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    is_system_role=True,
                    is_active=True
                )
                db.add(role)
                roles_created += 1
        
        db.commit()
        logger.info(f"✓ Created {roles_created} system roles")
        
        # Create superuser if SUPERUSER_EMAIL env var is explicitly set
        # (e.g. for automated/CI deployments). In interactive deployments
        # the first-run setup wizard (/api/v1/setup/init) handles this.
        superuser_email = os.getenv("SUPERUSER_EMAIL", "")
        superuser_password = os.getenv("SUPERUSER_PASSWORD", "")

        if superuser_email and superuser_password:
            existing_superuser = db.query(User).filter(User.is_superuser == True).first()  # noqa
            if not existing_superuser:
                logger.info("Creating superuser from environment variables...")
                super_admin_role = db.query(Role).filter(Role.slug == "super_admin").first()
                superuser = User(
                    email=superuser_email,
                    hashed_password=hash_password(superuser_password),
                    full_name="Super Administrator",
                    is_active=True,
                    is_superuser=True,
                    is_verified=True,
                    tenant_id=default_tenant.id
                )
                if super_admin_role:
                    superuser.roles.append(super_admin_role)
                db.add(superuser)
                db.commit()
                logger.info(f"✓ Superuser created: {superuser_email}")
                logger.info("  ⚠️  Please change the superuser password after first login!")
            else:
                logger.info("Superuser already exists — skipping.")
        else:
            logger.info("No SUPERUSER_EMAIL set — skipping superuser creation.")
            logger.info("Visit the platform URL to complete first-run setup.")

        logger.info("\n" + "="*60)
        logger.info("Database initialization completed successfully!")
        logger.info("="*60)
    
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()


if __name__ == "__main__":
    init_database()

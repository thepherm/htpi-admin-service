"""Main entry point for HTPI Admin Service"""

import asyncio
import logging

from app.config import get_settings
from app.services import NATSService, AuthService
from app.controllers import AdminController, OrganizationController, UserController

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
settings = get_settings()


async def create_super_admin(nats_service: NATSService, auth_service: AuthService):
    """Create default super admin if none exists"""
    try:
        # Check if any super admin exists
        response = await nats_service.request("db.find_one", {
            'collection': 'admin_users',
            'filter': {'is_super_admin': True, 'is_active': True}
        })
        
        if not response.get('data'):
            logger.info("Creating default super admin...")
            
            # Create super admin
            admin_data = {
                'email': settings.SUPER_ADMIN_EMAIL,
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': 'super_admin',
                'is_super_admin': True,
                'is_active': True,
                'password_hash': auth_service.hash_password(settings.DEFAULT_ADMIN_PASSWORD)
            }
            
            await nats_service.request("db.create", {
                'collection': 'admin_users',
                'document': admin_data
            })
            
            logger.info(f"Created super admin: {settings.SUPER_ADMIN_EMAIL}")
            logger.warning(f"Default password: {settings.DEFAULT_ADMIN_PASSWORD}")
            logger.warning("Please change the password immediately!")
            
    except Exception as e:
        logger.error(f"Error creating super admin: {e}")


async def main():
    """Main application entry point"""
    # Initialize services
    nats_service = NATSService()
    auth_service = AuthService(nats_service)
    
    # Initialize controllers
    admin_controller = AdminController(nats_service, auth_service)
    org_controller = OrganizationController(nats_service)
    user_controller = UserController(nats_service, auth_service)
    
    try:
        # Connect to NATS
        await nats_service.connect()
        
        # Create super admin if needed
        await create_super_admin(nats_service, auth_service)
        
        # Setup subscriptions
        await admin_controller.setup_subscriptions()
        await org_controller.setup_subscriptions()
        await user_controller.setup_subscriptions()
        
        # Setup audit log subscription
        async def handle_audit_create(data, msg):
            try:
                await nats_service.request("db.create", {
                    'collection': 'audit_logs',
                    'document': data
                })
            except Exception as e:
                logger.error(f"Error creating audit log: {e}")
                
        await nats_service.subscribe("audit.create", handle_audit_create)
        
        logger.info(f"{settings.SERVICE_NAME} started successfully")
        
        # Keep service running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Service error: {e}")
    finally:
        await nats_service.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
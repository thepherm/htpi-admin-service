"""Authentication and authorization service"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
import bcrypt

from app.config import get_settings
from app.models import AdminUser, AdminSession

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """Handle authentication and authorization"""
    
    def __init__(self, nats_service):
        self.nats = nats_service
        
    def hash_password(self, password: str) -> str:
        """Hash a password"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        
    def generate_token(self, admin_user: AdminUser) -> str:
        """Generate JWT token for admin"""
        payload = {
            'admin_id': admin_user.id,
            'email': admin_user.email,
            'role': admin_user.role,
            'permissions': admin_user.permissions,
            'is_super_admin': admin_user.is_super_admin,
            'exp': datetime.utcnow() + timedelta(seconds=settings.JWT_EXPIRATION_DELTA),
            'iat': datetime.utcnow()
        }
        
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
            
    async def authenticate_admin(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate admin user"""
        try:
            # Get admin from database
            response = await self.nats.request("admin.get_by_email", {
                'email': email
            })
            
            if not response.get('success'):
                return None
                
            admin_data = response.get('data')
            if not admin_data:
                return None
                
            # Check if admin is active
            if not admin_data.get('is_active'):
                logger.warning(f"Inactive admin login attempt: {email}")
                return None
                
            # Check if account is locked
            locked_until = admin_data.get('locked_until')
            if locked_until and datetime.fromisoformat(locked_until) > datetime.utcnow():
                logger.warning(f"Locked admin login attempt: {email}")
                return None
                
            # Verify password
            if not self.verify_password(password, admin_data.get('password_hash', '')):
                # Update failed login attempts
                await self.nats.publish("admin.update_login_attempts", {
                    'admin_id': admin_data['id'],
                    'increment': True
                })
                return None
                
            # Reset failed attempts on successful login
            await self.nats.publish("admin.update_login_attempts", {
                'admin_id': admin_data['id'],
                'reset': True
            })
            
            # Update last login
            await self.nats.publish("admin.update_last_login", {
                'admin_id': admin_data['id'],
                'last_login': datetime.utcnow().isoformat()
            })
            
            # Create admin user object
            admin_user = AdminUser(**admin_data)
            
            # Generate token
            token = self.generate_token(admin_user)
            
            return {
                'token': token,
                'admin': admin_user.dict(exclude={'password_hash', 'mfa_secret'})
            }
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
            
    async def create_session(self, admin_id: str, token: str, ip_address: str, user_agent: str) -> Optional[AdminSession]:
        """Create admin session"""
        try:
            session = AdminSession(
                id=f"session_{datetime.utcnow().timestamp()}",
                admin_id=admin_id,
                token=token,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=datetime.utcnow() + timedelta(seconds=settings.JWT_EXPIRATION_DELTA)
            )
            
            # Store session
            response = await self.nats.request("admin.create_session", session.dict())
            
            if response.get('success'):
                return session
                
            return None
            
        except Exception as e:
            logger.error(f"Session creation error: {e}")
            return None
            
    async def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate admin session"""
        try:
            # Verify token
            payload = self.verify_token(token)
            if not payload:
                return None
                
            # Check if session exists and is active
            response = await self.nats.request("admin.get_session", {
                'token': token
            })
            
            if not response.get('success'):
                return None
                
            session = response.get('data')
            if not session or not session.get('is_active'):
                return None
                
            # Update last activity
            await self.nats.publish("admin.update_session_activity", {
                'session_id': session['id'],
                'last_activity': datetime.utcnow().isoformat()
            })
            
            return payload
            
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return None
            
    async def logout(self, token: str):
        """Logout admin (invalidate session)"""
        try:
            await self.nats.publish("admin.invalidate_session", {
                'token': token
            })
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            
    def has_permission(self, admin_data: Dict[str, Any], permission: str) -> bool:
        """Check if admin has specific permission"""
        if admin_data.get('is_super_admin'):
            return True
            
        permissions = admin_data.get('permissions', [])
        return permission in permissions
        
    def can_access_org(self, admin_data: Dict[str, Any], org_id: str) -> bool:
        """Check if admin can access organization"""
        if admin_data.get('is_super_admin'):
            return True
            
        org_ids = admin_data.get('org_ids', [])
        return org_id in org_ids or len(org_ids) == 0  # Empty means all orgs
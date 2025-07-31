"""Admin management controller"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.models import AdminUser, AdminRole, AuditLog
from app.services import AuthService

logger = logging.getLogger(__name__)


class AdminController:
    """Handle admin user operations"""
    
    def __init__(self, nats_service, auth_service: AuthService):
        self.nats = nats_service
        self.auth = auth_service
        
    async def handle_create_admin(self, data: Dict[str, Any], msg) -> None:
        """Handle create admin request"""
        try:
            # Validate requester permissions
            requester = data.get('requester', {})
            if not requester.get('is_super_admin'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Only super admins can create admin users'
                    }
                }).encode())
                return
                
            # Create admin user
            admin_data = data.get('admin', {})
            
            # Hash password
            password = admin_data.pop('password', None)
            if password:
                admin_data['password_hash'] = self.auth.hash_password(password)
                
            # Create admin object
            admin = AdminUser(**admin_data)
            admin.created_by = requester.get('admin_id')
            
            # Check if email already exists
            existing = await self.nats.request("db.find_one", {
                'collection': 'admin_users',
                'filter': {'email': admin.email}
            })
            
            if existing.get('data'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'ALREADY_EXISTS',
                        'message': 'Admin with this email already exists'
                    }
                }).encode())
                return
                
            # Save to database
            response = await self.nats.request("db.create", {
                'collection': 'admin_users',
                'document': admin.dict(exclude={'password_hash'})
            })
            
            if response.get('success'):
                created_admin = response.get('data')
                
                # Audit log
                await self._create_audit_log(
                    admin_id=requester.get('admin_id'),
                    action='admin.create',
                    resource_type='admin_user',
                    resource_id=created_admin.get('id'),
                    new_values=created_admin,
                    success=True,
                    request_data=data
                )
                
                await msg.respond(json.dumps({
                    'success': True,
                    'data': created_admin
                }).encode())
            else:
                await msg.respond(json.dumps(response).encode())
                
        except Exception as e:
            logger.error(f"Error creating admin: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_update_admin(self, data: Dict[str, Any], msg) -> None:
        """Handle update admin request"""
        try:
            admin_id = data.get('admin_id')
            updates = data.get('updates', {})
            requester = data.get('requester', {})
            
            # Check permissions
            if not requester.get('is_super_admin') and requester.get('admin_id') != admin_id:
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions'
                    }
                }).encode())
                return
                
            # Get current admin
            current = await self.nats.request("db.find_by_id", {
                'collection': 'admin_users',
                'id': admin_id
            })
            
            if not current.get('success'):
                await msg.respond(json.dumps(current).encode())
                return
                
            old_values = current.get('data')
            
            # Handle password update
            if 'password' in updates:
                password = updates.pop('password')
                updates['password_hash'] = self.auth.hash_password(password)
                
            # Update admin
            updates['updated_at'] = datetime.utcnow().isoformat()
            updates['updated_by'] = requester.get('admin_id')
            
            response = await self.nats.request("db.update", {
                'collection': 'admin_users',
                'id': admin_id,
                'updates': updates
            })
            
            if response.get('success'):
                # Audit log
                await self._create_audit_log(
                    admin_id=requester.get('admin_id'),
                    action='admin.update',
                    resource_type='admin_user',
                    resource_id=admin_id,
                    old_values=old_values,
                    new_values=updates,
                    success=True,
                    request_data=data
                )
                
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error updating admin: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_delete_admin(self, data: Dict[str, Any], msg) -> None:
        """Handle delete admin request"""
        try:
            admin_id = data.get('admin_id')
            requester = data.get('requester', {})
            
            # Only super admins can delete
            if not requester.get('is_super_admin'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Only super admins can delete admin users'
                    }
                }).encode())
                return
                
            # Prevent self-deletion
            if requester.get('admin_id') == admin_id:
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'INVALID_REQUEST',
                        'message': 'Cannot delete your own admin account'
                    }
                }).encode())
                return
                
            # Soft delete
            response = await self.nats.request("db.update", {
                'collection': 'admin_users',
                'id': admin_id,
                'updates': {
                    'is_active': False,
                    'deleted_at': datetime.utcnow().isoformat(),
                    'deleted_by': requester.get('admin_id')
                }
            })
            
            if response.get('success'):
                # Invalidate all sessions
                await self.nats.publish("admin.invalidate_all_sessions", {
                    'admin_id': admin_id
                })
                
                # Audit log
                await self._create_audit_log(
                    admin_id=requester.get('admin_id'),
                    action='admin.delete',
                    resource_type='admin_user',
                    resource_id=admin_id,
                    success=True,
                    request_data=data
                )
                
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error deleting admin: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_list_admins(self, data: Dict[str, Any], msg) -> None:
        """Handle list admins request"""
        try:
            requester = data.get('requester', {})
            
            # Check permissions
            if not requester.get('is_super_admin'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Only super admins can list admin users'
                    }
                }).encode())
                return
                
            # Build filter
            filter_params = {'is_active': True}
            
            if data.get('role'):
                filter_params['role'] = data['role']
                
            # List admins
            response = await self.nats.request("db.find", {
                'collection': 'admin_users',
                'filter': filter_params,
                'projection': {
                    'password_hash': 0,
                    'mfa_secret': 0
                },
                'sort': {'created_at': -1},
                'limit': data.get('limit', 50),
                'skip': data.get('skip', 0)
            })
            
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error listing admins: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_get_admin_by_email(self, data: Dict[str, Any], msg) -> None:
        """Handle get admin by email request"""
        try:
            email = data.get('email')
            
            response = await self.nats.request("db.find_one", {
                'collection': 'admin_users',
                'filter': {'email': email, 'is_active': True}
            })
            
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error getting admin by email: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def _create_audit_log(self, **kwargs):
        """Create audit log entry"""
        try:
            audit_log = AuditLog(
                admin_id=kwargs.get('admin_id'),
                action=kwargs.get('action'),
                resource_type=kwargs.get('resource_type'),
                resource_id=kwargs.get('resource_id'),
                org_id=kwargs.get('org_id'),
                old_values=kwargs.get('old_values'),
                new_values=kwargs.get('new_values'),
                success=kwargs.get('success', True),
                error_message=kwargs.get('error_message'),
                ip_address=kwargs.get('request_data', {}).get('ip_address', 'unknown'),
                user_agent=kwargs.get('request_data', {}).get('user_agent', 'unknown'),
                request_method=kwargs.get('request_data', {}).get('method', 'NATS'),
                request_path=kwargs.get('request_data', {}).get('path', kwargs.get('action'))
            )
            
            await self.nats.publish("audit.create", audit_log.dict())
            
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
            
    async def setup_subscriptions(self):
        """Setup NATS subscriptions"""
        await self.nats.subscribe("admin.create", self.handle_create_admin)
        await self.nats.subscribe("admin.update", self.handle_update_admin)
        await self.nats.subscribe("admin.delete", self.handle_delete_admin)
        await self.nats.subscribe("admin.list", self.handle_list_admins)
        await self.nats.subscribe("admin.get_by_email", self.handle_get_admin_by_email)
"""User management controller"""

import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any

from app.models import User, UserInvite, UserRole, UserStatus
from app.services import AuthService

logger = logging.getLogger(__name__)


class UserController:
    """Handle user operations"""
    
    def __init__(self, nats_service, auth_service: AuthService):
        self.nats = nats_service
        self.auth = auth_service
        
    async def handle_create_user(self, data: Dict[str, Any], msg) -> None:
        """Handle create user request"""
        try:
            requester = data.get('requester', {})
            user_data = data.get('user', {})
            org_id = user_data.get('org_id')
            
            # Check permissions
            if not self._has_permission(requester, 'user:create', org_id):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to create user'
                    }
                }).encode())
                return
                
            # Create user
            password = user_data.pop('password', None)
            if password:
                user_data['password_hash'] = self.auth.hash_password(password)
                
            user = User(**user_data)
            user.created_by = requester.get('admin_id') or requester.get('user_id')
            
            # Check if email already exists in org
            existing = await self.nats.request("db.find_one", {
                'collection': 'users',
                'filter': {
                    'email': user.email,
                    'org_id': org_id
                }
            })
            
            if existing.get('data'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'ALREADY_EXISTS',
                        'message': 'User with this email already exists in organization'
                    }
                }).encode())
                return
                
            # Check organization limits
            org_response = await self.nats.request("db.find_by_id", {
                'collection': 'organizations',
                'id': org_id
            })
            
            if org_response.get('success'):
                org = org_response.get('data', {})
                if org.get('current_users', 0) >= org.get('max_users', 10):
                    await msg.respond(json.dumps({
                        'success': False,
                        'error': {
                            'code': 'LIMIT_EXCEEDED',
                            'message': 'Organization has reached maximum user limit'
                        }
                    }).encode())
                    return
                    
            # Save user
            response = await self.nats.request("db.create", {
                'collection': 'users',
                'document': user.dict(exclude={'password_hash'})
            })
            
            if response.get('success'):
                created_user = response.get('data')
                
                # Update org user count
                await self.nats.publish("organization.increment_users", {
                    'org_id': org_id,
                    'increment': 1
                })
                
                # Send welcome email
                await self.nats.publish("email.send_welcome", {
                    'user_id': created_user.get('id'),
                    'email': user.email,
                    'first_name': user.first_name
                })
                
                # Publish event
                await self.nats.publish("user.created", created_user)
                
                await msg.respond(json.dumps({
                    'success': True,
                    'data': created_user
                }).encode())
            else:
                await msg.respond(json.dumps(response).encode())
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_invite_user(self, data: Dict[str, Any], msg) -> None:
        """Handle invite user request"""
        try:
            requester = data.get('requester', {})
            invite_data = data.get('invite', {})
            org_id = invite_data.get('org_id')
            
            # Check permissions
            if not self._has_permission(requester, 'user:invite', org_id):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to invite users'
                    }
                }).encode())
                return
                
            # Check if user already exists
            existing = await self.nats.request("db.find_one", {
                'collection': 'users',
                'filter': {
                    'email': invite_data.get('email'),
                    'org_id': org_id
                }
            })
            
            if existing.get('data'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'ALREADY_EXISTS',
                        'message': 'User already exists in organization'
                    }
                }).encode())
                return
                
            # Create invite
            invite = UserInvite(
                org_id=org_id,
                email=invite_data.get('email'),
                role=invite_data.get('role', UserRole.STAFF),
                invite_token=secrets.token_urlsafe(32),
                invited_by=requester.get('admin_id') or requester.get('user_id'),
                message=invite_data.get('message'),
                expires_at=datetime.utcnow() + timedelta(days=7)
            )
            
            # Save invite
            response = await self.nats.request("db.create", {
                'collection': 'user_invites',
                'document': invite.dict()
            })
            
            if response.get('success'):
                created_invite = response.get('data')
                
                # Send invite email
                await self.nats.publish("email.send_invite", {
                    'invite_id': created_invite.get('id'),
                    'email': invite.email,
                    'org_name': await self._get_org_name(org_id),
                    'invite_token': invite.invite_token,
                    'invited_by_name': await self._get_user_name(invite.invited_by),
                    'message': invite.message
                })
                
                await msg.respond(json.dumps({
                    'success': True,
                    'data': created_invite
                }).encode())
            else:
                await msg.respond(json.dumps(response).encode())
                
        except Exception as e:
            logger.error(f"Error inviting user: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_update_user(self, data: Dict[str, Any], msg) -> None:
        """Handle update user request"""
        try:
            user_id = data.get('user_id')
            updates = data.get('updates', {})
            requester = data.get('requester', {})
            
            # Get user to check org
            user_response = await self.nats.request("db.find_by_id", {
                'collection': 'users',
                'id': user_id
            })
            
            if not user_response.get('success'):
                await msg.respond(json.dumps(user_response).encode())
                return
                
            user = user_response.get('data')
            org_id = user.get('org_id')
            
            # Check permissions
            is_self = requester.get('user_id') == user_id
            can_manage = self._has_permission(requester, 'user:manage', org_id)
            
            if not (is_self or can_manage):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to update user'
                    }
                }).encode())
                return
                
            # Restrict what users can update about themselves
            if is_self and not can_manage:
                allowed_fields = [
                    'first_name', 'last_name', 'preferences',
                    'notification_settings', 'password'
                ]
                updates = {k: v for k, v in updates.items() if k in allowed_fields}
                
            # Handle password update
            if 'password' in updates:
                password = updates.pop('password')
                updates['password_hash'] = self.auth.hash_password(password)
                
            # Update user
            updates['updated_at'] = datetime.utcnow().isoformat()
            updates['updated_by'] = requester.get('admin_id') or requester.get('user_id')
            
            response = await self.nats.request("db.update", {
                'collection': 'users',
                'id': user_id,
                'updates': updates
            })
            
            if response.get('success'):
                # Publish event
                await self.nats.publish("user.updated", {
                    'user_id': user_id,
                    'org_id': org_id,
                    'updates': updates
                })
                
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_suspend_user(self, data: Dict[str, Any], msg) -> None:
        """Handle suspend user request"""
        try:
            user_id = data.get('user_id')
            reason = data.get('reason', 'Administrative action')
            requester = data.get('requester', {})
            
            # Get user
            user_response = await self.nats.request("db.find_by_id", {
                'collection': 'users',
                'id': user_id
            })
            
            if not user_response.get('success'):
                await msg.respond(json.dumps(user_response).encode())
                return
                
            user = user_response.get('data')
            org_id = user.get('org_id')
            
            # Check permissions
            if not self._has_permission(requester, 'user:manage', org_id):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to suspend user'
                    }
                }).encode())
                return
                
            # Suspend user
            response = await self.nats.request("db.update", {
                'collection': 'users',
                'id': user_id,
                'updates': {
                    'status': UserStatus.SUSPENDED,
                    'suspended_reason': reason,
                    'suspended_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat(),
                    'updated_by': requester.get('admin_id') or requester.get('user_id')
                }
            })
            
            if response.get('success'):
                # Invalidate user sessions
                await self.nats.publish("auth.invalidate_user_sessions", {
                    'user_id': user_id
                })
                
                # Publish event
                await self.nats.publish("user.suspended", {
                    'user_id': user_id,
                    'org_id': org_id,
                    'reason': reason
                })
                
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error suspending user: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_list_users(self, data: Dict[str, Any], msg) -> None:
        """Handle list users request"""
        try:
            org_id = data.get('org_id')
            requester = data.get('requester', {})
            
            # Check permissions
            if not self._has_permission(requester, 'user:read', org_id):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to list users'
                    }
                }).encode())
                return
                
            # Build filter
            filter_params = {'org_id': org_id}
            
            if data.get('status'):
                filter_params['status'] = data['status']
            if data.get('role'):
                filter_params['role'] = data['role']
                
            # List users
            response = await self.nats.request("db.find", {
                'collection': 'users',
                'filter': filter_params,
                'projection': {
                    'password_hash': 0
                },
                'sort': {'created_at': -1},
                'limit': data.get('limit', 50),
                'skip': data.get('skip', 0)
            })
            
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_create_owner(self, data: Dict[str, Any], msg) -> None:
        """Handle create organization owner (called when org is created)"""
        try:
            org_id = data.get('org_id')
            
            # Create owner user
            user = User(
                org_id=org_id,
                email=data.get('email'),
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                role=UserRole.OWNER,
                status=UserStatus.ACTIVE,
                email_verified=True,  # Trust org creation process
                created_by=data.get('created_by')
            )
            
            # Generate temporary password
            temp_password = secrets.token_urlsafe(12)
            user.password_hash = self.auth.hash_password(temp_password)
            
            # Save user
            response = await self.nats.request("db.create", {
                'collection': 'users',
                'document': user.dict(exclude={'password_hash'})
            })
            
            if response.get('success'):
                created_user = response.get('data')
                
                # Send welcome email with temp password
                await self.nats.publish("email.send_owner_welcome", {
                    'user_id': created_user.get('id'),
                    'email': user.email,
                    'first_name': user.first_name,
                    'temp_password': temp_password,
                    'org_id': org_id
                })
                
                logger.info(f"Created owner user for org {org_id}")
                
        except Exception as e:
            logger.error(f"Error creating owner user: {e}")
            
    async def handle_suspend_all(self, data: Dict[str, Any], msg) -> None:
        """Handle suspend all users in org (called when org is suspended)"""
        try:
            org_id = data.get('org_id')
            reason = data.get('reason', 'Organization suspended')
            
            # Update all active users
            await self.nats.request("db.update_many", {
                'collection': 'users',
                'filter': {
                    'org_id': org_id,
                    'status': UserStatus.ACTIVE
                },
                'updates': {
                    'status': UserStatus.SUSPENDED,
                    'suspended_reason': reason,
                    'suspended_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
            })
            
            # Invalidate all sessions for org
            await self.nats.publish("auth.invalidate_org_sessions", {
                'org_id': org_id
            })
            
            logger.info(f"Suspended all users in org {org_id}")
            
        except Exception as e:
            logger.error(f"Error suspending org users: {e}")
            
    def _has_permission(self, requester: Dict[str, Any], permission: str, org_id: str = None) -> bool:
        """Check if requester has permission"""
        # Super admin can do anything
        if requester.get('is_super_admin'):
            return True
            
        # Admin must have permission and org access
        if requester.get('admin_id'):
            has_perm = permission in requester.get('permissions', [])
            if org_id:
                org_ids = requester.get('org_ids', [])
                can_access = not org_ids or org_id in org_ids
                return has_perm and can_access
            return has_perm
            
        # Regular user permissions
        if requester.get('user_id'):
            user_perms = requester.get('permissions', [])
            return permission in user_perms
            
        return False
        
    async def _get_org_name(self, org_id: str) -> str:
        """Get organization name"""
        response = await self.nats.request("db.find_by_id", {
            'collection': 'organizations',
            'id': org_id,
            'projection': {'name': 1}
        })
        
        if response.get('success'):
            return response.get('data', {}).get('name', 'Organization')
        return 'Organization'
        
    async def _get_user_name(self, user_id: str) -> str:
        """Get user full name"""
        # Try users collection first
        response = await self.nats.request("db.find_by_id", {
            'collection': 'users',
            'id': user_id,
            'projection': {'first_name': 1, 'last_name': 1}
        })
        
        if response.get('success') and response.get('data'):
            user = response.get('data')
            return f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            
        # Try admin users
        response = await self.nats.request("db.find_by_id", {
            'collection': 'admin_users',
            'id': user_id,
            'projection': {'first_name': 1, 'last_name': 1}
        })
        
        if response.get('success') and response.get('data'):
            admin = response.get('data')
            return f"{admin.get('first_name', '')} {admin.get('last_name', '')}".strip()
            
        return 'User'
        
    async def setup_subscriptions(self):
        """Setup NATS subscriptions"""
        await self.nats.subscribe("user.create", self.handle_create_user)
        await self.nats.subscribe("user.invite", self.handle_invite_user)
        await self.nats.subscribe("user.update", self.handle_update_user)
        await self.nats.subscribe("user.suspend", self.handle_suspend_user)
        await self.nats.subscribe("user.list", self.handle_list_users)
        await self.nats.subscribe("user.create_owner", self.handle_create_owner)
        await self.nats.subscribe("user.suspend_all", self.handle_suspend_all)
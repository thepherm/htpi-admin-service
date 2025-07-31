"""Organization management controller"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from app.models import Organization, OrganizationStats, OrganizationStatus, BillingPlan

logger = logging.getLogger(__name__)


class OrganizationController:
    """Handle organization operations"""
    
    def __init__(self, nats_service):
        self.nats = nats_service
        
    async def handle_create_organization(self, data: Dict[str, Any], msg) -> None:
        """Handle create organization request"""
        try:
            requester = data.get('requester', {})
            
            # Check permissions
            if not self._has_permission(requester, 'org:create'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to create organization'
                    }
                }).encode())
                return
                
            # Create organization
            org_data = data.get('organization', {})
            
            # Set trial end date for new orgs
            if org_data.get('billing_plan') == BillingPlan.FREE_TRIAL:
                org_data['trial_ends_at'] = (
                    datetime.utcnow() + timedelta(days=30)
                ).isoformat()
                
            org = Organization(**org_data)
            org.created_by = requester.get('admin_id')
            
            # Check if organization name already exists
            existing = await self.nats.request("db.find_one", {
                'collection': 'organizations',
                'filter': {'name': org.name}
            })
            
            if existing.get('data'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'ALREADY_EXISTS',
                        'message': 'Organization with this name already exists'
                    }
                }).encode())
                return
                
            # Save to database
            response = await self.nats.request("db.create", {
                'collection': 'organizations',
                'document': org.dict()
            })
            
            if response.get('success'):
                created_org = response.get('data')
                
                # Create default admin user for organization
                await self.nats.publish("user.create_owner", {
                    'org_id': created_org.get('id'),
                    'email': org.primary_contact_email,
                    'first_name': org.primary_contact_name.split()[0],
                    'last_name': ' '.join(org.primary_contact_name.split()[1:]) or 'Admin',
                    'created_by': requester.get('admin_id')
                })
                
                # Publish event
                await self.nats.publish("organization.created", created_org)
                
                await msg.respond(json.dumps({
                    'success': True,
                    'data': created_org
                }).encode())
            else:
                await msg.respond(json.dumps(response).encode())
                
        except Exception as e:
            logger.error(f"Error creating organization: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_update_organization(self, data: Dict[str, Any], msg) -> None:
        """Handle update organization request"""
        try:
            org_id = data.get('org_id')
            updates = data.get('updates', {})
            requester = data.get('requester', {})
            
            # Check permissions
            if not self._has_permission(requester, 'org:update'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to update organization'
                    }
                }).encode())
                return
                
            # Check if admin can access this org
            if not self._can_access_org(requester, org_id):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Cannot access this organization'
                    }
                }).encode())
                return
                
            # Update organization
            updates['updated_at'] = datetime.utcnow().isoformat()
            updates['updated_by'] = requester.get('admin_id')
            
            response = await self.nats.request("db.update", {
                'collection': 'organizations',
                'id': org_id,
                'updates': updates
            })
            
            if response.get('success'):
                # Publish event
                await self.nats.publish("organization.updated", {
                    'org_id': org_id,
                    'updates': updates
                })
                
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error updating organization: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_suspend_organization(self, data: Dict[str, Any], msg) -> None:
        """Handle suspend organization request"""
        try:
            org_id = data.get('org_id')
            reason = data.get('reason', 'Administrative action')
            requester = data.get('requester', {})
            
            # Check permissions
            if not self._has_permission(requester, 'org:suspend'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to suspend organization'
                    }
                }).encode())
                return
                
            # Suspend organization
            response = await self.nats.request("db.update", {
                'collection': 'organizations',
                'id': org_id,
                'updates': {
                    'status': OrganizationStatus.SUSPENDED,
                    'suspended_reason': reason,
                    'suspended_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat(),
                    'updated_by': requester.get('admin_id')
                }
            })
            
            if response.get('success'):
                # Suspend all users
                await self.nats.publish("user.suspend_all", {
                    'org_id': org_id,
                    'reason': f"Organization suspended: {reason}"
                })
                
                # Publish event
                await self.nats.publish("organization.suspended", {
                    'org_id': org_id,
                    'reason': reason
                })
                
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error suspending organization: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_list_organizations(self, data: Dict[str, Any], msg) -> None:
        """Handle list organizations request"""
        try:
            requester = data.get('requester', {})
            
            # Check permissions
            if not self._has_permission(requester, 'org:read'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions to list organizations'
                    }
                }).encode())
                return
                
            # Build filter
            filter_params = {}
            
            if data.get('status'):
                filter_params['status'] = data['status']
            if data.get('type'):
                filter_params['type'] = data['type']
            if data.get('billing_plan'):
                filter_params['billing_plan'] = data['billing_plan']
                
            # If not super admin, limit to accessible orgs
            if not requester.get('is_super_admin'):
                org_ids = requester.get('org_ids', [])
                if org_ids:
                    filter_params['id'] = {'$in': org_ids}
                    
            # List organizations
            response = await self.nats.request("db.find", {
                'collection': 'organizations',
                'filter': filter_params,
                'sort': {'created_at': -1},
                'limit': data.get('limit', 50),
                'skip': data.get('skip', 0)
            })
            
            await msg.respond(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"Error listing organizations: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    async def handle_get_organization_stats(self, data: Dict[str, Any], msg) -> None:
        """Handle get organization statistics request"""
        try:
            org_id = data.get('org_id')
            requester = data.get('requester', {})
            period_days = data.get('period_days', 30)
            
            # Check permissions
            if not self._has_permission(requester, 'org:read'):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Insufficient permissions'
                    }
                }).encode())
                return
                
            # Check access
            if not self._can_access_org(requester, org_id):
                await msg.respond(json.dumps({
                    'success': False,
                    'error': {
                        'code': 'FORBIDDEN',
                        'message': 'Cannot access this organization'
                    }
                }).encode())
                return
                
            # Calculate period
            period_end = datetime.utcnow()
            period_start = period_end - timedelta(days=period_days)
            
            # Get organization stats from various services
            stats_requests = await asyncio.gather(
                self.nats.request("user.get_stats", {
                    'org_id': org_id,
                    'period_start': period_start.isoformat(),
                    'period_end': period_end.isoformat()
                }),
                self.nats.request("patient.get_stats", {
                    'org_id': org_id,
                    'period_start': period_start.isoformat(),
                    'period_end': period_end.isoformat()
                }),
                self.nats.request("claim.get_stats", {
                    'org_id': org_id,
                    'period_start': period_start.isoformat(),
                    'period_end': period_end.isoformat()
                }),
                return_exceptions=True
            )
            
            # Combine stats
            stats = OrganizationStats(
                org_id=org_id,
                period_start=period_start,
                period_end=period_end
            )
            
            # Process user stats
            if isinstance(stats_requests[0], dict) and stats_requests[0].get('success'):
                user_stats = stats_requests[0].get('data', {})
                stats.total_users = user_stats.get('total_users', 0)
                stats.active_users = user_stats.get('active_users', 0)
                stats.new_users = user_stats.get('new_users', 0)
                
            # Process patient stats
            if isinstance(stats_requests[1], dict) and stats_requests[1].get('success'):
                patient_stats = stats_requests[1].get('data', {})
                stats.total_patients = patient_stats.get('total_patients', 0)
                stats.new_patients = patient_stats.get('new_patients', 0)
                stats.active_patients = patient_stats.get('active_patients', 0)
                
            # Process claim stats
            if isinstance(stats_requests[2], dict) and stats_requests[2].get('success'):
                claim_stats = stats_requests[2].get('data', {})
                stats.total_claims = claim_stats.get('total_claims', 0)
                stats.submitted_claims = claim_stats.get('submitted_claims', 0)
                stats.accepted_claims = claim_stats.get('accepted_claims', 0)
                stats.rejected_claims = claim_stats.get('rejected_claims', 0)
                stats.pending_claims = claim_stats.get('pending_claims', 0)
                stats.total_billed = claim_stats.get('total_billed', 0.0)
                stats.total_collected = claim_stats.get('total_collected', 0.0)
                stats.outstanding_amount = claim_stats.get('outstanding_amount', 0.0)
                stats.avg_claim_processing_time = claim_stats.get('avg_processing_time', 0.0)
                stats.eligibility_check_count = claim_stats.get('eligibility_checks', 0)
                stats.era_received_count = claim_stats.get('era_received', 0)
                
            await msg.respond(json.dumps({
                'success': True,
                'data': stats.dict()
            }).encode())
            
        except Exception as e:
            logger.error(f"Error getting organization stats: {e}")
            await msg.respond(json.dumps({
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e)
                }
            }).encode())
            
    def _has_permission(self, requester: Dict[str, Any], permission: str) -> bool:
        """Check if requester has permission"""
        if requester.get('is_super_admin'):
            return True
        return permission in requester.get('permissions', [])
        
    def _can_access_org(self, requester: Dict[str, Any], org_id: str) -> bool:
        """Check if requester can access organization"""
        if requester.get('is_super_admin'):
            return True
        org_ids = requester.get('org_ids', [])
        return not org_ids or org_id in org_ids
        
    async def setup_subscriptions(self):
        """Setup NATS subscriptions"""
        await self.nats.subscribe("organization.create", self.handle_create_organization)
        await self.nats.subscribe("organization.update", self.handle_update_organization)
        await self.nats.subscribe("organization.suspend", self.handle_suspend_organization)
        await self.nats.subscribe("organization.list", self.handle_list_organizations)
        await self.nats.subscribe("organization.get_stats", self.handle_get_organization_stats)
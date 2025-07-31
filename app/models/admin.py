"""Admin user models"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr, validator
from enum import Enum


class AdminRole(str, Enum):
    """Admin role types"""
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    BILLING_ADMIN = "billing_admin"
    CLINICAL_ADMIN = "clinical_admin"
    SUPPORT_ADMIN = "support_admin"
    READ_ONLY_ADMIN = "read_only"


class AdminPermission(str, Enum):
    """Admin permissions"""
    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_SUSPEND = "user:suspend"
    
    # Organization management
    ORG_CREATE = "org:create"
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"
    ORG_SUSPEND = "org:suspend"
    
    # Billing management
    BILLING_VIEW = "billing:view"
    BILLING_UPDATE = "billing:update"
    BILLING_EXPORT = "billing:export"
    
    # Clinical management
    CLINICAL_VIEW = "clinical:view"
    CLINICAL_AUDIT = "clinical:audit"
    CLINICAL_EXPORT = "clinical:export"
    
    # System management
    SYSTEM_CONFIG = "system:config"
    SYSTEM_MONITOR = "system:monitor"
    SYSTEM_AUDIT = "system:audit"
    
    # Report access
    REPORT_VIEW = "report:view"
    REPORT_CREATE = "report:create"
    REPORT_EXPORT = "report:export"


class AdminUser(BaseModel):
    """Admin user model"""
    id: Optional[str] = Field(None, description="Admin user ID")
    email: EmailStr = Field(..., description="Admin email address")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: AdminRole = Field(..., description="Admin role")
    permissions: List[AdminPermission] = Field(default_factory=list)
    org_ids: List[str] = Field(default_factory=list, description="Organizations the admin can access")
    is_active: bool = Field(True, description="Whether admin is active")
    is_super_admin: bool = Field(False, description="Whether admin has super admin privileges")
    
    # Security
    password_hash: Optional[str] = Field(None, description="Hashed password")
    mfa_enabled: bool = Field(False, description="Whether MFA is enabled")
    mfa_secret: Optional[str] = Field(None, description="MFA secret key")
    
    # Session management
    last_login: Optional[datetime] = None
    failed_login_attempts: int = Field(0)
    locked_until: Optional[datetime] = None
    
    # Audit fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    @validator('permissions', pre=True, always=True)
    def set_permissions_by_role(cls, v, values):
        """Set default permissions based on role"""
        role = values.get('role')
        if not v and role:
            if role == AdminRole.SUPER_ADMIN:
                return list(AdminPermission)
            elif role == AdminRole.ORG_ADMIN:
                return [
                    AdminPermission.USER_CREATE,
                    AdminPermission.USER_READ,
                    AdminPermission.USER_UPDATE,
                    AdminPermission.USER_SUSPEND,
                    AdminPermission.ORG_READ,
                    AdminPermission.ORG_UPDATE,
                    AdminPermission.BILLING_VIEW,
                    AdminPermission.CLINICAL_VIEW,
                    AdminPermission.REPORT_VIEW,
                    AdminPermission.REPORT_CREATE
                ]
            elif role == AdminRole.BILLING_ADMIN:
                return [
                    AdminPermission.BILLING_VIEW,
                    AdminPermission.BILLING_UPDATE,
                    AdminPermission.BILLING_EXPORT,
                    AdminPermission.REPORT_VIEW,
                    AdminPermission.REPORT_EXPORT
                ]
            elif role == AdminRole.CLINICAL_ADMIN:
                return [
                    AdminPermission.CLINICAL_VIEW,
                    AdminPermission.CLINICAL_AUDIT,
                    AdminPermission.CLINICAL_EXPORT,
                    AdminPermission.REPORT_VIEW,
                    AdminPermission.REPORT_CREATE
                ]
            elif role == AdminRole.SUPPORT_ADMIN:
                return [
                    AdminPermission.USER_READ,
                    AdminPermission.ORG_READ,
                    AdminPermission.CLINICAL_VIEW,
                    AdminPermission.SYSTEM_MONITOR
                ]
            elif role == AdminRole.READ_ONLY_ADMIN:
                return [
                    AdminPermission.USER_READ,
                    AdminPermission.ORG_READ,
                    AdminPermission.BILLING_VIEW,
                    AdminPermission.CLINICAL_VIEW,
                    AdminPermission.REPORT_VIEW
                ]
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AdminSession(BaseModel):
    """Admin session model"""
    id: str = Field(..., description="Session ID")
    admin_id: str = Field(..., description="Admin user ID")
    token: str = Field(..., description="Session token")
    ip_address: str = Field(..., description="IP address")
    user_agent: str = Field(..., description="User agent")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(..., description="Session expiration")
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(True)


class AuditLog(BaseModel):
    """Admin audit log model"""
    id: Optional[str] = Field(None, description="Audit log ID")
    admin_id: str = Field(..., description="Admin who performed the action")
    action: str = Field(..., description="Action performed")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: Optional[str] = Field(None, description="ID of resource affected")
    org_id: Optional[str] = Field(None, description="Organization context")
    
    # Details
    ip_address: str = Field(..., description="IP address of request")
    user_agent: str = Field(..., description="User agent")
    request_method: str = Field(..., description="HTTP method")
    request_path: str = Field(..., description="Request path")
    
    # Change tracking
    old_values: Optional[Dict[str, Any]] = Field(None, description="Previous values")
    new_values: Optional[Dict[str, Any]] = Field(None, description="New values")
    
    # Result
    success: bool = Field(..., description="Whether action succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
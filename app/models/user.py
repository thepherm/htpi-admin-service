"""User management models"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from enum import Enum


class UserRole(str, Enum):
    """User roles within an organization"""
    OWNER = "owner"
    ADMIN = "admin"
    BILLER = "biller"
    PROVIDER = "provider"
    STAFF = "staff"
    READ_ONLY = "read_only"


class UserStatus(str, Enum):
    """User status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class UserPermission(str, Enum):
    """User permissions"""
    # Patient management
    PATIENT_CREATE = "patient:create"
    PATIENT_READ = "patient:read"
    PATIENT_UPDATE = "patient:update"
    PATIENT_DELETE = "patient:delete"
    
    # Insurance management
    INSURANCE_CREATE = "insurance:create"
    INSURANCE_READ = "insurance:read"
    INSURANCE_UPDATE = "insurance:update"
    INSURANCE_DELETE = "insurance:delete"
    INSURANCE_VERIFY = "insurance:verify"
    
    # Form management
    FORM_CREATE = "form:create"
    FORM_READ = "form:read"
    FORM_UPDATE = "form:update"
    FORM_DELETE = "form:delete"
    FORM_SUBMIT = "form:submit"
    
    # Claim management
    CLAIM_SUBMIT = "claim:submit"
    CLAIM_READ = "claim:read"
    CLAIM_UPDATE = "claim:update"
    CLAIM_BATCH = "claim:batch"
    
    # Reporting
    REPORT_VIEW = "report:view"
    REPORT_EXPORT = "report:export"
    
    # Organization settings
    ORG_SETTINGS_VIEW = "org:settings:view"
    ORG_SETTINGS_UPDATE = "org:settings:update"
    
    # User management
    USER_INVITE = "user:invite"
    USER_MANAGE = "user:manage"


class User(BaseModel):
    """Organization user model"""
    id: Optional[str] = Field(None, description="User ID")
    org_id: str = Field(..., description="Organization ID")
    email: EmailStr = Field(..., description="User email")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    
    # Role and permissions
    role: UserRole = Field(..., description="User role")
    permissions: List[UserPermission] = Field(default_factory=list)
    custom_permissions: List[str] = Field(default_factory=list)
    
    # Professional info
    npi: Optional[str] = Field(None, description="National Provider Identifier")
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    specialty: Optional[str] = None
    
    # Account info
    status: UserStatus = Field(UserStatus.PENDING_VERIFICATION)
    email_verified: bool = Field(False)
    password_hash: Optional[str] = Field(None, exclude=True)
    
    # Settings
    preferences: Dict[str, Any] = Field(default_factory=dict)
    notification_settings: Dict[str, bool] = Field(default_factory=lambda: {
        'email_claims': True,
        'email_patients': True,
        'email_billing': True,
        'sms_enabled': False
    })
    
    # Activity
    last_login: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    login_count: int = Field(0)
    
    # Audit fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    def get_all_permissions(self) -> List[str]:
        """Get all user permissions including role-based ones"""
        role_permissions = self._get_role_permissions()
        all_perms = set(role_permissions + self.permissions + self.custom_permissions)
        return list(all_perms)
    
    def _get_role_permissions(self) -> List[UserPermission]:
        """Get permissions based on role"""
        if self.role == UserRole.OWNER:
            return list(UserPermission)
        elif self.role == UserRole.ADMIN:
            return [p for p in UserPermission if not p.value.startswith('org:settings')]
        elif self.role == UserRole.BILLER:
            return [
                UserPermission.PATIENT_READ,
                UserPermission.INSURANCE_CREATE,
                UserPermission.INSURANCE_READ,
                UserPermission.INSURANCE_UPDATE,
                UserPermission.INSURANCE_VERIFY,
                UserPermission.FORM_CREATE,
                UserPermission.FORM_READ,
                UserPermission.FORM_UPDATE,
                UserPermission.FORM_SUBMIT,
                UserPermission.CLAIM_SUBMIT,
                UserPermission.CLAIM_READ,
                UserPermission.CLAIM_UPDATE,
                UserPermission.CLAIM_BATCH,
                UserPermission.REPORT_VIEW,
                UserPermission.REPORT_EXPORT
            ]
        elif self.role == UserRole.PROVIDER:
            return [
                UserPermission.PATIENT_CREATE,
                UserPermission.PATIENT_READ,
                UserPermission.PATIENT_UPDATE,
                UserPermission.INSURANCE_READ,
                UserPermission.FORM_CREATE,
                UserPermission.FORM_READ,
                UserPermission.FORM_UPDATE,
                UserPermission.CLAIM_READ,
                UserPermission.REPORT_VIEW
            ]
        elif self.role == UserRole.STAFF:
            return [
                UserPermission.PATIENT_CREATE,
                UserPermission.PATIENT_READ,
                UserPermission.PATIENT_UPDATE,
                UserPermission.INSURANCE_READ,
                UserPermission.FORM_READ,
                UserPermission.CLAIM_READ
            ]
        else:  # READ_ONLY
            return [
                UserPermission.PATIENT_READ,
                UserPermission.INSURANCE_READ,
                UserPermission.FORM_READ,
                UserPermission.CLAIM_READ,
                UserPermission.REPORT_VIEW
            ]
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserInvite(BaseModel):
    """User invitation model"""
    id: Optional[str] = Field(None, description="Invite ID")
    org_id: str = Field(..., description="Organization ID")
    email: EmailStr = Field(..., description="Invited email")
    role: UserRole = Field(..., description="Assigned role")
    
    # Invite details
    invite_token: str = Field(..., description="Unique invite token")
    invited_by: str = Field(..., description="User ID who sent invite")
    message: Optional[str] = Field(None, description="Custom invite message")
    
    # Status
    status: str = Field("pending")  # pending, accepted, expired
    accepted_at: Optional[datetime] = None
    expires_at: datetime = Field(..., description="Invite expiration")
    
    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
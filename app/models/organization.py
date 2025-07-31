"""Organization management models"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


class OrganizationType(str, Enum):
    """Organization types"""
    HOSPITAL = "hospital"
    CLINIC = "clinic"
    PRIVATE_PRACTICE = "private_practice"
    URGENT_CARE = "urgent_care"
    SPECIALTY_CENTER = "specialty_center"
    BILLING_COMPANY = "billing_company"
    OTHER = "other"


class OrganizationStatus(str, Enum):
    """Organization status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"
    PENDING_APPROVAL = "pending_approval"
    TRIAL = "trial"


class BillingPlan(str, Enum):
    """Billing plans"""
    FREE_TRIAL = "free_trial"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class Organization(BaseModel):
    """Organization model"""
    id: Optional[str] = Field(None, description="Organization ID")
    name: str = Field(..., min_length=1, max_length=200)
    type: OrganizationType = Field(..., description="Organization type")
    tax_id: Optional[str] = Field(None, description="Tax ID / EIN")
    npi: Optional[str] = Field(None, description="National Provider Identifier")
    
    # Contact information
    primary_contact_name: str = Field(..., min_length=1)
    primary_contact_email: str = Field(..., description="Primary contact email")
    primary_contact_phone: str = Field(..., description="Primary contact phone")
    
    # Address
    address_line1: str = Field(..., min_length=1)
    address_line2: Optional[str] = None
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str = Field(..., pattern=r'^\d{5}(-\d{4})?$')
    country: str = Field("US", min_length=2, max_length=2)
    
    # Billing
    billing_plan: BillingPlan = Field(BillingPlan.FREE_TRIAL)
    billing_contact_email: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    trial_ends_at: Optional[datetime] = None
    
    # Status
    status: OrganizationStatus = Field(OrganizationStatus.PENDING_APPROVAL)
    suspended_reason: Optional[str] = None
    suspended_at: Optional[datetime] = None
    
    # Settings
    settings: Dict[str, Any] = Field(default_factory=dict)
    features: List[str] = Field(default_factory=list)
    
    # Limits
    max_users: int = Field(10, description="Maximum number of users")
    max_patients: int = Field(1000, description="Maximum number of patients")
    max_claims_per_month: int = Field(500, description="Maximum claims per month")
    
    # Usage
    current_users: int = Field(0)
    current_patients: int = Field(0)
    claims_this_month: int = Field(0)
    
    # Audit fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    @validator('billing_contact_email', pre=True, always=True)
    def set_billing_email(cls, v, values):
        """Default billing email to primary contact email"""
        if not v:
            return values.get('primary_contact_email')
        return v
    
    @validator('features', pre=True, always=True)
    def set_features_by_plan(cls, v, values):
        """Set features based on billing plan"""
        plan = values.get('billing_plan')
        if not v and plan:
            if plan == BillingPlan.FREE_TRIAL:
                return ['basic_claims', 'patient_management']
            elif plan == BillingPlan.BASIC:
                return ['basic_claims', 'patient_management', 'insurance_verification']
            elif plan == BillingPlan.PROFESSIONAL:
                return [
                    'basic_claims', 'patient_management', 'insurance_verification',
                    'batch_claims', 'era_processing', 'reporting'
                ]
            elif plan in [BillingPlan.ENTERPRISE, BillingPlan.CUSTOM]:
                return [
                    'basic_claims', 'patient_management', 'insurance_verification',
                    'batch_claims', 'era_processing', 'reporting', 'api_access',
                    'custom_workflows', 'advanced_analytics'
                ]
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class OrganizationStats(BaseModel):
    """Organization statistics"""
    org_id: str
    period_start: datetime
    period_end: datetime
    
    # User stats
    total_users: int = 0
    active_users: int = 0
    new_users: int = 0
    
    # Patient stats
    total_patients: int = 0
    new_patients: int = 0
    active_patients: int = 0
    
    # Claim stats
    total_claims: int = 0
    submitted_claims: int = 0
    accepted_claims: int = 0
    rejected_claims: int = 0
    pending_claims: int = 0
    
    # Financial stats
    total_billed: float = 0.0
    total_collected: float = 0.0
    outstanding_amount: float = 0.0
    
    # Performance
    avg_claim_processing_time: float = 0.0
    eligibility_check_count: int = 0
    era_received_count: int = 0
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
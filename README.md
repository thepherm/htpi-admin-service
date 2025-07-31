# HTPI Admin Service

Administrative backend service for managing organizations, users, and system-wide operations in the HTPI ecosystem.

## Overview

The HTPI Admin Service provides:

- **Super Admin Management**: System-wide administrative functions
- **Organization Management**: Create, update, suspend organizations
- **User Management**: Manage users across organizations
- **Billing Management**: Handle billing plans and limits
- **Audit Logging**: Track all administrative actions
- **Statistics & Reporting**: Organization and system-wide metrics

## Features

### Admin Management
- Super admin accounts with full system access
- Role-based permissions (super_admin, org_admin, billing_admin, etc.)
- Multi-factor authentication support
- Session management and security

### Organization Management
- Create and manage healthcare organizations
- Billing plan management (Free Trial, Basic, Professional, Enterprise)
- Usage limits and quotas
- Organization suspension and reactivation
- Multi-tenant data isolation

### User Management
- Create and invite users
- Role-based access control
- User suspension and reactivation
- Password management
- Activity tracking

### Audit & Compliance
- Comprehensive audit logging
- HIPAA-compliant data handling
- Activity tracking and reporting
- Security event monitoring

## Architecture

```
Admin Service <---> NATS <---> MongoDB Service
                     |
                     +---> Other HTPI Services
```

## Prerequisites

- Python 3.11+
- NATS server with JetStream
- MongoDB (via htpi-mongodb-service)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/htpi-admin-service.git
cd htpi-admin-service
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Set environment variables or create a `.env` file:

```env
# Service Configuration
SERVICE_NAME=htpi-admin-service
HOST=0.0.0.0
PORT=8080

# NATS Configuration
NATS_URL=nats://localhost:4222
NATS_USER=admin_user
NATS_PASSWORD=your_password

# JWT Configuration
JWT_SECRET=your_jwt_secret
JWT_ALGORITHM=HS256
JWT_EXPIRATION_DELTA=3600

# Default Super Admin
SUPER_ADMIN_EMAIL=admin@htpi.com
DEFAULT_ADMIN_PASSWORD=changeme123

# Service URLs
GATEWAY_URL=http://localhost:8000
```

## Running the Service

### Development
```bash
python -m app.main
```

### Production (Docker)
```bash
docker build -t htpi-admin-service .
docker run --env-file .env htpi-admin-service
```

### Deploy to Railway
```bash
railway login
railway link
railway up
```

## Default Super Admin

On first run, the service creates a default super admin account:
- Email: `admin@htpi.com` (configurable)
- Password: `changeme123` (configurable)

**Important**: Change the default password immediately after first login!

## API Operations (via NATS)

### Admin Operations

- `admin.create` - Create new admin user
- `admin.update` - Update admin details
- `admin.delete` - Delete (deactivate) admin
- `admin.list` - List admin users
- `admin.get_by_email` - Get admin by email

### Organization Operations

- `organization.create` - Create new organization
- `organization.update` - Update organization
- `organization.suspend` - Suspend organization
- `organization.list` - List organizations
- `organization.get_stats` - Get organization statistics

### User Operations

- `user.create` - Create new user
- `user.invite` - Send user invitation
- `user.update` - Update user details
- `user.suspend` - Suspend user
- `user.list` - List users in organization

## Roles and Permissions

### Admin Roles

1. **Super Admin**
   - Full system access
   - Can manage all organizations
   - Can create other admins

2. **Organization Admin**
   - Manage users in assigned organizations
   - View organization settings
   - Access reports

3. **Billing Admin**
   - View and update billing information
   - Export billing reports
   - Manage payment methods

4. **Clinical Admin**
   - View clinical data
   - Run clinical audits
   - Export clinical reports

5. **Support Admin**
   - Read-only access to user/org data
   - Monitor system health
   - Assist with support tickets

### User Roles (within organizations)

1. **Owner**
   - Full access within organization
   - Can manage all settings

2. **Admin**
   - Manage users and settings
   - Full operational access

3. **Biller**
   - Submit and manage claims
   - Access billing reports

4. **Provider**
   - Create patients and forms
   - View claims

5. **Staff**
   - Basic patient management
   - Limited access

## Security

- JWT-based authentication
- Password hashing with bcrypt
- Session management
- IP-based access tracking
- Failed login attempt tracking
- Account lockout protection

## Monitoring

The service tracks:
- Admin login attempts
- Permission usage
- Organization limits
- User activity
- System health metrics

## Development

### Project Structure
```
htpi-admin-service/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── controllers/
│   │   ├── admin_controller.py
│   │   ├── organization_controller.py
│   │   └── user_controller.py
│   ├── models/
│   │   ├── admin.py
│   │   ├── organization.py
│   │   └── user.py
│   └── services/
│       ├── auth_service.py
│       └── nats_service.py
├── requirements.txt
├── Dockerfile
└── README.md
```

### Testing
```bash
pytest tests/
```

### Code Style
```bash
black app/
isort app/
flake8 app/
```

## Troubleshooting

### Super Admin Login Issues
- Verify JWT_SECRET matches across services
- Check NATS connectivity
- Ensure MongoDB service is running

### Organization Limits
- Check billing plan limits
- Monitor usage metrics
- Review audit logs

### Permission Errors
- Verify admin role and permissions
- Check organization access
- Review audit logs for denied actions

## License

MIT
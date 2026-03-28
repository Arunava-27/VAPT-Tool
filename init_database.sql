-- VAPT Platform Database Initialization Script
-- Run this in PostgreSQL to set up the schema

-- ============================================================================
-- TABLE 1: Tenants
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    contact_email VARCHAR(255),
    schema_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}',
    max_users INTEGER DEFAULT 10,
    max_scans INTEGER DEFAULT 100,
    max_concurrent_scans INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE tenants IS 'Multi-tenant organizations';

-- ============================================================================
-- TABLE 2: Roles
-- ============================================================================

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB DEFAULT '[]',
    is_system_role BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE roles IS 'RBAC roles with permissions';

-- ============================================================================
-- TABLE 3: Users
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    reset_token VARCHAR(255),
    reset_token_expires TIMESTAMP,
    last_login TIMESTAMP,
    login_count VARCHAR(10) DEFAULT '0',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

COMMENT ON TABLE users IS 'Platform users with authentication';

-- ============================================================================
-- TABLE 4: User-Role Junction
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id)
);

COMMENT ON TABLE user_roles IS 'Many-to-many relationship between users and roles';

-- ============================================================================
-- TABLE 5: Scans
-- ============================================================================

CREATE TABLE IF NOT EXISTS scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    scan_type VARCHAR(50) NOT NULL,
    target VARCHAR(500) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    scan_config JSONB DEFAULT '{}',
    result_summary JSONB,
    error TEXT,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scans_tenant ON scans(tenant_id);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);
CREATE INDEX IF NOT EXISTS idx_scans_created_by ON scans(created_by_id);
CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at DESC);

COMMENT ON TABLE scans IS 'Security scan jobs';

-- ============================================================================
-- INSERT DEFAULT DATA
-- ============================================================================

-- Insert default tenant
INSERT INTO tenants (name, slug, contact_email, schema_name, is_active, max_users, max_scans, max_concurrent_scans)
VALUES ('Default Organization', 'default', 'admin@vapt-platform.local', 'default', TRUE, 50, 1000, 10)
ON CONFLICT (slug) DO UPDATE 
SET updated_at = CURRENT_TIMESTAMP
RETURNING id;

-- Insert system roles
INSERT INTO roles (name, slug, description, permissions, is_system_role, is_active)
VALUES 
    ('Super Administrator', 'super_admin', 'Full system access across all tenants', 
     '["manage_tenants","manage_users","manage_roles","manage_scans","create_scans","view_scans","view_reports","export_results","manage_settings","view_audit_logs","manage_api_keys"]'::jsonb, 
     TRUE, TRUE),
    ('Tenant Administrator', 'tenant_admin', 'Full access within their tenant', 
     '["manage_users","manage_roles","manage_scans","create_scans","view_scans","view_reports","export_results","manage_settings","view_audit_logs"]'::jsonb, 
     TRUE, TRUE),
    ('Security Analyst', 'analyst', 'Can create and manage scans', 
     '["create_scans","manage_scans","view_scans","view_reports","export_results"]'::jsonb, 
     TRUE, TRUE),
    ('Viewer', 'viewer', 'Read-only access to scans and reports', 
     '["view_scans","view_reports"]'::jsonb, 
     TRUE, TRUE)
ON CONFLICT (slug) DO UPDATE 
SET updated_at = CURRENT_TIMESTAMP;

-- ============================================================================
-- CREATE SUPERUSER
-- ============================================================================

-- Get the default tenant ID
DO $$
DECLARE
    default_tenant_id UUID;
    super_admin_role_id UUID;
    new_user_id UUID;
BEGIN
    -- Get tenant ID
    SELECT id INTO default_tenant_id FROM tenants WHERE slug = 'default';
    
    -- Get super_admin role ID
    SELECT id INTO super_admin_role_id FROM roles WHERE slug = 'super_admin';
    
    -- Insert superuser (password: changeme123)
    -- This is a bcrypt hash of 'changeme123'
    INSERT INTO users (email, hashed_password, full_name, is_superuser, is_verified, is_active, tenant_id)
    VALUES (
        'admin@vapt-platform.local',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lZCj7CqJ.xGa',  -- changeme123
        'Super Administrator',
        TRUE,
        TRUE,
        TRUE,
        default_tenant_id
    )
    ON CONFLICT (email) DO UPDATE 
    SET updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO new_user_id;
    
    -- Assign super_admin role
    INSERT INTO user_roles (user_id, role_id)
    VALUES (new_user_id, super_admin_role_id)
    ON CONFLICT DO NOTHING;
    
    RAISE NOTICE 'Superuser created/updated with ID: %', new_user_id;
END $$;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Show created tables
SELECT 
    schemaname,
    tablename,
    tableowner
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN ('tenants', 'roles', 'users', 'user_roles', 'scans')
ORDER BY tablename;

-- Show tenant
SELECT id, name, slug, contact_email, is_active FROM tenants;

-- Show roles
SELECT id, name, slug, is_system_role FROM roles ORDER BY slug;

-- Show superuser
SELECT u.id, u.email, u.full_name, u.is_superuser, t.name as tenant_name
FROM users u
JOIN tenants t ON u.tenant_id = t.id;

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE '✅ Database initialized successfully!';
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE '';
    RAISE NOTICE 'Default Login Credentials:';
    RAISE NOTICE '  Email:    admin@vapt-platform.local';
    RAISE NOTICE '  Password: changeme123';
    RAISE NOTICE '';
    RAISE NOTICE '⚠️  Remember to change the password after first login!';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables Created:';
    RAISE NOTICE '  • tenants (1 row)';
    RAISE NOTICE '  • roles (4 rows)';
    RAISE NOTICE '  • users (1 row)';
    RAISE NOTICE '  • user_roles (1 row)';
    RAISE NOTICE '  • scans (0 rows)';
    RAISE NOTICE '';
END $$;

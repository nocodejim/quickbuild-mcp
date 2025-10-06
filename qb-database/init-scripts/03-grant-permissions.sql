-- QuickBuild 14 User Permissions Script
-- Grants necessary permissions to qb_user for QuickBuild operations
-- Uses db_owner role for full database access as required by QuickBuild

USE quickbuild;
GO

-- Grant db_owner role to qb_user
-- QuickBuild requires extensive database permissions for schema management
IF IS_ROLEMEMBER('db_owner', 'qb_user') = 0
BEGIN
    PRINT 'Granting db_owner role to qb_user...'
    
    ALTER ROLE db_owner ADD MEMBER qb_user;
    
    PRINT 'db_owner role granted to qb_user successfully.'
END
ELSE
BEGIN
    PRINT 'qb_user already has db_owner role.'
END
GO

-- Grant additional server-level permissions if needed
USE master;
GO

-- Grant VIEW SERVER STATE for monitoring (optional)
IF NOT EXISTS (
    SELECT * FROM sys.server_permissions sp
    JOIN sys.server_principals pr ON sp.grantee_principal_id = pr.principal_id
    WHERE pr.name = 'qb_user' AND sp.permission_name = 'VIEW SERVER STATE'
)
BEGIN
    PRINT 'Granting VIEW SERVER STATE permission to qb_user...'
    
    GRANT VIEW SERVER STATE TO qb_user;
    
    PRINT 'VIEW SERVER STATE permission granted successfully.'
END
ELSE
BEGIN
    PRINT 'qb_user already has VIEW SERVER STATE permission.'
END
GO

-- Verify permissions
USE quickbuild;
GO

PRINT 'Verifying qb_user permissions...'

-- Check if user exists and has proper role membership
SELECT 
    dp.name AS principal_name,
    dp.type_desc AS principal_type,
    r.name AS role_name
FROM sys.database_role_members rm
JOIN sys.database_principals dp ON rm.member_principal_id = dp.principal_id
JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
WHERE dp.name = 'qb_user';

PRINT 'Permission verification completed.'
GO
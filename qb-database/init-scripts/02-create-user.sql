-- QuickBuild 14 User Creation Script
-- Creates dedicated qb_user for QuickBuild server connections
-- Uses strong password and minimal required permissions

USE master;
GO

-- Create login for QuickBuild user
-- Password will be set via environment variable QB_DB_PASSWORD
DECLARE @password NVARCHAR(128) = '$(QB_DB_PASSWORD)'
DECLARE @sql NVARCHAR(MAX)

-- Check if login already exists
IF NOT EXISTS (SELECT name FROM sys.server_principals WHERE name = 'qb_user')
BEGIN
    PRINT 'Creating qb_user login...'
    
    -- Create the login with the provided password
    SET @sql = 'CREATE LOGIN qb_user WITH PASSWORD = ''' + @password + ''', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF'
    EXEC sp_executesql @sql
    
    PRINT 'qb_user login created successfully.'
END
ELSE
BEGIN
    PRINT 'qb_user login already exists.'
    
    -- Update password in case it changed
    SET @sql = 'ALTER LOGIN qb_user WITH PASSWORD = ''' + @password + ''''
    EXEC sp_executesql @sql
    
    PRINT 'qb_user password updated.'
END
GO

-- Switch to quickbuild database to create user
USE quickbuild;
GO

-- Create database user for the login
IF NOT EXISTS (SELECT name FROM sys.database_principals WHERE name = 'qb_user')
BEGIN
    PRINT 'Creating qb_user database user...'
    
    CREATE USER qb_user FOR LOGIN qb_user;
    
    PRINT 'qb_user database user created successfully.'
END
ELSE
BEGIN
    PRINT 'qb_user database user already exists.'
END
GO